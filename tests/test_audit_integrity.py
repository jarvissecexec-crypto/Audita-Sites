import unittest

from bs4 import BeautifulSoup

from siteaudit.audit.extract import extract_content, extract_contacts, extract_schema


class AuditIntegrityTests(unittest.TestCase):
    def test_content_extraction_does_not_destroy_other_audit_inputs(self):
        soup = BeautifulSoup(
            """<html><body>
            <h1>Serviço local</h1><p>Descrição suficiente para a extração de texto.</p>
            <script type="application/ld+json">{"@type":"LocalBusiness"}</script>
            <script src="/app.js"></script><style>.hero{display:flex}</style>
            <iframe src="https://www.google.com/maps/embed?x=1"></iframe>
            </body></html>""",
            "html.parser",
        )

        content = extract_content(soup)

        self.assertEqual(content["h1"], ["Serviço local"])
        self.assertIsNotNone(soup.find("script", attrs={"type": "application/ld+json"}))
        self.assertIsNotNone(soup.find("script", src="/app.js"))
        self.assertIsNotNone(soup.find("style"))
        self.assertIsNotNone(soup.find("iframe"))
        self.assertTrue(extract_schema(soup)["has_local_business"])
        self.assertIn("/app.js", [tag["src"] for tag in soup.find_all("script", src=True)])

    def test_plain_phone_is_not_misreported_as_whatsapp(self):
        soup = BeautifulSoup("<p>Telefone: (51) 3333-4444</p>", "html.parser")

        contacts = extract_contacts(soup, str(soup), "https://example.com")

        self.assertTrue(contacts["phones"])
        self.assertEqual(contacts["whatsapp"], "")
        self.assertFalse(contacts["whatsapp_verified"])


if __name__ == "__main__":
    unittest.main()
