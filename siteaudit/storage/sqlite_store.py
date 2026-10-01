from __future__ import annotations

from pathlib import Path
from typing import Any

from ..admin import db


class SQLiteStorage:
    """Adapter da persistência atual em SQLite."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = path
        db.initialize(path)

    def create_run(self, config: dict[str, Any]) -> str:
        return db.create_run(config, self.path)

    def save_leads(self, run_id: str, leads: list[Any]) -> int:
        return db.save_leads(run_id, leads, self.path)

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        return db.list_runs(limit=limit, path=self.path)

    def list_leads(self, *, run_id: str | None = None, search: str = "", stage: str = "",
                   limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
        return db.list_leads(run_id=run_id, search=search, stage=stage, limit=limit, offset=offset, path=self.path)

    def run_exists(self, run_id: str) -> bool:
        return db.run_exists(run_id, path=self.path)
