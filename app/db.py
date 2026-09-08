from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT DEFAULT '', created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), request_json TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, error TEXT, snapshot_path TEXT);
            CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), run_id TEXT NOT NULL REFERENCES runs(id), source_name TEXT NOT NULL, schema_json TEXT NOT NULL, row_count INTEGER NOT NULL, rows_json TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), run_id TEXT NOT NULL REFERENCES runs(id), title TEXT NOT NULL, objective TEXT NOT NULL, optimized_prompt TEXT NOT NULL, status TEXT NOT NULL, steps_json TEXT NOT NULL, selection_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS todos (id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), agent_name TEXT NOT NULL, step_order INTEGER NOT NULL, title TEXT NOT NULL, allowed_inputs_json TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS findings (id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), agent_name TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, content_json TEXT NOT NULL, fingerprint TEXT NOT NULL, validation_status TEXT NOT NULL DEFAULT 'pending', duplicate_of TEXT REFERENCES findings(id), created_at TEXT NOT NULL, UNIQUE(run_id, fingerprint));
            CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), artifact_type TEXT NOT NULL, path TEXT NOT NULL, description TEXT DEFAULT '', created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id), scope TEXT NOT NULL DEFAULT 'project', user_message TEXT NOT NULL, assistant_message TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, snapshot_path TEXT);
            CREATE TABLE IF NOT EXISTS traces (id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), span_name TEXT NOT NULL, agent_name TEXT NOT NULL, step_order INTEGER NOT NULL, status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 1, error TEXT, input_json TEXT NOT NULL, output_json TEXT, started_at TEXT NOT NULL, finished_at TEXT);
            CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, started_at);
            CREATE INDEX IF NOT EXISTS idx_trace_run ON traces(run_id, step_order, attempt);
            CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project_id, created_at);
            """)

