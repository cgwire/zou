from tests.base import ApiDBTestCase


class CrudCreateRelationsTestCase(ApiDBTestCase):
    """
    A freshly created entry must have the same shape as the same entry
    fetched back from the single-instance GET route: relation keys are
    included in the creation response (see cgwire/gazu#385).
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()

    def test_create_response_includes_relations(self):
        playlist = self.post(
            "data/playlists",
            {
                "name": "created-with-relations",
                "project_id": str(self.project.id),
                "for_entity": "shot",
            },
        )
        self.assertIn("build_jobs", playlist)
        fetched = self.get(f"data/playlists/{playlist['id']}")
        self.assertEqual(set(playlist.keys()), set(fetched.keys()))
