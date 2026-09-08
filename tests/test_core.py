import os
import tempfile
import time
import unittest
from pathlib import Path

from app.db import Database
from app.memory import MemoryStore
from app.orchestrator import Orchestrator
from app.retention import RetentionManager
from app.selection import devote, filter_data, resolve_selection


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        for name in ("runs", "history", "charts", "reports", "logs"): (self.root / name).mkdir()
        self.memory = MemoryStore(Database(self.root / "app.db"), self.root)
        self.orchestrator = Orchestrator(self.memory, self.root, max_retries=1)

    def test_prompt_filter_and_devote(self):
        optimized = self.orchestrator.optimize(request="模糊分析", product_mode="online")
        self.assertIn("线性趋势图", optimized["optimized_prompt"])
        self.assertEqual(len(devote()), 7)
        result = filter_data([{"date":"2026-01-01"}] * 10, selection=resolve_selection(), filters={"limit": 3}, max_rows=5)
        self.assertEqual(len(result["rows"]), 3); self.assertTrue(result["truncated"])

    def test_pipeline_and_trace(self):
        result = self.orchestrator.analyze(project_name="测试", request="分析销售", data=[{"date":"2026/01/01","product":"A","channel":"线上","amount":"100"},{"date":"2026/01/02","product":"A","channel":"线上","amount":"150"}])
        self.assertEqual(result["status"], "completed"); self.assertTrue(result["report_validation"]["valid"]); self.assertEqual(set(result["charts"]["charts"]), {"bar", "line"})
        self.assertEqual([x["step_order"] for x in self.orchestrator.trace(result["run_id"])], list(range(1, 8)))
        self.assertEqual(len(self.memory.run_memory(result["run_id"])["findings"]), 7)
        replay = self.orchestrator.rerun(result["run_id"], from_step=4)
        self.assertEqual(replay["replay"]["source_run_id"], result["run_id"])

    def test_permissions_privacy_and_retention(self):
        project = self.memory.create_project("权限"); run = self.memory.create_run(project, {})
        with self.assertRaises(PermissionError): self.memory.create_plan(actor="insights", project_id=project, run_id=run, objective="x", optimized_prompt="x", steps=[], selection={})
        with self.assertRaises(PermissionError): self.orchestrator.analyze(project_name="隐私", request="x", data=[{"email":"x","amount":1}], privacy_consent=False)
        old = self.root / "runs" / "old.json"; old.write_text("{}"); stamp = time.time() - 8 * 86400; os.utime(old, (stamp, stamp)); self.assertIn(str(old), RetentionManager(self.root, 7).cleanup())


if __name__ == "__main__": unittest.main()
