"""Servidor HTTP local e API JSON do painel de administração."""

from __future__ import annotations

import ipaddress
import json
import re
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import db
from .worker import execute_search

STATIC_DIR = Path(__file__).parent / "static"
RUN_ID_RE = re.compile(r"^[0-9a-f-]{36}$", re.I)
WORKERS = ThreadPoolExecutor(max_workers=2, thread_name_prefix="siteaudit-run")


def _json_bytes(data: object) -> bytes:
    return json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")


def _validate_run(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("O corpo da busca deve ser um objeto JSON")
    business_type = str(payload.get("business_type", "")).strip()
    if not business_type or len(business_type) > 160:
        raise ValueError("Informe o tipo de empresa (máximo 160 caracteres)")

    raw_locations = payload.get("locations")
    if not isinstance(raw_locations, list) or not raw_locations or len(raw_locations) > 20:
        raise ValueError("Informe de 1 a 20 localidades por execução")
    locations = []
    for item in raw_locations:
        if isinstance(item, str):
            parts = [part.strip() for part in item.split(",", 2)]
            item = {"city": parts[0], "state": parts[1] if len(parts) > 1 else "",
                    "country": parts[2] if len(parts) > 2 else "Brasil"}
        if not isinstance(item, dict):
            raise ValueError("Cada localidade deve informar cidade, UF e país opcional")
        city = str(item.get("city", "")).strip()
        state = str(item.get("state", "")).strip()
        country = str(item.get("country", "Brasil")).strip() or "Brasil"
        if not city or len(city) > 160 or len(state) > 80 or len(country) > 100:
            raise ValueError("Localidade inválida: informe uma cidade com UF/país opcionais")
        location = {"city": city, "state": state, "country": country}
        if location not in locations:
            locations.append(location)

    quantity = payload.get("quantity", 20)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 500:
        raise ValueError("A quantidade deve ser um inteiro entre 1 e 500")
    quantity_mode = payload.get("quantity_mode", "total")
    if quantity_mode not in {"total", "per_location"}:
        raise ValueError("quantity_mode deve ser 'total' ou 'per_location'")
    requested_total = quantity * len(locations) if quantity_mode == "per_location" else quantity
    if requested_total > 500:
        raise ValueError("O total solicitado por execução não pode exceder 500 empresas")

    # Lazy import: persistence and the UI remain decoupled from provider code.
    from ..discovery import PROVIDERS

    providers = payload.get("providers", ["bing", "ddg"])
    if not isinstance(providers, list) or not providers:
        raise ValueError("Selecione pelo menos um provedor")
    providers = list(dict.fromkeys(str(provider).strip().lower() for provider in providers))
    unknown = [provider for provider in providers if provider not in PROVIDERS or provider == "manual"]
    if unknown:
        raise ValueError("Provedor inválido ou indisponível no painel: " + ", ".join(unknown))
    if "places" in providers:
        raise ValueError(
            "Google Places está temporariamente indisponível no painel: o conector atual é Legacy; "
            "vamos habilitá-lo depois de migrar a API e implementar limites de custo."
        )
    extra_queries = payload.get("extra_queries", [])
    if not isinstance(extra_queries, list) or len(extra_queries) > 8:
        raise ValueError("Consultas adicionais devem ser uma lista com até 8 itens")
    extra_queries = [str(query).strip()[:200] for query in extra_queries if str(query).strip()]

    audit_sites = bool(payload.get("audit_sites", False))
    max_audits = payload.get("max_audits", 10 if audit_sites else 0)
    if isinstance(max_audits, bool) or not isinstance(max_audits, int) or not 0 <= max_audits <= 100:
        raise ValueError("O limite de auditorias deve estar entre 0 e 100")
    if audit_sites and max_audits == 0:
        raise ValueError("Defina um limite maior que zero para auditar sites")

    return {
        "business_type": business_type,
        "locations": locations,
        "quantity": quantity,
        "quantity_mode": quantity_mode,
        "providers": providers,
        "extra_queries": extra_queries,
        "audit_sites": audit_sites,
        "max_audits": max_audits,
    }


class AdminHandler(BaseHTTPRequestHandler):
    server_version = "SiteAuditAdmin/0.1"

    def log_message(self, fmt: str, *args) -> None:
        # Avoid logging query strings, which could contain business-search terms.
        print(f"siteaudit-admin {self.address_string()} {fmt % args}")

    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, data: object) -> None:
        self._send(status, _json_bytes(data))

    def _read_json(self) -> object:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length inválido") from exc
        if length <= 0 or length > 1_000_000:
            raise ValueError("Corpo da requisição vazio ou maior que 1 MB")
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("JSON inválido") from exc

    def _is_local_request(self, check_origin: bool = False) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0].strip("[]").lower()
        if host not in {"127.0.0.1", "localhost"}:
            return False
        origin = self.headers.get("Origin", "")
        if check_origin and origin:
            origin_host = urlparse(origin).hostname or ""
            if origin_host.lower() not in {"127.0.0.1", "localhost"}:
                return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        if not self._is_local_request():
            self._send_json(403, {"error": "O painel só aceita acessos locais"})
            return
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self._static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/static/"):
            name = parsed.path.removeprefix("/static/")
            if name not in {"admin.css", "admin.js"}:
                self._send_json(404, {"error": "Arquivo não encontrado"})
                return
            content_type = "text/css; charset=utf-8" if name.endswith(".css") else "text/javascript; charset=utf-8"
            self._static(name, content_type)
            return
        if parsed.path == "/api/health":
            self._send_json(200, {"ok": True})
            return
        if parsed.path == "/api/providers":
            try:
                from ..discovery import PROVIDERS, PROVIDER_HELP

                items = [
                    {"id": key, "label": PROVIDERS[key].label, "description": description,
                     "needs_key": bool(PROVIDERS[key].needs_api_key),
                     "needs_browser": bool(PROVIDERS[key].needs_browser),
                     "enabled": key != "places"}
                    for key, description in PROVIDER_HELP.items() if key != "manual"
                ]
                self._send_json(200, {"providers": items})
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": f"Não foi possível carregar os provedores: {exc}"})
            return
        if parsed.path == "/api/runs":
            self._send_json(200, {"runs": db.list_runs()})
            return
        if parsed.path == "/api/leads":
            query = parse_qs(parsed.query)
            stage = query.get("stage", [""])[0]
            if stage and stage not in db.OUTREACH_STAGES:
                self._send_json(400, {"error": "Etapa comercial inválida"})
                return
            self._send_json(200, {"leads": db.list_leads(
                run_id=query.get("run_id", [""])[0] or None,
                search=query.get("q", [""])[0],
                stage=stage,
            )})
            return
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "runs"] and RUN_ID_RE.fullmatch(parts[2]):
            run = db.get_run(parts[2])
            if run:
                self._send_json(200, {"run": run})
            else:
                self._send_json(404, {"error": "Execução não encontrada"})
            return
        self._send_json(404, {"error": "Rota não encontrada"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._is_local_request(check_origin=True):
            self._send_json(403, {"error": "O painel só aceita acessos locais"})
            return
        if urlparse(self.path).path != "/api/runs":
            self._send_json(404, {"error": "Rota não encontrada"})
            return
        try:
            config = _validate_run(self._read_json())
            run_id = db.create_run(config)
            WORKERS.submit(execute_search, run_id)
            self._send_json(202, {"run_id": run_id, "status": "queued"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"error": f"Não foi possível iniciar a busca: {exc}"})

    def do_PATCH(self) -> None:  # noqa: N802
        if not self._is_local_request(check_origin=True):
            self._send_json(403, {"error": "O painel só aceita acessos locais"})
            return
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["api", "leads"] or not RUN_ID_RE.fullmatch(parts[2]):
            self._send_json(404, {"error": "Rota não encontrada"})
            return
        try:
            payload = self._read_json()
            if not isinstance(payload, dict):
                raise ValueError("O corpo deve ser um objeto JSON")
            status = payload.get("outreach_status")
            notes = payload.get("notes")
            if status is not None and not isinstance(status, str):
                raise ValueError("Etapa comercial inválida")
            if notes is not None and not isinstance(notes, str):
                raise ValueError("As notas devem ser texto")
            if status is None and notes is None:
                raise ValueError("Informe etapa comercial ou notas")
            updated = db.update_lead(parts[2], outreach_status=status, notes=notes)
            self._send_json(200 if updated else 404, {"ok": updated, "error": None if updated else "Lead não encontrado"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})

    def _static(self, name: str, content_type: str) -> None:
        target = STATIC_DIR / name
        try:
            body = target.read_bytes()
        except OSError:
            self._send_json(404, {"error": "Arquivo não encontrado"})
            return
        self._send(200, body, content_type)


def serve_admin(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Inicia o painel apenas em loopback até existir autenticação de usuários."""
    if host == "localhost":
        host = "127.0.0.1"
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        raise ValueError("O painel administrativo só pode escutar em localhost nesta versão")
    db.initialize()
    server = ThreadingHTTPServer((host, port), AdminHandler)
    url = f"http://{host}:{port}"
    print(f"Painel do siteaudit: {url}")
    print(f"Banco local: {db.database_path()}")
    if open_browser:
        try:
            if not webbrowser.open(url):
                print(f"Abra manualmente: {url}")
        except Exception as exc:  # noqa: BLE001 - headless/WSL may have no browser handler
            print(f"Abra manualmente: {url} ({exc})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando o painel…")
    finally:
        server.server_close()
        WORKERS.shutdown(wait=False, cancel_futures=True)
