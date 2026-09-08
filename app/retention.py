from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path


class RetentionManager:
    def __init__(self, storage_path: Path, retention_days: int = 7):
        self.storage_path, self.retention_days = Path(storage_path), max(1, int(retention_days))
        self.stop_event, self.thread = threading.Event(), None

    def cleanup(self) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        removed = []
        for folder in ("runs", "history", "charts", "reports", "logs"):
            root = self.storage_path / folder
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file() and datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
                    try:
                        path.unlink(); removed.append(str(path))
                    except OSError:
                        pass
        return removed

    def start(self, interval_seconds: int = 3600) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        def loop() -> None:
            while not self.stop_event.wait(max(60, interval_seconds)):
                self.cleanup()
        self.thread = threading.Thread(target=loop, daemon=True, name="retention-cleaner"); self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

