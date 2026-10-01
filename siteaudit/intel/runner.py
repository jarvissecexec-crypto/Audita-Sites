from __future__ import annotations

from ..models import Lead


def _score(socials: dict, directories: list[dict], mentions: list[dict]) -> int:
    score = 0
    score += min(35, len([k for k, v in socials.items() if v]) * 8)
    score += min(35, len(directories) * 7)
    score += min(30, len(mentions) * 5)
    return max(0, min(100, score))


def enrich_lead(lead: Lead) -> dict:
    """Estrutura inicial do enriquecimento digital.

    Nesta fase inicial, preenchimento é placeholder para integrar provedores nas próximas tasks.
    """
    socials = {}
    directories: list[dict] = []
    mentions: list[dict] = []
    return {
        "socials": socials,
        "directories": directories,
        "mentions": mentions,
        "nap_consistency": None,
        "digital_footprint_score": _score(socials, directories, mentions),
    }
