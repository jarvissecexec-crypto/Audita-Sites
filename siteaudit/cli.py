"""Interface de linha de comando do siteaudit.

Exemplos:

    # pipeline completo: pizzarias em Igrejinha/RS
    python -m siteaudit run --niche "pizzaria" --city "Igrejinha" --state RS \\
        --providers bing,maps --limit 25

    # só descobrir leads
    python -m siteaudit discover --niche "contador" --city "Novo Hamburgo" --state RS

    # auditar sites específicos
    python -m siteaudit audit --url https://exemplo.com.br --url https://outro.com

    # gerar o relatório de uma auditoria já feita
    python -m siteaudit report --from leads.json --out-dir saida

    # servir o dashboard no navegador
    python -m siteaudit serve --dir out/run --port 8080
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import __version__
from .audit.runner import audit_lead
from .discovery import PROVIDER_HELP, discover
from .discovery.base import normalize_lead
from .models import Lead
from .report.generator import write_outputs
from .storage import build_runtime_storage, resolve_storage_mode
from .sync import sync_sqlite_to_supabase
from .utils.http import Fetcher

BANNER = r"""
  _ _                       _ _ _
 ___(_) |_ ___  __ _ _   _| | __| |_   _ _ __ | |_
/ __| | __/ _ \/ _` | | | | |/ _` | | | | '_ \| __|
\__ \ | ||  __/ (_| | |_| | | (_| | |_| | | | | |_
|___/_|\__\___|\__,_|\__,_|_|\__,_|\__,_|_| |_|\__|
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="siteaudit",
        description="Descobre empresas por nicho/região e audita os sites delas "
                    "para gerar uma demo de venda.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=" provedores disponíveis:\n" + "\n".join(
            f"   {k:8} {v}" for k, v in PROVIDER_HELP.items()),
    )
    p.add_argument("-v", "--version", action="version", version=f"siteaudit {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--out-dir", default="relatorios", help="diretório de saída (padrão: relatorios)")
        sp.add_argument("--timeout", type=float, default=20.0)
        sp.add_argument("--delay", type=float, default=0.6, help="espera entre requisições no mesmo host (s)")
        sp.add_argument("--concurrency", type=int, default=6, help="sites auditados em paralelo")
        sp.add_argument("--proxy", default=os.getenv("HTTP_PROXY") or os.getenv("http_proxy"))
        sp.add_argument("--ignore-robots", action="store_true",
                        help="ignora robots.txt (use apenas em sites seus/autorizados)")
        sp.add_argument("--render", action="store_true", help="usa navegador real (Playwright) em todo site")
        sp.add_argument("--no-auto-render", action="store_true",
                        help="desliga o fallback automático para navegador em sites vazios (JS)")
        sp.add_argument("--screenshots", action="store_true", help="salva captura da home (requer Playwright)")
        sp.add_argument("--max-pages", type=int, default=4, help="páginas internas visitadas por site")
        sp.add_argument("--fast", action="store_true", help="pula medição de tamanho dos assets (mais rápido)")
        sp.add_argument("--no-badge", action="store_true", help="remove o selo 'proposta de demonstração' da demo")
        sp.add_argument("--internal-only", action="store_true",
                        help="modo interno: não gera propostas/briefings automáticos")

    # ------------------------------------------------------------- run
    sp = sub.add_parser("run", help="pipeline completo: descobrir + auditar + relatório")
    sp.add_argument("--niche", required=True, help='ex.: "pizzaria", "contador", "advogado"')
    sp.add_argument("--city", default="")
    sp.add_argument("--state", default="", help="UF, ex.: RS")
    sp.add_argument("--providers", default="bing,ddg",
                    help="lista separada por vírgula: bing,ddg,google,maps,places,manual")
    sp.add_argument("--limit", type=int, default=20, help="leads desejados por provedor")
    sp.add_argument("--max-audit", type=int, default=40, help="máximo de sites a auditar")
    sp.add_argument("--places-key", default=os.getenv("GOOGLE_MAPS_API_KEY"))
    sp.add_argument("--file", help="CSV/JSON com leads próprios (use com --providers manual)")
    sp.add_argument("--query", action="append", default=[], help="consulta extra (pode repetir)")
    sp.add_argument("--name", default="", help="nome da pasta do run (padrão: nicho-cidade)")
    sp.add_argument("--storage", choices=("sqlite", "supabase", "dual"), default=None,
                    help="persistência do run: sqlite|supabase|dual (padrão: SITEAUDIT_STORAGE ou sqlite)")
    common(sp)

    # --------------------------------------------------------- discover
    sp = sub.add_parser("discover", help="apenas descobrir leads (sem auditar)")
    sp.add_argument("--niche", required=True)
    sp.add_argument("--city", default="")
    sp.add_argument("--state", default="")
    sp.add_argument("--providers", default="bing,ddg")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--places-key", default=os.getenv("GOOGLE_MAPS_API_KEY"))
    sp.add_argument("--file", help="CSV/JSON (com --providers manual)")
    sp.add_argument("--query", action="append", default=[])
    sp.add_argument("--json", dest="json_out", help="salvar leads em JSON")
    sp.add_argument("--csv", dest="csv_out", help="salvar leads em CSV")
    common(sp)

    # ------------------------------------------------------------ audit
    sp = sub.add_parser("audit", help="auditar uma lista de URLs")
    sp.add_argument("--url", action="append", default=[], help="URL (pode repetir)")
    sp.add_argument("--file", help="arquivo com uma URL por linha, ou CSV/JSON de leads")
    sp.add_argument("--city", default="", help="rótulo da cidade (para o relatório)")
    sp.add_argument("--state", default="", help="rótulo da UF (para o relatório)")
    sp.add_argument("--name", default="audit")
    common(sp)

    # ----------------------------------------------------------- report
    sp = sub.add_parser("report", help="gerar relatório a partir de um leads.json")
    sp.add_argument("--from", dest="src", required=True, help="arquivo leads.json")
    sp.add_argument("--out-dir", default="relatorios/relatorio")
    sp.add_argument("--no-badge", action="store_true")
    sp.add_argument("--internal-only", action="store_true",
                    help="modo interno: não gera propostas/briefings automáticos")

    # ------------------------------------------------------------ serve
    sp = sub.add_parser("serve", help="servir o relatório em um servidor local")
    sp.add_argument("--dir", default="relatorios")
    sp.add_argument("--port", type=int, default=8080)

    # --------------------------------------------------------- providers
    sub.add_parser("providers", help="listar provedores de descoberta")

    # ------------------------------------------------------------ admin
    sp = sub.add_parser("admin", help="abrir o painel administrativo local")
    sp.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"),
                    help="o painel fica restrito à máquina local")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--no-open", action="store_true", help="não abrir o navegador automaticamente")

    # ------------------------------------------------------------- sync
    sp = sub.add_parser("sync", help="sincronizar histórico local (SQLite) para Supabase")
    sp.add_argument("--from-sqlite", dest="sqlite_path", default="data/siteaudit.sqlite3")
    sp.add_argument("--limit-runs", type=int, default=50)
    return p


