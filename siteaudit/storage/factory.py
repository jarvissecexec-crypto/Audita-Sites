from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from .base import Storage
from .sqlite_store import SQLiteStorage
from .supabase_store import SupabaseStorage

StorageMode = Literal["sqlite", "supabase", "dual"]


class DualStorage:
    """Escreve em SQLite + Supabase e lê do primário (SQLite por padrão)."""

    def __init__(self, primary: Storage, secondary: Storage) -> None:
        self.primary = primary
        self.secondary = secondary

    def create_run(self, config: dict[str, Any]) -> str:
        run_id = self.primary.create_run(config)
        # O ID do secundário pode divergir, então apenas espelhamos o conteúdo.
        self.secondary.create_run(config)
        return run_id

    def save_leads(self, run_id: str, leads: list[Any]) -> int:
        saved = self.primary.save_leads(run_id, leads)
        try:
            self.secondary.save_leads(run_id, leads)
        except Exception:
            # Estratégia resiliente: não impedir o fluxo local caso a nuvem falhe.
            pass
        return saved

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.primary.list_runs(limit=limit)

    def list_leads(
        self,
        *,
        run_id: str | None = None,
        search: str = "",
        stage: str = "",
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self.primary.list_leads(run_id=run_id, search=search, stage=stage, limit=limit, offset=offset)


def resolve_storage_mode(explicit_mode: str | None = None) -> StorageMode:
    raw = (explicit_mode or os.getenv("SITEAUDIT_STORAGE") or "sqlite").strip().lower()
    if raw not in {"sqlite", "supabase", "dual"}:
        return "sqlite"
    return raw  # type: ignore[return-value]


def build_runtime_storage(*, mode: str | None = None, sqlite_path: str | Path | None = None) -> Storage:
    selected = resolve_storage_mode(mode)
    if selected == "supabase":
        return SupabaseStorage()
    if selected == "dual":
        return DualStorage(SQLiteStorage(sqlite_path), SupabaseStorage())
    return SQLiteStorage(sqlite_path)
