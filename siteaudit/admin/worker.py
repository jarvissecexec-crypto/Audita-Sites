"""Workers das execuções administrativas; nenhum scraping bloqueia a interface."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from . import db
from ..models import Lead
from ..utils.http import Fetcher


def diagnose_lead(lead_id: str, db_path: str | Path | None = None) -> dict:
    """Diagnostica um lead específico pelo ID e salva o resultado no banco."""
    from ..audit.runner import audit_lead

    row = db.get_lead(lead_id, db_path)
    if not row:
        return {"ok": False, "error": "Lead não encontrado"}
    website = (row.get("website") or "").strip()
    if not website:
        return {"ok": False, "error": "Lead não possui site para diagnosticar"}
    lead = Lead(
        name=row.get("name", ""),
        website=website,
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
        status="pending",
        score=None,
        error="",
        audit=None,
    )
    fetcher = Fetcher(timeout=20, delay=0.5, respect_robots=True)
    try:
        audit_lead(fetcher, lead, max_pages=4, deep_perf=False)
    finally:
        fetcher.close()
    run_id = (row.get("runs") or [None])[0]
    if run_id:
        db.save_leads(run_id, [lead], db_path)
    result = lead.to_dict()
    result["ok"] = lead.status == "ok"
    return result


def diagnose_run_leads(run_id: str, db_path: str | Path | None = None) -> dict:
    """Diagnostica todos os leads de uma run que têm site.
    Retorna sumário com contagem de sucessos e falhas."""
    from ..audit.runner import audit_lead

    leads_rows = db.list_leads(run_id=run_id, path=db_path, limit=1000)
    results = {"total": 0, "success": 0, "failed": 0, "details": []}
    for row in leads_rows:
        website = (row.get("website") or "").strip()
        if not website:
            continue
        results["total"] += 1
        fetcher = Fetcher(timeout=20, delay=0.5, respect_robots=True)
        try:
            lead = Lead(
                name=row.get("name", ""),
                website=website,
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
                status="pending",
                score=None,
                error="",
                audit=None,
            )
            audit_lead(fetcher, lead, max_pages=4, deep_perf=False)
            db.save_leads(run_id, [lead], db_path)
            if lead.status == "ok":
                results["success"] += 1
                results["details"].append({"name": lead.name, "status": "ok", "score": lead.score})
            else:
                results["failed"] += 1
                results["details"].append({"name": lead.name, "status": "error", "error": lead.error})
        except Exception as exc:
            results["failed"] += 1
            results["details"].append({"name": row.get("name", "?"), "status": "exception", "error": str(exc)})
        finally:
            fetcher.close()
    return results


def _locations(config: dict[str, Any]) -> list[dict[str, str]]:
    return config["locations"]


def _interleave(groups: list[list[Any]], limit: int) -> list[Any]:
    """Distribui resultados entre localidades em vez de favorecer a primeira."""
    output: list[Any] = []
    cursor = 0
    while len(output) < limit:
        added = False
        for group in groups:
            if cursor < len(group):
                output.append(group[cursor])
                added = True
                if len(output) >= limit:
                    break
        if not added:
            break
        cursor += 1
    return output


def execute_search(run_id: str, db_path: str | Path | None = None) -> None:
    """Executa descoberta configurável e opcionalmente audita sites encontrados."""
    run = db.get_run(run_id, db_path)
    if not run:
        return
    config = run["config"]
    errors: list[str] = []
    db.update_run(run_id, status="running", progress="Preparando provedores", path=db_path)

    try:
        # Importação tardia mantém módulos de persistência/painel independentes
        # dos conectores externos.
        from ..discovery import discover
        from ..models import Lead
        from ..utils.http import Fetcher

        locations = _locations(config)
        target = int(config["quantity"])
        is_total = config["quantity_mode"] == "total"
        per_location = max(1, math.ceil(target / max(1, len(locations)))) if is_total else target
        groups: list[list[Lead]] = []

        for index, location in enumerate(locations, start=1):
            city = location["city"]
            state = location.get("state", "")
            label = ", ".join(part for part in (city, state, location.get("country", "Brasil")) if part)
            db.update_run(run_id, progress=f"Buscando {index}/{len(locations)}: {label}", path=db_path)
            fetcher = Fetcher(timeout=18, delay=1.0, respect_robots=True)
            try:
                found, provider_errors = discover(
                    fetcher,
                    config["business_type"],
                    city,
                    state,
                    providers=config["providers"],
                    limit=per_location,
                    places_key=config.get("places_key"),
                    extra_queries=config.get("extra_queries", []),
                    skip_social=False,
                    country=location.get("country", "Brasil"),
                )
            finally:
                fetcher.close()
            errors.extend(f"{label}: {message}" for message in provider_errors)
            for lead in found:
                lead.city = lead.city or city
                lead.state = lead.state or state
                lead.category = lead.category or config["business_type"]
            groups.append(found[:per_location])

        if is_total:
            leads = _interleave(groups, target)
        else:
            leads = [lead for group in groups for lead in group]

        if config.get("audit_sites") and config.get("max_audits", 0) > 0:
            candidates = [lead for lead in leads if lead.website][:config["max_audits"]]
            db.update_run(
                run_id,
                progress=f"Auditando {len(candidates)} site(s) (limite definido na busca)",
                path=db_path,
            )
            for index, lead in enumerate(candidates, start=1):
                fetcher = Fetcher(timeout=18, delay=1.0, respect_robots=True)
                try:
                    from ..audit.runner import audit_lead

                    audit_lead(fetcher, lead, max_pages=4, deep_perf=False)
                finally:
                    fetcher.close()
                db.update_run(
                    run_id,
                    progress=f"Auditoria {index}/{len(candidates)}: {lead.name or lead.domain}",
                    path=db_path,
                )

        db.save_leads(run_id, leads, db_path)
        final_status = "completed" if leads or not errors else "failed"
        db.update_run(
            run_id,
            status=final_status,
            progress=f"Concluído: {len(leads)} empresa(s) encontrada(s)",
            errors=errors,
            path=db_path,
        )
    except Exception as exc:  # noqa: BLE001 - persist the failure for the admin UI
        errors.append(f"{type(exc).__name__}: {exc}")
        db.update_run(
            run_id,
            status="failed",
            progress="A execução falhou; consulte os detalhes",
            errors=errors,
            path=db_path,
        )
