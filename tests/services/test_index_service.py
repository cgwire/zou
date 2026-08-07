from unittest.mock import patch

import pytest

from tests.base import ApiDBTestCase, indexer_is_up

from zou.app.models.entity import Entity

from zou.app.services import (
    assets_service,
    index_service,
    projects_service,
)
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


class SearchTestCase(ApiDBTestCase):
    pytestmark = needs_indexer

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
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
        self.assertEqual(
            len(index_service.search_assets("rabbit", self.project_ids)), 1
        )

    def test_search_assets_partial(self):
        self.assertEqual(
            len(index_service.search_assets("rabb", self.project_ids)), 1
        )
        self.assertEqual(
            len(index_service.search_assets("usten", self.project_ids)), 1
        )

    def test_search_assets_after_creation(self):
        self.assertEqual(
            index_service.search_assets("girafe", self.project_ids), []
        )

        assets_service.create_asset(
            self.project_id, self.asset_type_id, "Girafe", "", {}
        )

        self.assertEqual(
            len(index_service.search_assets("girafe", self.project_ids)), 1
        )

    def test_search_assets_after_update(self):
        asset = assets_service.create_asset(
            self.project_id, self.asset_type_id, "Girafe", "", {}
        )

        assets_service.update_asset(asset["id"], {"name": "Elephant"})

        self.assertEqual(index_service.search_assets("girafe"), [])
        self.assertEqual(len(index_service.search_assets("elephant")), 1)

    def test_search_assets_after_deletion(self):
        asset = assets_service.create_asset(
            self.project_id, self.asset_type_id, "Girafe", "", {}
        )
        self.assertEqual(len(index_service.search_assets("girafe")), 1)

        assets_service.remove_asset(asset["id"])

        self.assertEqual(index_service.search_assets("girafe"), [])

    def test_search_drops_a_hit_whose_row_is_gone(self):
        """
        The index and the database drift apart the moment a row leaves
        without a reindex. The stale hit is dropped rather than answered as
        a half built asset.
        """
        asset = assets_service.create_asset(
            self.project_id, self.asset_type_id, "Girafe", "", {}
        )
        Entity.get(asset["id"]).delete()

        self.assertEqual(index_service.search_assets("girafe"), [])

    def test_search_shots_of_a_tv_show_carry_their_episode(self):
        self.project.update({"production_type": "tvshow"})
        projects_service.clear_project_cache(str(self.project.id))

        shot = index_service.search_shots("P01", self.project_ids)[0]

        self.assertEqual(shot["episode"], self.episode.name)
        self.assertEqual(shot["episode_id"], str(self.episode.id))

    def test_search_shots_of_a_film_carry_no_episode(self):
        shot = index_service.search_shots("P01", self.project_ids)[0]

        self.assertNotIn("episode", shot)


class PrepareDocumentTestCase(ApiDBTestCase):
    """
    The documents pushed to the index. No indexer involved: they are plain
    dicts built from a model, and what a studio can search on is decided
    here rather than in the query.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_person()

    def test_prepare_asset(self):
        asset = self.generate_fixture_asset(name="main_character")
        asset.update({"data": {"size": 3}})

        document = index_service.prepare_asset(asset)

        self.assertEqual(document["id"], str(asset.id))
        # The name is repeated with its separators spelled out, so that a
        # search on "main character" reaches an asset named "main_character",
        # and prefixed with the asset type so that a search on the type
        # reaches its assets.
        self.assertEqual(
            document["name"], "Props main_character main character"
        )
        self.assertEqual(document["project_id"], str(self.project.id))
        # Stored as strings: the index has one type per field.
        self.assertEqual(document["metadatas"], {"size": "3"})

    def test_prepare_person(self):
        document = index_service.prepare_person(self.person)

        self.assertEqual(document["id"], str(self.person.id))
        self.assertEqual(document["name"], self.person.full_name)

    def test_prepare_shot(self):
        """
        A shot is named after where it sits: the episode and the sequence
        are part of what the studio types to find it, the same way the
        asset type is for an asset.
        """
        self.shot.update({"data": {"fps": 25, "camera": "A"}})

        document = index_service.prepare_shot(self.shot)

        self.assertEqual(document["id"], str(self.shot.id))
        self.assertEqual(document["name"], "E01 S01 P01 P01")
        self.assertEqual(document["sequence_id"], str(self.sequence.id))
        self.assertEqual(document["episode_id"], str(self.episode.id))
        self.assertEqual(document["project_id"], str(self.project.id))
        # The technical fields are not worth searching on.
        self.assertEqual(document["metadatas"], {"camera": "A"})

    def test_prepare_shot_outside_an_episode(self):
        # A production that is not a series has sequences and no episode:
        # the generator hangs one off self.episode, so this one is built by
        # hand.
        sequence = Entity.create(
            name="S02",
            project_id=self.project.id,
            entity_type_id=self.sequence_type.id,
        )
        shot = self.generate_fixture_shot("P02", sequence_id=sequence.id)

        document = index_service.prepare_shot(shot)

        self.assertEqual(document["name"], "S02 P02 P02")
        # Null rather than the empty string the two paths below give: the
        # sequence was found and simply has no parent. Nothing filters on
        # this field, so the difference is recorded, not corrected.
        self.assertIsNone(document["episode_id"])

    def test_prepare_shot_with_missing_sequence(self):
        with patch.object(
            index_service.shots_service,
            "get_sequence",
            side_effect=SequenceNotFoundException,
        ):
            document = index_service.prepare_shot(self.shot)

        self.assertEqual(document["name"], "P01 P01")
        self.assertEqual(document["sequence_id"], "")
        self.assertEqual(document["episode_id"], "")

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
            document = index_service.prepare_shot(self.shot)

        self.assertEqual(document["name"], "S01 P01 P01")
        self.assertEqual(document["sequence_id"], str(self.shot.parent_id))
        self.assertEqual(document["episode_id"], "")


class WithoutIndexerTestCase(ApiDBTestCase):
    """
    Most studios run no Meilisearch. Indexation is a side effect of writes
    it must never break, so every call answers an empty document rather
    than raising.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_person()

    @pytest.mark.skipif(indexer_is_up(), reason="Needs no running Meilisearch")
    def test_indexing_without_an_indexer_is_a_no_op(self):
        self.assertEqual(index_service.index_asset(self.asset), {})
        self.assertEqual(index_service.index_person(self.person), {})
        self.assertEqual(
            index_service.remove_asset_index(str(self.asset.id)), {}
        )
        self.assertEqual(
            index_service.remove_person_index(str(self.person.id)), {}
        )

    def test_an_indexer_that_stops_answering_is_swallowed_too(self):
        """
        A configured Meilisearch that goes down mid-run is the other half of
        the same promise: an unreachable one is logged, never raised, so the
        write that triggered the indexation still goes through.

        The index handle is faked so that this holds whether or not the
        machine running the tests has an indexer.
        """
        with patch.object(
            index_service.indexing, "get_index", return_value=object()
        ):
            with patch.object(
                index_service.indexing,
                "index_document",
                side_effect=ConnectionError("indexer is down"),
            ):
                self.assertEqual(index_service.index_asset(self.asset), {})
            with patch.object(
                index_service.indexing,
                "remove_document",
                side_effect=ConnectionError("indexer is down"),
            ):
                self.assertEqual(
                    index_service.remove_asset_index(str(self.asset.id)), {}
                )
