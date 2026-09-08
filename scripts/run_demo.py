from pathlib import Path
import sys
import logging
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.db import Database
from app.memory import MemoryStore
from app.orchestrator import Orchestrator
from app.llm import build_llm_provider

if __name__ == "__main__":
    settings.ensure_directories()
    logging.basicConfig(level=logging.INFO, filename=settings.storage_path / "logs" / "demo.log", encoding="utf-8", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    memory = MemoryStore(Database(settings.database_path), settings.storage_path)
    provider = build_llm_provider(settings)
    result = Orchestrator(memory, settings.storage_path, max_filter_rows=settings.max_filter_rows, max_retries=settings.max_retries, llm=provider).analyze(project_name="示例销售项目", request="分析产品和渠道趋势，制定下一周期营销策略", csv_path=str(Path(__file__).resolve().parents[1] / "data" / "sample_sales.csv"))
    print(f"run_id={result['run_id']}\nreport={result['report']['path']}\ncharts={result['charts']['charts']}")
