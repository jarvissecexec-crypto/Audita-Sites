"""Camada de persistência desacoplada (SQLite/Supabase)."""

from .base import Storage
from .sqlite_store import SQLiteStorage
from .supabase_store import SupabaseStorage

__all__ = ["Storage", "SQLiteStorage", "SupabaseStorage"]
