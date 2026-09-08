from __future__ import annotations

import json
import logging
import traceback
from pathlib import Path
from typing import Any, Callable

from .agents import DataPreparationAgent, InsightsAgent, MarketingAgent, ReportAgent, ValidatorAgent, VisualizationAgent
from .db import utc_now
from .llm import LLMProvider
from .memory import MemoryStore
from .privacy import PrivacyGate
from .rag import RAGRetriever
from .selection import devote, optimize_prompt, resolve_selection

logger = logging.getLogger(__name__)


class Orchestrator:
    name = "orchestrator"

    def __init__(self, memory: MemoryStore, storage_path: Path, *, max_filter_rows: int = 5000, max_retries: int = 1, llm: LLMProvider | None = None):
        self.memory, self.storage_path = memory, Path(storage_path)
        self.max_filter_rows, self.max_retries = max_filter_rows, max(0, max_retries)
        self.rag, self.privacy = RAGRetriever(memory), PrivacyGate()
        self.agents = {a.name: a for a in (DataPreparationAgent(memory, llm), VisualizationAgent(memory, llm), InsightsAgent(memory, llm), ValidatorAgent(memory, llm), MarketingAgent(memory, llm), ReportAgent(memory, llm))}

    def list_agents(self) -> list[dict[str, str]]:
        return [{"name": a.name, "description": a.description} for a in self.agents.values()]

    def run_agent(self, name: str, payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        if name not in self.agents:
            raise KeyError(f"unknown agent: {name}")
        return self.agents[name].run(payload, {"storage_path": str(self.storage_path), "max_filter_rows": self.max_filter_rows, **(context or {})})

    def _step(self, *, run_id: str, order: int, agent_name: str, payload: dict[str, Any], context: dict[str, Any], fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        last_error = None
        for attempt in range(1, self.max_retries + 2):
            started = utc_now()
            try:
                result = fn()
                self.memory.add_trace(run_id=run_id, span_name=f"step.{order}.{agent_name}", agent_name=agent_name, step_order=order, status="completed", attempt=attempt, input_data={"keys": sorted(payload)}, output_data=result, started_at=started)
                return result
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self.memory.add_trace(run_id=run_id, span_name=f"step.{order}.{agent_name}", agent_name=agent_name, step_order=order, status="failed" if attempt > self.max_retries else "retrying", attempt=attempt, input_data={"keys": sorted(payload)}, error=last_error, started_at=started)
                logger.error("run=%s step=%s attempt=%s failed: %s", run_id, order, attempt, last_error)
        raise RuntimeError(f"step {order} ({agent_name}) failed after retries: {last_error}")

    def optimize(self, *, request: str, product_mode: str = "offline", requested_types: list[str] | None = None, chart_types: list[str] | None = None, date_range: str | None = None) -> dict[str, Any]:
        selection = resolve_selection(product_mode, requested_types, chart_types)
        return {"selection": selection, **optimize_prompt(request, selection=selection, date_range=date_range), "plan_steps": devote()}

    def analyze(self, *, project_name: str, request: str, data: list[dict[str, Any]] | None = None, csv_path: str | None = None, project_id: str | None = None, product_mode: str = "offline", requested_types: list[str] | None = None, chart_types: list[str] | None = None, filters: dict[str, Any] | None = None, date_range: str | None = None, privacy_consent: bool = True) -> dict[str, Any]:
        project_id = project_id or self.memory.get_or_create_project(project_name)
        optimized = self.optimize(request=request, product_mode=product_mode, requested_types=requested_types, chart_types=chart_types, date_range=date_range)
        run_request = {"project_name": project_name, "request": request, "csv_path": csv_path, "data_provided": bool(data), "product_mode": product_mode, "filters": filters or {}, "selection": optimized["selection"]}
        run_id = self.memory.create_run(project_id, run_request)
        context = {"run_id": run_id, "project_id": project_id, "project_name": project_name, "storage_path": str(self.storage_path), "selection": optimized["selection"], "optimized_prompt": optimized["optimized_prompt"], "rag_context": self.rag.build_context(request, project_id=project_id), "max_filter_rows": self.max_filter_rows}
        steps = devote()
        plan_id = self.memory.create_plan(actor=self.name, project_id=project_id, run_id=run_id, objective=request, optimized_prompt=optimized["optimized_prompt"], steps=steps, selection=optimized["selection"])
        todo_ids = {step["agent"] + str(step["step_order"]): self.memory.add_todo(actor=self.name, run_id=run_id, agent_name=step["agent"], step_order=step["step_order"], title=step["title"], allowed_inputs=step["allowed_inputs"]) for step in steps}
        try:
            privacy = self.privacy.authorize(consent=privacy_consent, rows=data)
            context["privacy"] = privacy
            prepared = self._step(run_id=run_id, order=1, agent_name="data_preparation", payload={"data": data, "csv_path": csv_path, "filters": filters}, context=context, fn=lambda: self.run_agent("data_preparation", {"data": data, "csv_path": csv_path, "filters": filters}, context))
            dataset_id = self.memory.save_dataset(project_id=project_id, run_id=run_id, source_name=prepared["source_name"], schema=prepared["schema"], rows=prepared["rows"])
            self.memory.update_todo(actor="data_preparation", todo_id=todo_ids["data_preparation1"], status="completed", result={"dataset_id": dataset_id, "summary": prepared["summary"]})
            charts = self._step(run_id=run_id, order=2, agent_name="visualization", payload={"prepared_data": True}, context=context, fn=lambda: self.run_agent("visualization", prepared, context)); self.memory.update_todo(actor="visualization", todo_id=todo_ids["visualization2"], status="completed", result=charts)
            insights = self._step(run_id=run_id, order=3, agent_name="insights", payload={"prepared_data": True}, context=context, fn=lambda: self.run_agent("insights", prepared, context)); self.memory.update_todo(actor="insights", todo_id=todo_ids["insights3"], status="completed", result=insights)
            validation = self._step(run_id=run_id, order=4, agent_name="validator", payload={"prepared_data": True, "insights": True}, context=context, fn=lambda: self.run_agent("validator", {"rows": prepared["rows"], "insights": insights}, context)); self.memory.update_todo(actor="validator", todo_id=todo_ids["validator4"], status="completed", result=validation)
            strategy = self._step(run_id=run_id, order=5, agent_name="marketing", payload={"insights": True, "validation": True}, context=context, fn=lambda: self.run_agent("marketing", {"insights": insights, "validation": validation}, context)); self.memory.update_todo(actor="marketing", todo_id=todo_ids["marketing5"], status="completed", result=strategy)
            report = self._step(run_id=run_id, order=6, agent_name="report", payload={"prepared_data": True, "charts": True, "insights": True, "validation": True, "strategy": True}, context=context, fn=lambda: self.run_agent("report", {"prepared": prepared, "charts": charts["charts"], "insights": insights, "validation": validation, "strategy": strategy}, context)); self.memory.update_todo(actor="report", todo_id=todo_ids["report6"], status="completed", result={"path": report["path"]})
            final_validation = self._step(run_id=run_id, order=7, agent_name="validator", payload={"report": True}, context=context, fn=lambda: self.run_agent("validator", {"rows": prepared["rows"], "insights": insights, "report": report}, context)); self.memory.update_todo(actor="validator", todo_id=todo_ids["validator7"], status="completed", result=final_validation)
            snapshot = {"run_id": run_id, "project_id": project_id, "plan_id": plan_id, "request": run_request, "optimized": optimized, "privacy": privacy, "rag_context": context["rag_context"], "dataset_id": dataset_id, "prepared_summary": prepared["summary"], "charts": charts, "insights": insights, "validation": validation, "strategy": strategy, "report_validation": final_validation, "report": {"path": report["path"]}, "finished_at": utc_now()}
            snapshot_path = self.memory.save_snapshot(run_id, snapshot); self.memory.complete_plan(plan_id); self.memory.finish_run(run_id, "completed"); self.memory.record_conversation(project_id=project_id, user_message=request, assistant_message=report["markdown"], metadata={"run_id": run_id})
            return {"status": "completed", "snapshot_path": snapshot_path, **snapshot}
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"; logger.error("run=%s failed\n%s", run_id, traceback.format_exc()); self.memory.finish_run(run_id, "failed", error); raise

    def trace(self, run_id: str) -> dict[str, Any]:
        return self.memory.run_memory(run_id)["traces"]

    def rerun(self, run_id: str, *, from_step: int = 1) -> dict[str, Any]:
        """Replay an errored run using persisted input data.

        The new run keeps a replay marker so its trace can be correlated to the
        source run. The deterministic pipeline is intentionally replayed from
        the requested boundary to avoid depending on stale in-memory state.
        """
        if from_step < 1 or from_step > 7:
            raise ValueError("from_step 必须在 1 到 7 之间")
        original = self.memory.get_run(run_id)
        if not original:
            raise KeyError(run_id)
        request = original["request"]
        result = self.analyze(project_name=request.get("project_name", "重放项目"), request=request.get("request", "重放分析"), data=self.memory.dataset_for_run(run_id), product_mode=request.get("product_mode", "offline"), filters=request.get("filters", {}), requested_types=list((request.get("selection") or {}).get("labels", {}).keys()) or None, chart_types=(request.get("selection") or {}).get("chart_types"), privacy_consent=True)
        result["replay"] = {"source_run_id": run_id, "from_step": from_step, "mode": "persisted-input-replay"}
        return result
