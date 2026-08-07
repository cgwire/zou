import unittest

from unittest import mock

from zou.app.services import templates_service


class TemplatesServiceTestCase(unittest.TestCase):
    """
    The two pieces every notification email is built from: a signature that
    names the studio in the reader's language, and the HTML shell the
    message is dropped into. No database is involved, only the organisation
    name, which is mocked.
    """

    def setUp(self):
        self.organisation = mock.patch.object(
            templates_service.persons_service,
            "get_organisation",
            return_value={"name": "Ghost Studio"},
        ).start()
        self.addCleanup(mock.patch.stopall)

    def test_signature_carries_the_organisation_name(self):
        self.assertIn("Ghost Studio", templates_service.get_signature("en_US"))

    def test_signature_follows_the_locale(self):
        self.assertIn("Best regards", templates_service.get_signature("en_US"))
        self.assertIn("Cordialement", templates_service.get_signature("fr_FR"))
        self.assertIn(
            "Saludos cordiales", templates_service.get_signature("es_ES")
        )

    def test_signature_falls_back_to_english(self):
        # A locale nobody wrote a translation for, and no locale at all: a
        # notification is sent either way.
        self.assertIn("Best regards", templates_service.get_signature("zz_ZZ"))
        self.assertIn("Best regards", templates_service.get_signature())

    def test_signature_escapes_the_organisation_name(self):
        # A studio names itself, and the name lands in an HTML mail.
        self.organisation.return_value = {"name": "<b>Ghost</b> & Co"}

        signature = templates_service.get_signature("en_US")

        self.assertIn("&lt;b&gt;Ghost&lt;/b&gt; &amp; Co", signature)
        self.assertNotIn("<b>Ghost</b>", signature)

    def test_body_wraps_title_and_message_in_the_template(self):
        body = templates_service.generate_html_body(
            "A title", "<p>A message</p>", locale="en_US"
        )

        self.assertTrue(body.lstrip().startswith("<!DOCTYPE html>"))
        self.assertTrue(body.rstrip().endswith("</html>"))
        # Title, then message, then the studio signing off.
        self.assertLess(body.index("A title"), body.index("<p>A message</p>"))
        self.assertLess(body.index("<p>A message</p>"), body.index("Ghost"))

    def test_body_follows_the_locale(self):
        body = templates_service.generate_html_body("t", "m", locale="fr_FR")

        self.assertIn("Cordialement", body)

    def test_message_is_inserted_as_raw_html(self):
        # Pinning the contract rather than the behaviour we would like:
        # generate_html_body receives HTML its callers have already built,
        # so it cannot escape. Callers interpolating a playlist name or a
        # person name are the ones that have to escape, and today they do
        # not. Should that be fixed, this test is the one to revisit.
        body = templates_service.generate_html_body(
            "t", "<script>alert(1)</script>", locale="en_US"
        )

        self.assertIn("<script>alert(1)</script>", body)
