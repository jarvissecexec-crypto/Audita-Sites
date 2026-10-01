import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from siteaudit.admin import db


class AdminDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "test.sqlite3"
        db.initialize(self.path)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_run_and_lead_lifecycle(self):
        run_id = db.create_run({"business_type": "example livre"}, self.path)
        lead = SimpleNamespace(
            domain="empresa.example", name="Empresa Exemplo", website="https://empresa.example",
            phone="(51) 3333-4444", address="Rua Central, 10", city="Porto Alegre", state="RS",
            category="example livre", rating=None, reviews=None, source="test", query="empresa local",
            maps_url="", has_website=True, status="pending", score=None, error="", audit=None,
        )

        self.assertEqual(db.save_leads(run_id, [lead], self.path), 1)
        self.assertEqual(db.save_leads(run_id, [lead], self.path), 1)
        self.assertEqual(len(db.list_leads(run_id=run_id, path=self.path)), 1)
        self.assertEqual(db.get_run(run_id, self.path)["leads_found"], 1)

        saved = db.list_leads(run_id=run_id, path=self.path)[0]
        self.assertEqual(saved["site_status"], "website_found_unverified")
        self.assertTrue(db.update_lead(saved["id"], outreach_status="qualified", notes="Revisar", path=self.path))
        updated = db.list_leads(run_id=run_id, path=self.path)[0]
        self.assertEqual(updated["outreach_status"], "qualified")
        self.assertEqual(updated["notes"], "Revisar")

    def test_invalid_outreach_stage_is_rejected(self):
        with self.assertRaises(ValueError):
            db.update_lead("missing", outreach_status="unknown", path=self.path)


if __name__ == "__main__":
    unittest.main()
