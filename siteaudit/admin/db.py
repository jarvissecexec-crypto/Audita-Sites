"""Persistência SQLite do painel administrativo.

O banco guarda os leads e o estado comercial. Dados de provedores permanecem
associados às execuções para que a origem dos resultados não se perca.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

OUTREACH_STAGES = {
    "new", "review", "qualified", "contacted", "replied", "won", "lost", "do_not_contact",
}


def database_path() -> Path:
    configured = os.getenv("SITEAUDIT_DB", "data/siteaudit.sqlite3")
    return Path(configured).expanduser().resolve()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    target = Path(path) if path else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize(path: str | Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                config_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                progress TEXT NOT NULL DEFAULT '',
                leads_found INTEGER NOT NULL DEFAULT 0,
                errors_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                dedupe_key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL DEFAULT '',
                website TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                rating REAL,
                reviews INTEGER,
                source TEXT NOT NULL DEFAULT '',
                query TEXT NOT NULL DEFAULT '',
                maps_url TEXT NOT NULL DEFAULT '',
                has_website INTEGER NOT NULL DEFAULT 0,
                site_status TEXT NOT NULL DEFAULT 'not_checked',
                outreach_status TEXT NOT NULL DEFAULT 'new',
                score INTEGER,
                error TEXT NOT NULL DEFAULT '',
                audit_json TEXT,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS run_leads (
                run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                source TEXT NOT NULL DEFAULT '',
                query TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (run_id, lead_id)
            );

            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
                provider TEXT NOT NULL,
                operation TEXT NOT NULL,
                units INTEGER NOT NULL DEFAULT 1,
                estimated_cost_usd REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_leads_outreach ON leads(outreach_status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_leads_site_status ON leads(site_status);
            CREATE INDEX IF NOT EXISTS idx_run_leads_lead ON run_leads(lead_id);
            """
        )
        # A process restart must not leave an execution looking active forever.
        conn.execute(
            "UPDATE runs SET status='interrupted', progress='Processo reiniciado' "
            "WHERE status IN ('queued','running')"
        )


def run_exists(run_id: str, path: str | Path | None = None) -> bool:
    """Verifica se um run existe no banco."""
    with connect(path) as conn:
        row = conn.execute("SELECT 1 FROM runs WHERE id=? LIMIT 1", (run_id,)).fetchone()
        return bool(row)


def get_lead(lead_id: str, path: str | Path | None = None) -> dict[str, Any] | None:
    """Retorna um lead específico pelo ID."""
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["has_website"] = bool(item["has_website"])
        item["audit"] = json.loads(item.pop("audit_json")) if item.get("audit_json") else None
        item["runs"] = [r[0] for r in conn.execute(
            "SELECT run_id FROM run_leads WHERE lead_id=? ORDER BY run_id", (lead_id,)
        ).fetchall()]
        return item


def _decode_run(row: sqlite3.Row, leads_found: int | None = None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "config": json.loads(row["config_json"]),
        "status": row["status"],
        "progress": row["progress"],
        "leads_found": row["leads_found"] if leads_found is None else leads_found,
        "errors": json.loads(row["errors_json"]),
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


def create_run(config: dict[str, Any], path: str | Path | None = None) -> str:
    run_id = str(uuid.uuid4())
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO runs (id, config_json, created_at) VALUES (?, ?, ?)",
            (run_id, json.dumps(config, ensure_ascii=False), _now()),
        )
    return run_id


