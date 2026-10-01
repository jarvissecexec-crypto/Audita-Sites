"""Script auxiliar: extrai resumo de todos os runs na pasta relatorios."""
import glob
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("relatorios")

for leads_file in sorted(root.rglob("leads.json")):
    try:
        d = json.loads(leads_file.read_text(encoding="utf-8"))
    except Exception:
        continue
    m = d.get("meta", {})
    folder = leads_file.parent.name
    niche_guess = folder.split("-")[0] if "-" in folder else folder
    print(f"  {folder}:")
    print(f"    leads={len(d['leads'])}  total={m.get('leads_total','?')}  "
          f"com_site={m.get('with_site','?')}  sem_site={m.get('no_site','?')}  "
          f"nota_média={m.get('avg_score','?')}  oportunidades={m.get('hot_leads','?')}")
    if m.get("errors"):
        print(f"    erros={len(m['errors'])}")
    print()