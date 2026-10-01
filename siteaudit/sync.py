from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import Lead
from .storage.sqlite_store import SQLiteStorage
from .storage.supabase_store import SupabaseStorage


def build_sync_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="siteaudit sync", description="Sincroniza histórico SQLite -> Supabase")
    p.add_argument("--from-sqlite", dest="sqlite_path", default="data/siteaudit.sqlite3")
    p.add_argument("--limit-runs", type=int, default=50)
    return p


def sync_sqlite_to_supabase(sqlite_path: str, limit_runs: int = 50) -> dict:
    src = SQLiteStorage(Path(sqlite_path))
    dst = SupabaseStorage()

    runs = src.list_runs(limit=limit_runs)
    synced_runs = 0
    synced_leads = 0
    skipped_runs = 0
    failed_runs = 0
    details: list[dict] = []

    for run in runs:
        run_id = run["id"]
        try:
            if dst.run_exists(run_id):
                skipped_runs += 1
                details.append({"run_id": run_id, "status": "skipped_exists", "leads": 0})
                continue

            cfg = run.get("config") or {}
            new_run_id = dst.create_run_with_id(run_id, cfg)
            leads_rows = src.list_leads(run_id=run_id, limit=1000)
            leads: list[Lead] = []
            for row in leads_rows:
                lead = Lead(
                    name=row.get("name", ""),
                    website=row.get("website", ""),
                    phone=row.get("phone", ""),
                    address=row.get("address", ""),
                    city=row.get("city", ""),
                    state=row.get("state", ""),
                    category=row.get("category", ""),
                    rating=row.get("rating"),
                    reviews=row.get("reviews"),
                    source=row.get("source", ""),
                    query=row.get("query", ""),
                    maps_url=row.get("maps_url", ""),
                    has_website=bool(row.get("has_website")),
                    status="ok" if row.get("site_status") == "audit_ok" else "error" if row.get("site_status") == "audit_error" else "pending",
                    score=row.get("score"),
                    error=row.get("error", ""),
                    audit=row.get("audit") if isinstance(row.get("audit"), dict) else None,
                )
                leads.append(lead)
            saved = dst.save_leads(new_run_id, leads)
            synced_leads += saved
            synced_runs += 1
            details.append({"run_id": run_id, "status": "synced", "leads": saved})
        except Exception as exc:  # noqa: BLE001
            failed_runs += 1
            details.append({"run_id": run_id, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})

    return {
        "runs": synced_runs,
        "leads": synced_leads,
        "skipped_runs": skipped_runs,
        "failed_runs": failed_runs,
        "details": details,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_sync_parser().parse_args(argv)
    result = sync_sqlite_to_supabase(args.sqlite_path, args.limit_runs)
    print(json.dumps(result, ensure_ascii=False))
    return 0
