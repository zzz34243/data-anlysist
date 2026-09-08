from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .config import settings
from .db import Database
from .memory import MemoryStore
from .orchestrator import Orchestrator
from .llm import build_llm_provider
from .retention import RetentionManager

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
