from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .config import settings
from .db import Database
from .memory import MemoryStore
from .orchestrator import Orchestrator
from .llm import build_llm_provider
from .retention import RetentionManager
from .excel_reader import read_excel_rows

logger = logging.getLogger(__name__)


class AnalyzeRequest(BaseModel):
    project_name: str = "默认分析项目"
    request: str
    data: list[dict[str, Any]] | None = None
    csv_path: str | None = None
    project_id: str | None = None
    product_mode: str = "offline"
    requested_types: list[str] | None = None
    chart_types: list[str] | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    date_range: str | None = None
    privacy_consent: bool = True


class AgentRunRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class OptimizeRequest(BaseModel):
    request: str
    product_mode: str = "offline"
    requested_types: list[str] | None = None
    chart_types: list[str] | None = None
    date_range: str | None = None


class FilterRequest(BaseModel):
    rows: list[dict[str, Any]]
    product_mode: str = "offline"
    requested_types: list[str] | None = None
    filters: dict[str, Any] = Field(default_factory=dict)


class ConversationRequest(BaseModel):
    project_id: str | None = None
    user_message: str
    assistant_message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RerunRequest(BaseModel):
    from_step: int = Field(default=1, ge=1, le=7)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_directories()
    logging.getLogger().setLevel(logging.INFO)
    log_path = (settings.storage_path / "logs" / "app.log").resolve()
    if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == str(log_path) for h in logging.getLogger().handlers):
        handler = logging.FileHandler(log_path, encoding="utf-8"); handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")); logging.getLogger().addHandler(handler)
    retention = RetentionManager(settings.storage_path, settings.retention_days); retention.cleanup(); retention.start(settings.cleanup_interval_seconds); app.state.retention = retention
    yield
    retention.stop()


