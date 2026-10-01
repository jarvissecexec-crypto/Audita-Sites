"""Camada de persistência desacoplada (SQLite/Supabase)."""

from .base import Storage
from .factory import DualStorage, build_runtime_storage, resolve_storage_mode
from .sqlite_store import SQLiteStorage
from .supabase_store import SupabaseStorage

__all__ = [
    "Storage",
    "SQLiteStorage",
    "SupabaseStorage",
    "DualStorage",
    "build_runtime_storage",
    "resolve_storage_mode",
]