def get_run(run_id: str, path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        count = conn.execute("SELECT COUNT(*) FROM run_leads WHERE run_id=?", (run_id,)).fetchone()[0]
        return _decode_run(row, count)


def list_runs(limit: int = 100, path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT r.*, COUNT(rl.lead_id) AS actual_leads FROM runs r "
            "LEFT JOIN run_leads rl ON rl.run_id=r.id "
            "GROUP BY r.id ORDER BY r.created_at DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
        return [_decode_run(row, row["actual_leads"]) for row in rows]


def update_run(
    run_id: str,
    *,
    status: str | None = None,
    progress: str | None = None,
    errors: list[str] | None = None,
    path: str | Path | None = None,
) -> None:
    assignments: list[str] = []
    values: list[Any] = []
    if status is not None:
        assignments.append("status=?")
        values.append(status)
        if status == "running":
            assignments.append("started_at=COALESCE(started_at, ?)")
            values.append(_now())
        if status in {"completed", "failed", "interrupted"}:
            assignments.append("completed_at=?")
            values.append(_now())
    if progress is not None:
        assignments.append("progress=?")
        values.append(progress)
    if errors is not None:
        assignments.append("errors_json=?")
        values.append(json.dumps(errors, ensure_ascii=False))
    if not assignments:
        return
    values.append(run_id)
    with connect(path) as conn:
        conn.execute(f"UPDATE runs SET {', '.join(assignments)} WHERE id=?", values)


def _lead_key(lead: Any) -> str:
    phone = re.sub(r"\D", "", lead.phone or "")
    place = f"{(lead.city or '').casefold().strip()}|{(lead.state or '').casefold().strip()}"
    if phone:
        raw = f"phone:{phone}|{place}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    domain = lead.domain
    if domain:
        # Preserve distinct branches of the same company/domain across cities.
        raw = "domain:" + domain.lower() + "|" + place
    else:
        name = re.sub(r"\s+", " ", (lead.name or "").casefold()).strip()
        raw = f"name:{name}|{place}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def save_leads(run_id: str, leads: list[Any], path: str | Path | None = None) -> int:
    """Upsert businesses globally and preserve each run's source association."""
    now = _now()
    saved = 0
    with connect(path) as conn:
        for lead in leads:
            if not (lead.name or lead.website or lead.phone):
                continue
            lead_id = str(uuid.uuid4())
            key = _lead_key(lead)
            site_status = "website_found_unverified" if lead.website else "website_not_located"
            audit_json = json.dumps(lead.audit, ensure_ascii=False) if lead.audit else None
            conn.execute(
                """INSERT OR IGNORE INTO leads (
                    id,dedupe_key,name,website,phone,address,city,state,category,rating,reviews,
                    source,query,maps_url,has_website,site_status,score,error,audit_json,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (lead_id, key, lead.name or "", lead.website or "", lead.phone or "", lead.address or "",
                 lead.city or "", lead.state or "", lead.category or "", lead.rating, lead.reviews,
                 lead.source or "", lead.query or "", lead.maps_url or "", int(bool(lead.website)),
                 site_status, lead.score, lead.error or "", audit_json, now, now),
            )
            row = conn.execute("SELECT id,source,has_website FROM leads WHERE dedupe_key=?", (key,)).fetchone()
            actual_id = row["id"]
            sources = list(dict.fromkeys(
                token for value in (row["source"], lead.source or "")
                for token in value.split("+") if token
            ))
            incoming_site_status = (
                "audit_ok" if lead.status == "ok" else
                "audit_error" if lead.status == "error" else site_status
            )
            audit_checked = lead.status in {"ok", "error"}
            conn.execute(
                """UPDATE leads SET
                    name=CASE WHEN name='' THEN ? ELSE name END,
                    website=CASE WHEN website='' THEN ? ELSE website END,
                    phone=CASE WHEN phone='' THEN ? ELSE phone END,
                    address=CASE WHEN address='' THEN ? ELSE address END,
                    city=CASE WHEN city='' THEN ? ELSE city END,
                    state=CASE WHEN state='' THEN ? ELSE state END,
                    category=CASE WHEN category='' THEN ? ELSE category END,
                    rating=COALESCE(rating,?), reviews=COALESCE(reviews,?),
                    maps_url=CASE WHEN maps_url='' THEN ? ELSE maps_url END,
                    has_website=MAX(has_website,?),
                    site_status=CASE WHEN ?=1 THEN ? WHEN has_website=0 AND ?=1 THEN 'website_found_unverified' ELSE site_status END,
                    score=COALESCE(?,score), error=CASE WHEN ?<>'' THEN ? ELSE error END,
                    audit_json=COALESCE(?,audit_json), updated_at=?
                    WHERE id=?""",
                (lead.name or "", lead.website or "", lead.phone or "", lead.address or "",
                 lead.city or "", lead.state or "", lead.category or "", lead.rating, lead.reviews,
                 lead.maps_url or "", int(bool(lead.website)),
                 int(audit_checked), incoming_site_status, int(bool(lead.website)),
                 lead.score, lead.error or "", lead.error or "", audit_json, now, actual_id),
            )
            conn.execute("UPDATE leads SET source=? WHERE id=?", ("+".join(sources), actual_id))
            conn.execute(
                "INSERT OR IGNORE INTO run_leads (run_id,lead_id,source,query) VALUES (?,?,?,?)",
                (run_id, actual_id, lead.source or "", lead.query or ""),
            )
            saved += 1
        conn.execute(
            "UPDATE runs SET leads_found=(SELECT COUNT(*) FROM run_leads WHERE run_id=?) WHERE id=?",
            (run_id, run_id),
        )
    return saved


def list_leads(
    *, run_id: str | None = None, search: str = "", stage: str = "", limit: int = 500,
    offset: int = 0, path: str | Path | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if run_id:
        conditions.append("EXISTS (SELECT 1 FROM run_leads rl WHERE rl.lead_id=l.id AND rl.run_id=?)")
        params.append(run_id)
    if search.strip():
        conditions.append("(l.name LIKE ? OR l.city LIKE ? OR l.website LIKE ? OR l.category LIKE ?)")
        pattern = f"%{search.strip()}%"
        params.extend([pattern] * 4)
    if stage:
        conditions.append("l.outreach_status=?")
        params.append(stage)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    params.extend([max(1, min(limit, 1000)), max(0, offset)])
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT l.* FROM leads l" + where + " ORDER BY l.updated_at DESC LIMIT ? OFFSET ?", params
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["has_website"] = bool(item["has_website"])
            item["audit"] = json.loads(item.pop("audit_json")) if item.get("audit_json") else None
            item["runs"] = [r[0] for r in conn.execute(
                "SELECT run_id FROM run_leads WHERE lead_id=? ORDER BY run_id", (item["id"],)
            ).fetchall()]
            result.append(item)
        return result


def update_lead(
    lead_id: str, *, outreach_status: str | None = None, notes: str | None = None,
    path: str | Path | None = None,
) -> bool:
    if outreach_status is not None and outreach_status not in OUTREACH_STAGES:
        raise ValueError("Etapa comercial inválida")
    assignments: list[str] = []
    values: list[Any] = []
    if outreach_status is not None:
        assignments.append("outreach_status=?")
        values.append(outreach_status)
    if notes is not None:
        assignments.append("notes=?")
        values.append(notes[:10000])
    if not assignments:
        raise ValueError("Nenhum campo para atualizar")
    assignments.append("updated_at=?")
    values.extend([_now(), lead_id])
    with connect(path) as conn:
        cur = conn.execute(f"UPDATE leads SET {', '.join(assignments)} WHERE id=?", values)
        return cur.rowcount > 0


def record_usage(
    provider: str, operation: str, *, run_id: str | None = None, units: int = 1,
    estimated_cost_usd: float = 0.0, path: str | Path | None = None,
) -> None:
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO usage_events(run_id,provider,operation,units,estimated_cost_usd,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (run_id, provider, operation, max(1, units), max(0.0, estimated_cost_usd), _now()),
        )