settings.ensure_directories()
app = FastAPI(title="多智能体数据处理与营销策略 API", version="0.2.0", lifespan=lifespan)
memory = MemoryStore(Database(settings.database_path), settings.storage_path)
llm_provider = build_llm_provider(settings)
orchestrator = Orchestrator(memory, settings.storage_path, max_filter_rows=settings.max_filter_rows, max_retries=settings.max_retries, llm=llm_provider)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (Path(__file__).resolve().parent / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": settings.app_name, "retention_days": settings.retention_days, "llm_provider": getattr(llm_provider, "provider_name", "unknown"), "llm_model": getattr(llm_provider, "model", "unknown")}


@app.get("/api/projects")
def projects() -> dict[str, Any]:
    return {"projects": memory.list_projects()}


@app.get("/api/runs")
def runs(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return {"runs": memory.list_runs(limit)}


@app.get("/api/agents")
def agents() -> dict[str, Any]:
    return {"agents": orchestrator.list_agents()}


@app.post("/api/prompt/optimize")
def optimize(body: OptimizeRequest) -> dict[str, Any]:
    try: return orchestrator.optimize(request=body.request, product_mode=body.product_mode, requested_types=body.requested_types, chart_types=body.chart_types, date_range=body.date_range)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@app.post("/api/filter")
def filter_endpoint(body: FilterRequest) -> dict[str, Any]:
    from .selection import filter_data, resolve_selection
    try:
        selection = resolve_selection(body.product_mode, body.requested_types)
        return {"selection": selection, **filter_data(body.rows, selection=selection, filters=body.filters, max_rows=settings.max_filter_rows)}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@app.post("/api/devote")
def devote_endpoint() -> dict[str, Any]:
    from .selection import devote
    return {"steps": devote()}


@app.post("/api/analyze")
def analyze(body: AnalyzeRequest) -> dict[str, Any]:
    if not body.data and not body.csv_path: raise HTTPException(422, "data 或 csv_path 至少提供一个")
    try:
        return orchestrator.analyze(project_name=body.project_name, request=body.request, data=body.data, csv_path=body.csv_path, project_id=body.project_id, product_mode=body.product_mode, requested_types=body.requested_types, chart_types=body.chart_types, filters=body.filters, date_range=body.date_range, privacy_consent=body.privacy_consent)
    except PermissionError as exc: raise HTTPException(403, str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc: raise HTTPException(422, str(exc)) from exc
    except Exception as exc: logger.exception("analysis failed"); raise HTTPException(500, str(exc)) from exc


@app.post("/api/analyze/excel")
async def analyze_excel(
    file: UploadFile = File(...),
    project_name: str = Form("默认分析项目"),
    request: str = Form(...),
    product_mode: str = Form("offline"),
    privacy_consent: bool = Form(True),
) -> dict[str, Any]:
    max_bytes = max(settings.max_excel_upload_mb, 1) * 1024 * 1024
    try:
        content = await file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise HTTPException(413, f"Excel 文件不能超过 {settings.max_excel_upload_mb} MB")
        rows, sheet_name = await run_in_threadpool(read_excel_rows, content, file.filename or "")
        result = await run_in_threadpool(
            orchestrator.analyze,
            project_name=project_name.strip() or "默认分析项目",
            request=request.strip(),
            data=rows,
            source_name=f"{file.filename} / {sheet_name}",
            product_mode=product_mode,
            privacy_consent=privacy_consent,
        )
        return {
            "upload": {"filename": file.filename, "sheet_name": sheet_name, "source_rows": len(rows)},
            **result,
        }
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.exception("excel analysis failed")
        raise HTTPException(500, str(exc)) from exc
    finally:
        await file.close()


@app.post("/api/agents/{agent_name}/run")
def run_agent(agent_name: str, body: AgentRunRequest) -> dict[str, Any]:
    try: return {"agent": agent_name, "result": orchestrator.run_agent(agent_name, body.payload, body.context)}
    except KeyError as exc: raise HTTPException(404, str(exc)) from exc
    except (ValueError, FileNotFoundError, PermissionError) as exc: raise HTTPException(422, str(exc)) from exc


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    result = memory.get_run(run_id)
    if not result: raise HTTPException(404, "run not found")
    return result


@app.get("/api/runs/{run_id}/pdf")
def run_pdf(run_id: str) -> FileResponse:
    if not memory.get_run(run_id):
        raise HTTPException(404, "run not found")
    path = (settings.storage_path / "reports" / f"{run_id}-report.pdf").resolve()
    reports_dir = (settings.storage_path / "reports").resolve()
    if reports_dir not in path.parents or not path.is_file():
        raise HTTPException(404, "PDF report not found")
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{run_id}-report.pdf"'})


@app.get("/api/runs/{run_id}/pdf/download")
def download_run_pdf(run_id: str) -> FileResponse:
    if not memory.get_run(run_id):
        raise HTTPException(404, "run not found")
    path = (settings.storage_path / "reports" / f"{run_id}-report.pdf").resolve()
    reports_dir = (settings.storage_path / "reports").resolve()
    if reports_dir not in path.parents or not path.is_file():
        raise HTTPException(404, "PDF report not found")
    return FileResponse(path, media_type="application/pdf", filename=f"{run_id}-销售分析报告.pdf")


@app.get("/api/runs/{run_id}/chart/{chart_name}")
def run_chart(run_id: str, chart_name: str) -> FileResponse:
    if chart_name not in {"bar", "line"} or not memory.get_run(run_id):
        raise HTTPException(404, "chart not found")
    path = (settings.storage_path / "charts" / f"{run_id}-{chart_name}.svg").resolve()
    charts_dir = (settings.storage_path / "charts").resolve()
    if charts_dir not in path.parents or not path.is_file():
        raise HTTPException(404, "chart not found")
    return FileResponse(path, media_type="image/svg+xml")


@app.get("/api/logs")
def logs(tail: int = Query(default=200, ge=1, le=2000)) -> dict[str, Any]:
    path = (settings.storage_path / "logs" / "app.log").resolve()
    if not path.is_file():
        return {"lines": [], "path": str(path)}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"lines": lines[-tail:], "path": str(path)}


@app.get("/api/runs/{run_id}/memory")
def run_memory(run_id: str) -> dict[str, Any]:
    if not memory.get_run(run_id): raise HTTPException(404, "run not found")
    return memory.run_memory(run_id)


@app.get("/api/runs/{run_id}/trace")
def run_trace(run_id: str) -> dict[str, Any]:
    if not memory.get_run(run_id): raise HTTPException(404, "run not found")
    return {"run_id": run_id, "trace": orchestrator.trace(run_id)}


@app.post("/api/runs/{run_id}/rerun")
def rerun(run_id: str, body: RerunRequest) -> dict[str, Any]:
    try:
        return orchestrator.rerun(run_id, from_step=body.from_step)
    except KeyError as exc: raise HTTPException(404, "run not found") from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    except Exception as exc: logger.exception("rerun failed"); raise HTTPException(500, str(exc)) from exc


@app.get("/api/memory/search")
def search_memory(query: str = Query(min_length=1), project_id: str | None = None, scope: str = "project", top_k: int = Query(default=5, ge=1, le=50)) -> dict[str, Any]:
    if scope == "project" and not project_id: raise HTTPException(422, "project scope requires project_id")
    try: return {"query": query, "scope": scope, "results": memory.search_conversations(query, project_id=project_id, scope=scope, top_k=top_k)}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@app.post("/api/conversations")
def conversation(body: ConversationRequest) -> dict[str, Any]:
    return {"id": memory.record_conversation(project_id=body.project_id, user_message=body.user_message, assistant_message=body.assistant_message, metadata=body.metadata)}


@app.post("/api/retention/cleanup")
def cleanup() -> dict[str, Any]:
    manager = getattr(app.state, "retention", RetentionManager(settings.storage_path, settings.retention_days)); removed = manager.cleanup()
    return {"removed_count": len(removed), "removed": removed, "retention_days": settings.retention_days}
