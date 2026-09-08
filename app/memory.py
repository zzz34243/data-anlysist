from __future__ import annotations

import hashlib
import math
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from .db import Database, dumps, loads, utc_now


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower())


def _fingerprint(title: str, content: Any) -> str:
    return hashlib.sha256(f"{title}|{dumps(content)}".encode()).hexdigest()


class MemoryStore:
    def __init__(self, db: Database, storage_path: Path):
        self.db, self.storage_path = db, Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        for name in ("runs", "history", "charts", "reports", "logs"):
            (self.storage_path / name).mkdir(exist_ok=True)

    def create_project(self, name: str, description: str = "") -> str:
        project_id = str(uuid.uuid4())
        with self.db.connection() as conn:
            conn.execute("INSERT INTO projects VALUES (?, ?, ?, ?)", (project_id, name, description, utc_now()))
        return project_id

    def get_or_create_project(self, name: str) -> str:
        with self.db.connection() as conn:
            row = conn.execute("SELECT id FROM projects WHERE name=? ORDER BY created_at LIMIT 1", (name,)).fetchone()
        return row["id"] if row else self.create_project(name)

    def create_run(self, project_id: str, request: dict[str, Any]) -> str:
        run_id = str(uuid.uuid4())
        with self.db.connection() as conn:
            conn.execute("INSERT INTO runs(id,project_id,request_json,status,started_at) VALUES (?,?,?,?,?)", (run_id, project_id, dumps(request), "running", utc_now()))
        return run_id

    def finish_run(self, run_id: str, status: str, error: str | None = None) -> None:
        with self.db.connection() as conn:
            conn.execute("UPDATE runs SET status=?,finished_at=?,error=? WHERE id=?", (status, utc_now(), error, run_id))

    def save_snapshot(self, run_id: str, snapshot: dict[str, Any]) -> str:
        path = self.storage_path / "runs" / f"{run_id}.json"
        path.write_text(dumps(snapshot), encoding="utf-8")
        with self.db.connection() as conn:
            conn.execute("UPDATE runs SET snapshot_path=? WHERE id=?", (str(path), run_id))
        return str(path)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.db.connection() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["request"] = loads(result.pop("request_json"), {})
        return result

    def list_projects(self) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM projects ORDER BY created_at DESC")]

    def create_plan(self, *, actor: str, project_id: str, run_id: str, objective: str, optimized_prompt: str, steps: list[dict[str, Any]], selection: dict[str, Any]) -> str:
        if actor != "orchestrator":
            raise PermissionError("Plan 只有主控可写")
        plan_id, now = str(uuid.uuid4()), utc_now()
        with self.db.connection() as conn:
            conn.execute("INSERT INTO plans VALUES (?,?,?,?,?,?,?,?,?,?,?)", (plan_id, project_id, run_id, "分析计划", objective, optimized_prompt, "active", dumps(steps), dumps(selection), now, now))
        return plan_id

    def complete_plan(self, plan_id: str, status: str = "completed") -> None:
        with self.db.connection() as conn:
            conn.execute("UPDATE plans SET status=?,updated_at=? WHERE id=?", (status, utc_now(), plan_id))

    def add_todo(self, *, actor: str, run_id: str, agent_name: str, step_order: int, title: str, allowed_inputs: list[str]) -> str:
        if actor not in {"orchestrator", agent_name}:
            raise PermissionError("智能体只能接收或维护自己的 Todo")
        todo_id, now = str(uuid.uuid4()), utc_now()
        with self.db.connection() as conn:
            conn.execute("INSERT INTO todos VALUES (?,?,?,?,?,?,?,?,?,?)", (todo_id, run_id, agent_name, step_order, title, dumps(allowed_inputs), "pending", None, now, now))
        return todo_id

    def update_todo(self, *, actor: str, todo_id: str, status: str, result: Any = None) -> None:
        with self.db.connection() as conn:
            row = conn.execute("SELECT agent_name FROM todos WHERE id=?", (todo_id,)).fetchone()
            if not row:
                raise KeyError(todo_id)
            if actor not in {"orchestrator", row["agent_name"]}:
                raise PermissionError("智能体只能更新自己的 Todo")
            conn.execute("UPDATE todos SET status=?,result_json=?,updated_at=? WHERE id=?", (status, dumps(result) if result is not None else None, utc_now(), todo_id))

    def add_finding(self, *, actor: str, run_id: str, agent_name: str, kind: str, title: str, content: Any) -> tuple[str, bool]:
        if actor not in {agent_name, "orchestrator"}:
            raise PermissionError("Finding 只能由产生它的智能体追加")
        fp = _fingerprint(title, content)
        with self.db.connection() as conn:
            old = conn.execute("SELECT id FROM findings WHERE run_id=? AND fingerprint=?", (run_id, fp)).fetchone()
            if old:
                return old["id"], True
            finding_id = str(uuid.uuid4())
            conn.execute("INSERT INTO findings(id,run_id,agent_name,kind,title,content_json,fingerprint,created_at) VALUES (?,?,?,?,?,?,?,?)", (finding_id, run_id, agent_name, kind, title, dumps(content), fp, utc_now()))
            return finding_id, False

    def validate_finding(self, *, actor: str, finding_id: str, status: str, duplicate_of: str | None = None) -> None:
        if actor != "validator":
            raise PermissionError("只有独立验证智能体可以改变 Finding 状态")
        if status not in {"pending", "verified", "rejected", "duplicate"}:
            raise ValueError("invalid validation status")
        with self.db.connection() as conn:
            conn.execute("UPDATE findings SET validation_status=?,duplicate_of=? WHERE id=?", (status, duplicate_of, finding_id))

    def add_artifact(self, *, run_id: str, artifact_type: str, path: str, description: str = "") -> str:
        artifact_id = str(uuid.uuid4())
        with self.db.connection() as conn:
            conn.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?)", (artifact_id, run_id, artifact_type, path, description, utc_now()))
        return artifact_id

    def save_dataset(self, *, project_id: str, run_id: str, source_name: str, schema: Any, rows: list[dict[str, Any]]) -> str:
        dataset_id = str(uuid.uuid4())
        with self.db.connection() as conn:
            conn.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)", (dataset_id, project_id, run_id, source_name, dumps(schema), len(rows), dumps(rows), utc_now()))
        return dataset_id

    def dataset_for_run(self, run_id: str) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            row = conn.execute("SELECT rows_json FROM datasets WHERE run_id=? ORDER BY created_at DESC LIMIT 1", (run_id,)).fetchone()
        return loads(row["rows_json"], []) if row else []

    def add_trace(self, *, run_id: str, span_name: str, agent_name: str, step_order: int, status: str, attempt: int, input_data: Any, output_data: Any = None, error: str | None = None, started_at: str | None = None) -> str:
        trace_id = str(uuid.uuid4())
        with self.db.connection() as conn:
            conn.execute("INSERT INTO traces VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (trace_id, run_id, span_name, agent_name, step_order, status, attempt, error, dumps(input_data), dumps(output_data) if output_data is not None else None, started_at or utc_now(), utc_now()))
        return trace_id

    def record_conversation(self, *, project_id: str | None, user_message: str, assistant_message: str, metadata: dict[str, Any] | None = None) -> str:
        conversation_id, now = str(uuid.uuid4()), utc_now()
        path = self.storage_path / "history" / f"{conversation_id}.json"
        record = {"id": conversation_id, "project_id": project_id, "user_message": user_message, "assistant_message": assistant_message, "metadata": metadata or {}, "created_at": now}
        path.write_text(dumps(record), encoding="utf-8")
        with self.db.connection() as conn:
            conn.execute("INSERT INTO conversations VALUES (?,?,?,?,?,?,?,?)", (conversation_id, project_id, "project", user_message, assistant_message, dumps(metadata or {}), now, str(path)))
        return conversation_id

    def search_conversations(self, query: str, *, project_id: str | None, scope: str, top_k: int = 5) -> list[dict[str, Any]]:
        if scope not in {"project", "cross_project"}:
            raise ValueError("scope must be project or cross_project")
        if scope == "project" and not project_id:
            return []
        with self.db.connection() as conn:
            rows = conn.execute("SELECT c.*,p.name project_name FROM conversations c LEFT JOIN projects p ON p.id=c.project_id " + ("WHERE c.project_id=? " if scope == "project" else "") + "ORDER BY c.created_at DESC", (project_id,) if scope == "project" else ()).fetchall()
        q, qnorm = Counter(_tokens(query)), math.sqrt(sum(v*v for v in Counter(_tokens(query)).values())) or 1
        scored = []
        for row in rows:
            counts = Counter(_tokens(f"{row['user_message']} {row['assistant_message']}"))
            norm = math.sqrt(sum(v*v for v in counts.values())) or 1
            score = sum(q[t]*counts[t] for t in q) / (qnorm*norm)
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda x: (x[0], x[1]["created_at"]), reverse=True)
        return [{"score": round(score, 4), "id": row["id"], "project_id": row["project_id"], "project_name": row["project_name"], "user_message": row["user_message"], "assistant_message": row["assistant_message"], "created_at": row["created_at"]} for score, row in scored[:top_k]]

    def run_memory(self, run_id: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            plan = conn.execute("SELECT * FROM plans WHERE run_id=? ORDER BY created_at DESC LIMIT 1", (run_id,)).fetchone()
            todos = conn.execute("SELECT * FROM todos WHERE run_id=? ORDER BY step_order", (run_id,)).fetchall()
            findings = conn.execute("SELECT * FROM findings WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()
            artifacts = conn.execute("SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()
            traces = conn.execute("SELECT * FROM traces WHERE run_id=? ORDER BY step_order,attempt", (run_id,)).fetchall()
        p = dict(plan) if plan else None
        if p:
            p["steps"], p["selection"] = loads(p.pop("steps_json"), []), loads(p.pop("selection_json"), {})
        def todo(row: Any) -> dict[str, Any]:
            item = dict(row); item["allowed_inputs"] = loads(item.pop("allowed_inputs_json"), []); item["result"] = loads(item.pop("result_json"), None); return item
        def finding(row: Any) -> dict[str, Any]:
            item = dict(row); item["content"] = loads(item.pop("content_json"), {}); return item
        return {"plan": p, "todos": [todo(r) for r in todos], "findings": [finding(r) for r in findings], "artifacts": [dict(r) for r in artifacts], "traces": [dict(r) for r in traces]}
