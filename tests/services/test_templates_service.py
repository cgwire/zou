import unittest

from unittest import mock

from zou.app.services import templates_service


class TemplatesServiceTestCase(unittest.TestCase):
    def setUp(self):
        organisation = mock.patch.object(
            templates_service.persons_service,
            "get_organisation",
            return_value={"name": "Ghost Studio"},
        )
        organisation.start()
        self.addCleanup(organisation.stop)

    def test_signature_carries_the_organisation_name(self):
        signature = templates_service.get_signature("en_US")
        self.assertIn("Ghost Studio", signature)

    def test_signature_follows_the_locale(self):
        self.assertIn("Best regards", templates_service.get_signature("en_US"))
        self.assertIn("Cordialement", templates_service.get_signature("fr_FR"))
        self.assertIn(
            "Saludos cordiales", templates_service.get_signature("es_ES")
        )

    def test_body_wraps_title_and_message_in_the_template(self):
        body = templates_service.generate_html_body(
            "A title", "<p>A message</p>", locale="en_US"
        )
        self.assertTrue(body.lstrip().startswith("<!DOCTYPE html>"))
        self.assertIn("A title", body)
        self.assertIn("<p>A message</p>", body)
        self.assertIn("Ghost Studio", body)
        self.assertLess(body.index("A title"), body.index("<p>A message</p>"))

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
