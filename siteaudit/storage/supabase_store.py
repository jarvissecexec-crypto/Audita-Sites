from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from supabase import Client, create_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _lead_key(lead: Any) -> str:
    phone = re.sub(r"\D", "", lead.phone or "")
    place = f"{(lead.city or '').casefold().strip()}|{(lead.state or '').casefold().strip()}"
    if phone:
        raw = f"phone:{phone}|{place}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    domain = lead.domain
    if domain:
        raw = "domain:" + domain.lower() + "|" + place
    else:
        name = re.sub(r"\s+", " ", (lead.name or "").casefold()).strip()
        raw = f"name:{name}|{place}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SupabaseStorage:
    """Persistência no Supabase usando a secret key."""

    def __init__(self, url: str | None = None, secret_key: str | None = None) -> None:
        self.url = url or os.getenv("SUPABASE_URL", "")
        self.secret_key = secret_key or os.getenv("SUPABASE_SECRET_KEY", "")
        if not self.url or not self.secret_key:
            raise ValueError("SUPABASE_URL e SUPABASE_SECRET_KEY são obrigatórios")
        self.client: Client = create_client(self.url, self.secret_key)

    def create_run(self, config: dict[str, Any]) -> str:
        run_id = str(uuid.uuid4())
        payload = {
            "id": run_id,
            "source": "local_worker",
            "config": config,
            "status": "queued",
            "progress": "",
            "leads_found": 0,
            "errors": [],
            "created_at": _now(),
        }
        self.client.table("runs").insert(payload).execute()
        return run_id

    def create_run_with_id(self, run_id: str, config: dict[str, Any]) -> str:
        payload = {
            "id": run_id,
            "source": "local_worker",
            "config": config,
            "status": "queued",
            "progress": "",
            "leads_found": 0,
            "errors": [],
            "created_at": _now(),
        }
        self.client.table("runs").upsert(payload, on_conflict="id").execute()
        return run_id

    def run_exists(self, run_id: str) -> bool:
        res = self.client.table("runs").select("id").eq("id", run_id).limit(1).execute()
        return bool(res.data)

    def save_leads(self, run_id: str, leads: list[Any]) -> int:
        saved = 0
        for lead in leads:
            if not (lead.name or lead.website or lead.phone):
                continue

            lead_key = _lead_key(lead)
            existing = self.client.table("leads").select("id,source").eq("dedupe_key", lead_key).limit(1).execute()

            site_status = "website_found_unverified" if lead.website else "website_not_located"
            audit_checked = lead.status in {"ok", "error"}
            incoming_site_status = "audit_ok" if lead.status == "ok" else "audit_error" if lead.status == "error" else site_status

            base_payload = {
                "dedupe_key": lead_key,
                "name": lead.name or "",
                "website": lead.website or "",
                "domain": lead.domain or "",
                "phone": lead.phone or "",
                "address": lead.address or "",
                "city": lead.city or "",
                "state": lead.state or "",
                "country": "Brasil",
                "category": lead.category or "",
                "rating": lead.rating,
                "reviews": lead.reviews,
                "source": lead.source or "",
                "query": lead.query or "",
                "maps_url": lead.maps_url or "",
                "has_website": bool(lead.website),
                "site_status": incoming_site_status if audit_checked else site_status,
                "outreach_status": "new",
                "score": lead.score,
                "notes": "",
                "updated_at": _now(),
            }

            if existing.data:
                lead_id = existing.data[0]["id"]
                current_source = existing.data[0].get("source") or ""
                merged = list(dict.fromkeys([x for x in (current_source + "+" + (lead.source or "")).split("+") if x]))
                base_payload["source"] = "+".join(merged)
                self.client.table("leads").update(base_payload).eq("id", lead_id).execute()
            else:
                lead_id = str(uuid.uuid4())
                payload = {"id": lead_id, "created_at": _now(), **base_payload}
                self.client.table("leads").insert(payload).execute()

            self.client.table("run_leads").upsert({
                "run_id": run_id,
                "lead_id": lead_id,
                "source": lead.source or "",
                "query": lead.query or "",
            }, on_conflict="run_id,lead_id").execute()

            if lead.audit:
                a = lead.audit
                self.client.table("audits").insert({
                    "lead_id": lead_id,
                    "run_id": run_id,
                    "ok": bool(a.get("ok")),
                    "score": a.get("score"),
                    "opportunity": a.get("opportunity"),
                    "opportunity_note": a.get("opportunity_note"),
                    "findings": a.get("findings") or [],
                    "seo": a.get("seo") or {},
                    "perf": a.get("perf") or {},
                    "tech": a.get("tech") or {},
                    "design": a.get("design") or {},
                    "content": a.get("content") or {},
                    "contacts": a.get("contacts") or {},
                    "links": a.get("links") or {},
                    "media": a.get("media") or {},
                    "forms": a.get("forms") or {},
                    "schema_data": a.get("schema") or {},
                    "raw": a,
                    "created_at": _now(),
                }).execute()

            saved += 1

        self.client.table("runs").update({"leads_found": saved, "status": "completed", "completed_at": _now()}).eq("id", run_id).execute()
        return saved

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        res = self.client.table("runs").select("*").order("created_at", desc=True).limit(max(1, min(limit, 500))).execute()
        return res.data or []

    def list_leads(self, *, run_id: str | None = None, search: str = "", stage: str = "",
                   limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
        q = self.client.table("leads").select("*").order("updated_at", desc=True).range(offset, offset + max(1, min(limit, 1000)) - 1)
        if stage:
            q = q.eq("outreach_status", stage)
        if search.strip():
            term = search.strip()
            q = q.or_(f"name.ilike.%{term}%,city.ilike.%{term}%,website.ilike.%{term}%,category.ilike.%{term}%")
        leads = q.execute().data or []
        if run_id:
            rel = self.client.table("run_leads").select("lead_id").eq("run_id", run_id).execute().data or []
            allowed = {x["lead_id"] for x in rel}
            leads = [l for l in leads if l.get("id") in allowed]
        return leads
