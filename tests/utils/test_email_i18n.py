import unittest
from zou.app.utils.email_i18n import get_email_translation, EMAIL_TRANSLATIONS


class EmailI18nTestCase(unittest.TestCase):
    def test_get_email_translation_en_us(self):
        result = get_email_translation("en_US", "comment_title")
        self.assertEqual(result, "New Comment")

    def test_get_email_translation_fr_fr(self):
        result = get_email_translation("fr_FR", "comment_title")
        self.assertEqual(result, "Nouveau commentaire")

    def test_get_email_translation_es_es(self):
        result = get_email_translation("es_ES", "comment_title")
        self.assertEqual(result, "Nuevo comentario")

    def test_get_email_translation_ja_jp(self):
        result = get_email_translation("ja_JP", "comment_title")
        self.assertEqual(result, "新しいコメント")

    def test_get_email_translation_de_de(self):
        result = get_email_translation("de_DE", "comment_title")
        self.assertEqual(result, "Neuer Kommentar")

    def test_get_email_translation_nl_nl(self):
        result = get_email_translation("nl_NL", "comment_title")
        self.assertEqual(result, "Nieuwe reactie")

    def test_get_email_translation_zh_cn(self):
        result = get_email_translation("zh_CN", "comment_title")
        self.assertEqual(result, "新评论")

    def test_get_email_translation_pt_br(self):
        result = get_email_translation("pt_BR", "comment_title")
        self.assertEqual(result, "Novo comentário")

    def test_get_email_translation_with_params(self):
        result = get_email_translation(
            "en_US",
            "comment_subject",
            task_status_name="WIP",
            author_first_name="John",
            task_name="Task 1",
        )
        self.assertEqual(
            result, "[Kitsu] WIP - John commented on Task 1"
        )

    def test_get_email_translation_fallback_to_en_us(self):
        result = get_email_translation("it_IT", "comment_title")
        self.assertEqual(result, "New Comment")

    def test_get_email_translation_fallback_with_short_code(self):
        result = get_email_translation("it", "comment_title")
        self.assertEqual(result, "New Comment")

    def test_get_email_translation_fallback_none_locale(self):
        result = get_email_translation(None, "comment_title")
        self.assertEqual(result, "New Comment")

    def test_get_email_translation_fallback_empty_string(self):
        result = get_email_translation("", "comment_title")
        self.assertEqual(result, "New Comment")

    def test_get_email_translation_short_code_mapping(self):
        result_fr = get_email_translation("fr", "comment_title")
        self.assertEqual(result_fr, "Nouveau commentaire")

        result_es = get_email_translation("es", "comment_title")
        self.assertEqual(result_es, "Nuevo comentario")

        result_ja = get_email_translation("ja", "comment_title")
        self.assertEqual(result_ja, "新しいコメント")

        result_de = get_email_translation("de", "comment_title")
        self.assertEqual(result_de, "Neuer Kommentar")

        result_nl = get_email_translation("nl", "comment_title")
        self.assertEqual(result_nl, "Nieuwe reactie")

        result_zh = get_email_translation("zh", "comment_title")
        self.assertEqual(result_zh, "新评论")

        result_pt = get_email_translation("pt", "comment_title")
        self.assertEqual(result_pt, "Novo comentário")

    def test_all_locales_have_all_keys(self):
        en_keys = set(EMAIL_TRANSLATIONS["en_US"].keys())

        for locale, translations in EMAIL_TRANSLATIONS.items():
            locale_keys = set(translations.keys())
            self.assertEqual(
                locale_keys,
                en_keys,
                f"Locale {locale} is missing keys: {en_keys - locale_keys}",
            )

    def test_comment_body_with_text_interpolation(self):
        result = get_email_translation(
            "fr_FR",
            "comment_body_with_text",
            author_full_name="Jean Dupont",
            task_url="http://example.com/task/1",
            task_name="Tâche 1",
            task_status_name="WIP",
            comment_text="Ceci est un commentaire",
        )
        self.assertIn("Jean Dupont", result)
        self.assertIn("Tâche 1", result)
        self.assertIn("WIP", result)
        self.assertIn("Ceci est un commentaire", result)
        self.assertIn("http://example.com/task/1", result)

    def test_playlist_episode_segment_interpolation(self):
        result = get_email_translation(
            "en_US",
            "playlist_episode_segment",
            episode_name="E01",
        )
        self.assertEqual(result, "the episode E01 of ")

        result_fr = get_email_translation(
            "fr_FR",
            "playlist_episode_segment",
            episode_name="E01",
        )
        self.assertEqual(result_fr, "l'épisode E01 du ")

    def test_email_signature_interpolation(self):
        result = get_email_translation(
            "en_US",
            "email_signature",
            organisation_name="Studio XYZ",
        )
        self.assertIn("Studio XYZ", result)
        self.assertIn("Best regards", result)

        result_fr = get_email_translation(
            "fr_FR",
            "email_signature",
            organisation_name="Studio XYZ",
        )
        self.assertIn("Studio XYZ", result_fr)
        self.assertIn("Cordialement", result_fr)