# ------------------------------------------------------------------ helpers
def make_fetcher(args) -> Fetcher:
    return Fetcher(
        timeout=getattr(args, "timeout", 20.0),
        delay=getattr(args, "delay", 0.6),
        respect_robots=not getattr(args, "ignore_robots", False),
        proxy=getattr(args, "proxy", None),
    )


def print_leads(leads: list[Lead]) -> None:
    print(f"\n{len(leads)} leads encontrados\n" + "-" * 92)
    print(f"{'EMPRESA':38} {'CIDADE':18} {'SITE':26} {'FONTE'}")
    print("-" * 92)
    for lead in leads:
        site = (lead.domain or "não localizado")[:25]
        print(f"{(lead.name or '?')[:37]:38} {(lead.city or '—')[:17]:18} {site:26} {lead.source}")
    print("-" * 92)


def audit_many(leads: list[Lead], args, max_audit: int | None = None) -> list[Lead]:
    targets = [l for l in leads if l.website][: max_audit or len(leads)]
    if not targets:
        return leads
    print(f"\nAuditando {len(targets)} site(s) com {args.concurrency} threads…")
    done = 0

    def work(lead: Lead) -> Lead:
        fetcher = make_fetcher(args)
        try:
            return audit_lead(
                fetcher, lead,
                render=args.render,
                auto_render=not getattr(args, "no_auto_render", False),
                max_pages=args.max_pages,
                deep_perf=not args.fast,
                screenshot_path=None,  # definido abaixo
            )
        finally:
            fetcher.close()

    # capturas opcionais: geradas ao final, em sequência (evita vários Chromium)
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = [pool.submit(work, lead) for lead in targets]
        for future in as_completed(futures):
            done += 1
            try:
                lead = future.result()
            except Exception as exc:  # noqa: BLE001
                print(f"  ! erro: {exc}")
                continue
            status = {  # noqa: SIM108
                "ok": f"nota {lead.score}",
                "error": f"erro: {(lead.error or '')[:40]}",
            }.get(lead.status, lead.status)
            print(f"  [{done}/{len(targets)}] {lead.domain[:42]:44} {status}")

    if args.screenshots:
        shots_dir = Path(args.out_dir) / "assets"
        shots_dir.mkdir(parents=True, exist_ok=True)
        fetcher = make_fetcher(args)
        for lead in targets:
            if lead.status != "ok":
                continue
            from .utils.text import slugify
            shot = shots_dir / f"{slugify(lead.domain)}.png"
            try:
                fetcher.render(lead.website, screenshot=str(shot), respect_robots=True)
            except Exception:
                pass
        fetcher.close()
    return leads


