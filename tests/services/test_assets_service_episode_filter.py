from tests.base import ApiDBTestCase
from zou.app.models.entity import EntityLink
from zou.app.services import assets_service


class AssetsAndTasksEpisodeFilterTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task()
        self.generate_fixture_task()
        self.generate_fixture_metadata_descriptor()
        self.person_id = str(self.person.id)
        self.asset_id = self.asset.id
        self.meta_descriptor_id = self.meta_descriptor.id
        self.department_id = self.department.id
        self.task_type_dict = self.task_type.serialize()

    def test_get_assets_and_tasks_episode_filter(self):
        """
        An asset both sourced from an episode and cast in it through an
        entity link must come back exactly once with its tasks, and an
        asset unrelated to the episode must not come back at all.
        """
        self.generate_fixture_episode("E01")
        episode_id = str(self.episode.id)
        self.asset.update({"source_id": self.episode.id})
        EntityLink.create(
            entity_in_id=self.episode.id, entity_out_id=self.asset.id
        )
        self.generate_fixture_asset_character()

        assets = assets_service.get_assets_and_tasks(
            {"episode_id": episode_id}
        )
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["id"], str(self.asset_id))
        self.assertEqual(len(assets[0]["tasks"]), 1)
        self.assertEqual(
            assets[0]["tasks"][0]["assignees"], [str(self.person_id)]
        )

        main_assets = assets_service.get_assets_and_tasks(
            {"episode_id": "main"}
        )
        self.assertEqual(len(main_assets), 1)
        self.assertEqual(main_assets[0]["id"], str(self.asset_character.id))
