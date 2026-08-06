from unittest.mock import patch

import pytest

from tests.base import ApiDBTestCase, indexer_is_up

from zou.app.services import assets_service, index_service
from zou.app.services.exception import (
    EpisodeNotFoundException,
    SequenceNotFoundException,
)

# The gate is on the class that talks to the indexer, not on the module: the
# document builders below need no Meilisearch and must run everywhere.
needs_indexer = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not indexer_is_up(),
        reason="Needs a running Meilisearch (integration test)",
    ),
]


class IndexServiceTestCase(ApiDBTestCase):
    pytestmark = needs_indexer

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_asset_character()
        self.generate_fixture_asset_character("Sprite")
        self.generate_fixture_asset_character("Cat")
        self.generate_fixture_asset_character("Dog")
        self.generate_fixture_asset_character("Fox")
        self.generate_fixture_asset_character("Lémo")
        self.generate_fixture_asset_character("L'ustensile")
        self.project_ids = [str(self.project.id)]
        self.asset_type_id = str(self.asset_type.id)
        index_service.reset_index()

    def test_search_assets_exact(self):
        assets = index_service.search_assets("rabbit", self.project_ids)
        self.assertEqual(len(assets), 1)

    def test_search_assets_partial(self):
        assets = index_service.search_assets("rabb", self.project_ids)
        self.assertEqual(len(assets), 1)
        assets = index_service.search_assets("usten", self.project_ids)
        self.assertEqual(len(assets), 1)

    def test_search_assets_after_creation(self):
        assets = index_service.search_assets("girafe", self.project_ids)
        self.assertEqual(assets, [])
        assets_service.create_asset(
            self.project_id, self.asset_type_id, "Girafe", "", {}
        )
        assets = index_service.search_assets("girafe", self.project_ids)
        self.assertEqual(len(assets), 1)

    def test_search_assets_after_update(self):
        asset = assets_service.create_asset(
            self.project_id, self.asset_type_id, "Girafe", "", {}
        )
        assets = index_service.search_assets("girafe")
        self.assertEqual(len(assets), 1)
        assets_service.update_asset(asset["id"], {"name": "Elephant"})
        assets = index_service.search_assets("girafe")
        self.assertEqual(assets, [])
        assets = index_service.search_assets("elephant")
        self.assertEqual(len(assets), 1)

    def test_search_assets_after_deletion(self):
        asset = assets_service.create_asset(
            self.project_id, self.asset_type_id, "Girafe", "", {}
        )
        assets = index_service.search_assets("girafe")
        self.assertEqual(len(assets), 1)
        assets_service.remove_asset(asset["id"])
        assets = index_service.search_assets("girafe")
        self.assertEqual(assets, [])

    def test_prepare_shot_with_missing_sequence(self):
        with patch.object(
            index_service.shots_service,
            "get_sequence",
            side_effect=SequenceNotFoundException,
        ):
            data = index_service.prepare_shot(self.shot)
        self.assertEqual(data["sequence_id"], "")
        self.assertEqual(data["episode_id"], "")

    def test_prepare_shot_with_missing_episode(self):
        fake_sequence = {"name": "S01", "parent_id": "missing-episode-id"}
        with patch.object(
            index_service.shots_service,
            "get_sequence",
            return_value=fake_sequence,
        ), patch.object(
            index_service.shots_service,
            "get_episode",
            side_effect=EpisodeNotFoundException,
        ):
            data = index_service.prepare_shot(self.shot)
        self.assertEqual(data["sequence_id"], str(self.shot.parent_id))
        self.assertEqual(data["episode_id"], "")


class PrepareDocumentTestCase(ApiDBTestCase):
    """
    The documents pushed to the index. No indexer involved: they are plain
    dicts built from a model.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_person()

    def test_prepare_asset(self):
        asset = self.generate_fixture_asset(name="main_character")
        asset.update({"data": {"size": 3}})
        document = index_service.prepare_asset(asset)
        self.assertEqual(document["id"], str(asset.id))
        # The name is repeated with its separators spelled out, so that a
        # search on "main character" reaches an asset named "main_character".
        self.assertEqual(
            document["name"], "Props main_character main character"
        )
        self.assertEqual(document["metadatas"], {"size": "3"})

    def test_prepare_person(self):
        document = index_service.prepare_person(self.person)
        self.assertEqual(document["id"], str(self.person.id))
        self.assertEqual(document["name"], self.person.full_name)