def leads_from_file(path: str) -> list[Lead]:
    from .discovery.manual import ManualProvider
    provider = ManualProvider(fetcher=None, path=path)  # type: ignore[arg-type]
    leads = provider._load()
    return leads


def save_simple(leads: list[Lead], json_out: str | None, csv_out: str | None) -> None:
    if json_out:
        Path(json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(json_out).write_text(
            json.dumps([l.to_dict() for l in leads], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON salvo em {json_out}")
    if csv_out:
        import csv
        Path(csv_out).parent.mkdir(parents=True, exist_ok=True)
        with open(csv_out, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["nome", "cidade", "uf", "endereco", "telefone", "site", "categoria", "origem", "maps_url"])
            for l in leads:
                w.writerow([l.name, l.city, l.state, l.address, l.phone, l.website, l.category, l.source, l.maps_url])
        print(f"CSV salvo em {csv_out}")


def persist_run_if_configured(args, leads: list[Lead], errors: list[str]) -> None:
    mode = resolve_storage_mode(getattr(args, "storage", None))
    if mode == "sqlite":
        # SQLite já é usado pelo painel/worker; no modo CLI tradicional não forçamos gravação adicional.
        return
    try:
        storage = build_runtime_storage(mode=mode)
        config = {
            "command": args.command,
            "niche": getattr(args, "niche", ""),
            "city": getattr(args, "city", ""),
            "state": getattr(args, "state", ""),
            "providers": getattr(args, "providers", ""),
            "internal_only": bool(getattr(args, "internal_only", False)),
            "errors": errors,
        }
        run_id = storage.create_run(config)
        saved = storage.save_leads(run_id, leads)
        print(f"Persistência ({mode}) concluída: run={run_id} leads={saved}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! persistência ({mode}) falhou: {type(exc).__name__}: {exc}")


def finish_report(leads: list[Lead], args, niche: str, city: str, state: str,
                  providers: str, errors: list[str]) -> dict:
    out_dir = Path(args.out_dir)
    if getattr(args, "name", ""):
        out_dir = out_dir / args.name
    stamp = time.strftime("%Y%m%d-%H%M")
    if not getattr(args, "name", ""):
        from .utils.text import slugify
        out_dir = out_dir / f"{slugify(niche or 'nicho')}-{slugify(city or 'regiao')}-{stamp[-4:]}"
    result = write_outputs(
        leads, out_dir, niche=niche, city=city, state=state,
        providers=providers, errors=errors, show_badge=not getattr(args, "no_badge", False),
        internal_only=getattr(args, "internal_only", False),
    )
    meta = result["meta"]
    print("\n" + "=" * 72)
    print("RELATÓRIO PRONTO")
    print("=" * 72)
    print(f"  Dashboard : {result['dashboard']}")
    print(f"  CSV       : {result['csv']}")
    print(f"  JSON      : {result['json']}")
    if not getattr(args, "internal_only", False):
        print(f"  Propostas : {out_dir / 'propostas'}")
        print(f"  Briefings : {out_dir / 'briefings'}")
    print("-" * 72)
    print(f"  {meta['leads_total']} empresas · {meta['with_site']} com site localizado · {meta['no_site']} sem domínio próprio localizado")
    print(f"  nota média: {meta['avg_score']} · oportunidades altas: {meta['hot_leads']}")
    if meta["errors"]:
        print("-" * 72)
        for err in meta["errors"][:6]:
            print(f"  ! {err}")
    print("=" * 72)
    print("\nDica: abra o arquivo index.html da pasta do run ou rode:")
    print(f"  python -m siteaudit serve --dir {out_dir}\n")
    return result


# -------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "providers":
        print("\nProvedores de descoberta:\n")
        for key, desc in PROVIDER_HELP.items():
            print(f"  {key:8} {desc}")
        print("\nUso: --providers bing,ddg,maps,places,manual")
        return 0

    if args.command == "serve":
        import functools
        import http.server
        import socketserver
        directory = str(Path(args.dir).resolve())
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("0.0.0.0", args.port), handler) as httpd:
            print(f"Servindo {directory} em http://0.0.0.0:{args.port}")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
        return 0

    if args.command == "admin":
        from .admin.server import serve_admin
        serve_admin(args.host, args.port, open_browser=not args.no_open)
        return 0

    if args.command == "sync":
        result = sync_sqlite_to_supabase(args.sqlite_path, args.limit_runs)
        print(f"Sincronização concluída: {result['runs']} runs, {result['leads']} leads")
        return 0

    if args.command == "report":
        data = json.loads(Path(args.src).read_text(encoding="utf-8"))
        leads = []
        for item in data.get("leads", []):
            lead = Lead(**{k: v for k, v in item.items() if k in Lead.__annotations__})
            leads.append(lead)
        meta = data.get("meta", {})
        write_outputs(leads, args.out_dir, niche=meta.get("niche", ""), city=meta.get("place", ""),
                      providers=meta.get("providers", ""), errors=meta.get("errors", []),
                      show_badge=not args.no_badge,
                      internal_only=args.internal_only)
        print(f"Relatório gerado em {args.out_dir}/index.html")
        return 0

    print(BANNER)
    fetcher = make_fetcher(args)

    try:
        if args.command == "discover":
            leads, errors = discover(
                fetcher, args.niche, args.city, args.state,
                providers=[p for p in args.providers.split(",") if p],
                limit=args.limit, places_key=args.places_key,
                manual_file=args.file, extra_queries=args.query,
            )
            print_leads(leads)
            for err in errors:
                print(f"  ! {err}")
            save_simple(leads, args.json_out, args.csv_out)
            return 0

        if args.command == "audit":
            leads: list[Lead] = []
            for url in args.url:
                leads.append(Lead(name=url, website=url if url.startswith("http") else "https://" + url))
            if args.file:
                text = Path(args.file).read_text(encoding="utf-8").strip()
                if text.startswith("[") or text.startswith("{"):
                    leads.extend(leads_from_file(args.file))
                else:
                    for line in text.splitlines():
                        line = line.strip()
                        if line:
                            leads.append(Lead(name=line, website=line if line.startswith("http") else "https://" + line))
            if not leads:
                print("Informe --url ou --file")
                return 1
            urls = [l.website if l.website.startswith("http") else "https://" + l.website for l in leads]
            leads = [normalize_lead(Lead(name=l.name or u, website=u)) for l, u in zip(leads, urls)]
            audit_many(leads, args)
            for lead in leads:
                lead.city = lead.city or args.city
                lead.state = lead.state or args.state
            finish_report(leads, args, "Auditoria de sites", args.city, args.state, "manual", [])
            return 0

        if args.command == "run":
            leads, errors = discover(
                fetcher, args.niche, args.city, args.state,
                providers=[p for p in args.providers.split(",") if p],
                limit=args.limit, places_key=args.places_key,
                manual_file=args.file, extra_queries=args.query,
            )
            print_leads(leads)
            for err in errors:
                print(f"  ! {err}")
            audit_many(leads, args, max_audit=args.max_audit)
            persist_run_if_configured(args, leads, errors)
            finish_report(leads, args, args.niche, args.city, args.state, args.providers, errors)
            return 0
    finally:
        fetcher.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
