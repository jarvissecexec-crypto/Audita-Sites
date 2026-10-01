import sys
import types
import unittest
from unittest.mock import patch

from siteaudit.admin.server import _validate_run
from siteaudit.admin.worker import _interleave


class AdminConfigTests(unittest.TestCase):
    def setUp(self):
        discovery = types.ModuleType("siteaudit.discovery")
        discovery.PROVIDERS = {key: object() for key in ("bing", "ddg", "osm", "places", "manual")}
        self.discovery_patch = patch.dict(sys.modules, {"siteaudit.discovery": discovery})
        self.discovery_patch.start()

    def tearDown(self):
        self.discovery_patch.stop()

    def test_search_config_accepts_free_text_and_multiple_locations(self):
        config = _validate_run({
            "business_type": "qualquer segmento escolhido pelo usuário",
            "locations": ["Porto Alegre, RS", {"city": "Caxias do Sul", "state": "RS"}],
            "quantity": 30,
            "quantity_mode": "total",
            "providers": ["bing", "ddg"],
        })

        self.assertEqual(config["business_type"], "qualquer segmento escolhido pelo usuário")
        self.assertEqual(len(config["locations"]), 2)
        self.assertEqual(config["quantity"], 30)

    def test_per_location_limit_cannot_expand_beyond_execution_cap(self):
        with self.assertRaisesRegex(ValueError, "500 empresas"):
            _validate_run({
                "business_type": "oficinas",
                "locations": [{"city": f"Cidade {i}"} for i in range(2)],
                "quantity": 300,
                "quantity_mode": "per_location",
                "providers": ["osm"],
            })

    def test_legacy_places_provider_is_paused_before_cost_controls(self):
        with self.assertRaisesRegex(ValueError, "Legacy"):
            _validate_run({
                "business_type": "empresas",
                "locations": ["Porto Alegre, RS"],
                "providers": ["places"],
            })

    def test_results_are_interleaved_between_locations_for_total_quota(self):
        self.assertEqual(_interleave([["A1", "A2"], ["B1", "B2"]], 3), ["A1", "B1", "A2"])


if __name__ == "__main__":
    unittest.main()
