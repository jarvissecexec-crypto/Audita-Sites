"""Modelos de dados do pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Lead:
    """Um potencial cliente encontrado na etapa de descoberta."""

    name: str = ""
    website: str = ""
    phone: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    category: str = ""
    rating: float | None = None
    reviews: int | None = None
    source: str = ""          # ddg | bing | maps | places | manual
    query: str = ""           # termo que encontrou este lead
    maps_url: str = ""
    has_website: bool = False
    status: str = "pending"   # pending | ok | website_not_located | error
    score: int | None = None  # 0-100 (só para quem tem site)
    error: str = ""
    audit: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def domain(self) -> str:
        w = (self.website or "").lower()
        for prefix in ("https://", "http://"):
            if w.startswith(prefix):
                w = w[len(prefix):]
        return w.split("/")[0].removeprefix("www.")


@dataclass
class Finding:
    """Um problema / oportunidade de melhoria detectado em um site."""

    severity: str      # critico | alto | medio | baixo | ok
    category: str      # SEO | Conteúdo | Performance | Design | Técnico | Conversão | Acessibilidade
    title: str
    detail: str = ""
    impact: str = ""   # por que isso importa para o dono do site
    fix: str = ""      # o que você vai entregar na demo

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SEVERITY_WEIGHT = {
    "critico": 22,
    "alto": 12,
    "medio": 6,
    "baixo": 2,
}
