from __future__ import annotations

from typing import Any, Protocol


class Storage(Protocol):
    """Contrato mínimo da camada de persistência."""

    def create_run(self, config: dict[str, Any]) -> str: ...

    def save_leads(self, run_id: str, leads: list[Any]) -> int: ...

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]: ...

    def list_leads(self, *, run_id: str | None = None, search: str = "", stage: str = "",
                   limit: int = 500, offset: int = 0) -> list[dict[str, Any]]: ...
