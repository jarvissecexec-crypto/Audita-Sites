import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from siteaudit.admin import db
from siteaudit.admin.worker import execute_search


class FakeFetcher:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def close(self):
        pass


class AdminWorkerTests(unittest.TestCase):
    def test_generic_search_worker_persists_results_for_each_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "admin.sqlite3"
            db.initialize(database)
            config = {
                "business_type": "segmento livre",
                "locations": [
                    {"city": "Cidade A", "state": "AA", "country": "Brasil"},
                    {"city": "Cidade B", "state": "BB", "country": "Brasil"},
                ],
                "quantity": 2,
                "quantity_mode": "total",
                "providers": ["fake"],
                "extra_queries": [],
                "audit_sites": False,
                "max_audits": 0,
            }
            run_id = db.create_run(config, database)

            discovery = types.ModuleType("siteaudit.discovery")

            def discover(fetcher, niche, city, state, **kwargs):
                from siteaudit.models import Lead

                return [Lead(
                    name=f"Negócio {city}", website=f"https://{city.casefold().replace(' ', '-')}.example",
                    city=city, state=state, category=niche, source="fake", query=city,
                )], []

            discovery.discover = discover
            utils = types.ModuleType("siteaudit.utils")
            utils.__path__ = []
            http = types.ModuleType("siteaudit.utils.http")
            http.Fetcher = FakeFetcher

            with patch.dict(sys.modules, {
                "siteaudit.discovery": discovery,
                "siteaudit.utils": utils,
                "siteaudit.utils.http": http,
            }):
                execute_search(run_id, database)

            run = db.get_run(run_id, database)
            leads = db.list_leads(run_id=run_id, path=database)
            self.assertEqual(run["status"], "completed")
            self.assertEqual(run["leads_found"], 2)
            self.assertEqual({lead["city"] for lead in leads}, {"Cidade A", "Cidade B"})


if __name__ == "__main__":
    unittest.main()
