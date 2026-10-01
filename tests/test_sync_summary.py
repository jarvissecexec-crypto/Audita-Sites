import unittest
from unittest.mock import patch

from siteaudit.models import Lead
from siteaudit.sync import sync_sqlite_to_supabase


class _SrcStub:
    def __init__(self, _path):
        pass

    def list_runs(self, limit=50):
        return [{"id": "run-1", "config": {"business_type": "x"}}]

    def list_leads(self, run_id=None, limit=1000):
        return [{
            "name": "Empresa",
            "website": "https://empresa.example",
            "phone": "",
            "address": "",
            "city": "POA",
            "state": "RS",
            "category": "x",
            "rating": None,
            "reviews": None,
            "source": "fake",
            "query": "x",
            "maps_url": "",
            "has_website": True,
            "site_status": "audit_ok",
            "score": 80,
            "error": "",
            "audit": {"ok": True, "score": 80},
        }]


class _DstStub:
    def __init__(self):
        self.calls = 0

    def run_exists(self, run_id):
        return self.calls > 0

    def create_run_with_id(self, run_id, config):
        return run_id

    def save_leads(self, run_id, leads):
        self.calls += 1
        assert isinstance(leads[0], Lead)
        return len(leads)


class SyncSummaryTests(unittest.TestCase):
    @patch("siteaudit.sync.SupabaseStorage", _DstStub)
    @patch("siteaudit.sync.SQLiteStorage", _SrcStub)
    def test_sync_returns_diagnostics(self):
        result = sync_sqlite_to_supabase("dummy.sqlite3", 10)
        self.assertEqual(result["runs"], 1)
        self.assertEqual(result["leads"], 1)
        self.assertEqual(result["failed_runs"], 0)
        self.assertIn("details", result)


if __name__ == "__main__":
    unittest.main()
