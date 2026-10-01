import os
import unittest

from siteaudit.storage.factory import resolve_storage_mode


class StorageFactoryTests(unittest.TestCase):
    def test_resolve_storage_mode_defaults_to_sqlite(self):
        old = os.environ.pop("SITEAUDIT_STORAGE", None)
        try:
            self.assertEqual(resolve_storage_mode(None), "sqlite")
            self.assertEqual(resolve_storage_mode("invalido"), "sqlite")
        finally:
            if old is not None:
                os.environ["SITEAUDIT_STORAGE"] = old

    def test_resolve_storage_mode_accepts_env(self):
        old = os.environ.get("SITEAUDIT_STORAGE")
        os.environ["SITEAUDIT_STORAGE"] = "supabase"
        try:
            self.assertEqual(resolve_storage_mode(None), "supabase")
        finally:
            if old is None:
                os.environ.pop("SITEAUDIT_STORAGE", None)
            else:
                os.environ["SITEAUDIT_STORAGE"] = old


if __name__ == "__main__":
    unittest.main()
