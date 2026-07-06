from unittest.mock import patch

import pytest

from tests.base import ApiDBTestCase, indexer_is_up

from zou.app.services import assets_service, index_service

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not indexer_is_up(),
        reason="Needs a running Meilisearch (integration test)",
    ),
]
from zou.app.services.exception import (
    EpisodeNotFoundException,
    SequenceNotFoundException,
)


class IndexServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(IndexServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset_types()
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
        self.assertEqual(len(assets), 0)
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
        self.assertEqual(len(assets), 0)
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
        self.assertEqual(len(assets), 0)

    def test_prepare_shot_with_missing_sequence(self):
        with patch.object(
            index_service.shots_service,
            "get_sequence",
            side_effect=SequenceNotFoundException,
        ):
            data = index_service.prepare_shot(self.shot, index="dummy")
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
            data = index_service.prepare_shot(self.shot, index="dummy")
        self.assertEqual(data["sequence_id"], str(self.shot.parent_id))
        self.assertEqual(data["episode_id"], "")
