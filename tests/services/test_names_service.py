from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.services import files_service, names_service


class NamesServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.sequence_dict = self.sequence.serialize()
        self.generate_fixture_task_type()
        self.task_type_dict = self.task_type_animation.serialize()
        self.asset_task = self.generate_fixture_task().serialize()
        self.shot_task = self.generate_fixture_shot_task().serialize()

    def a_sequence_under_no_episode(self, name="S02"):
        """
        generate_fixture_sequence reads episode_id=None as "the usual
        episode", so a sequence with nothing above it is built here.
        """
        return Entity.create(
            name=name,
            project_id=self.project.id,
            entity_type_id=self.sequence_type.id,
        )

    def test_get_full_entity_name(self):
        """
        Where an entity sits, read upwards: an asset under its type, a
        sequence and a shot under their episode, an episode alone.
        """
        cases = {
            self.asset.id: "Props / Tree",
            self.episode.id: "E01",
            self.sequence.id: "E01 / S01",
            self.shot.id: "E01 / S01 / P01",
        }
        for entity_id, expected in cases.items():
            with self.subTest(expected=expected):
                name, _, _ = names_service.get_full_entity_name(entity_id)
                self.assertEqual(name, expected)

    def test_get_full_entity_name_of_a_flat_production(self):
        # A sequence with no episode above it, and the shot under it.
        sequence = self.a_sequence_under_no_episode()
        shot = self.generate_fixture_shot("P02", sequence_id=sequence.id)

        self.assertEqual(
            names_service.get_full_entity_name(sequence.id)[0], "S02"
        )
        self.assertEqual(
            names_service.get_full_entity_name(shot.id)[0], "S02 / P02"
        )

    def test_get_full_entity_names_agrees_with_the_single_lookup(self):
        """
        The batch version walks the same branches in its own code, so what
        matters is that the two never disagree. Every kind of entity is
        represented here, with and without an episode above it.
        """
        sequence = self.a_sequence_under_no_episode()
        flat_shot = self.generate_fixture_shot("P02", sequence_id=sequence.id)
        entity_ids = [
            str(entity.id)
            for entity in [
                self.asset,
                self.episode,
                self.sequence,
                self.shot,
                sequence,
                flat_shot,
            ]
        ]

        names = names_service.get_full_entity_names(entity_ids)

        self.assertEqual(
            names,
            {
                entity_id: names_service.get_full_entity_name(entity_id)
                for entity_id in entity_ids
            },
        )

    def test_get_full_entity_names_of_nothing(self):
        self.assertEqual(names_service.get_full_entity_names([]), {})

    def test_get_preview_file_name(self):
        preview_file = files_service.create_preview_file(
            "main", 3, self.shot_task["id"], self.user["id"], source="webgui"
        )
        name = names_service.get_preview_file_name(preview_file["id"])
        self.assertEqual(name, "cosmos_landromat_e01_s01_p01_animation_v3.mp4")

        preview_file = files_service.create_preview_file(
            "main", 3, self.asset_task["id"], self.user["id"], source="webgui"
        )
        name = names_service.get_preview_file_name(preview_file["id"])
        self.assertEqual(name, "cosmos_landromat_props_tree_shaders_v3.mp4")

        preview_file = files_service.create_preview_file(
            "main",
            4,
            self.asset_task["id"],
            self.user["id"],
            source="webgui",
            position=5,
        )
        name = names_service.get_preview_file_name(preview_file["id"])
        self.assertEqual(name, "cosmos_landromat_props_tree_shaders_v4-5.mp4")
