import pytest

from tests.base import ApiDBTestCase

from zou.app.models.entity import EntityLink
from zou.app.services import (
    assets_service,
    deletion_service,
    entities_service,
    projects_service,
)

from zou.app.services.exception import (
    EntityLinkNotFoundException,
    EntityNotFoundException,
    EntityTypeNotFoundException,
    PreviewFileNotFoundException,
)

UNKNOWN = "00000000-0000-0000-0000-000000000000"


class EntityTypeTestCase(ApiDBTestCase):
    """
    Entity types are a tiny, heavily read table: every lookup is memoized
    for four minutes, and two of the three lookups create the row they do
    not find.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset_type()

    def test_get_entity_type(self):
        self.assertEqual(
            entities_service.get_entity_type(self.asset_type.id),
            self.asset_type.serialize(),
        )

        with pytest.raises(EntityTypeNotFoundException):
            entities_service.get_entity_type(UNKNOWN)

    def test_get_entity_type_by_name(self):
        self.assertEqual(
            entities_service.get_entity_type_by_name(self.asset_type.name),
            self.asset_type.serialize(),
        )

    def test_get_entity_type_by_name_creates_what_it_cannot_find(self):
        entity_type = entities_service.get_entity_type_by_name("Matte")

        self.assertEqual(entity_type["name"], "Matte")
        self.assertEqual(
            entities_service.get_entity_type_by_name("Matte")["id"],
            entity_type["id"],
        )

    def test_get_entity_type_by_name_or_not_found(self):
        self.assertEqual(
            entities_service.get_entity_type_by_name_or_not_found(
                self.asset_type.name
            )["id"],
            str(self.asset_type.id),
        )

        with pytest.raises(EntityTypeNotFoundException):
            entities_service.get_entity_type_by_name_or_not_found("Matte")

    def test_a_renamed_type_is_read_again_after_the_cache_is_dropped(self):
        entities_service.get_entity_type(self.asset_type.id)

        self.asset_type.update({"name": "Sets"})
        entities_service.clear_entity_type_cache(str(self.asset_type.id))

        self.assertEqual(
            entities_service.get_entity_type(self.asset_type.id)["name"],
            "Sets",
        )
        self.assertEqual(
            entities_service.get_entity_type_by_name("Sets")["id"],
            str(self.asset_type.id),
        )

    def test_get_temporal_entity_type_by_name(self):
        """
        The by-name lookup can have cached a None from before the type
        existed. This one drops that entry and looks again.
        """
        self.assertIsNotNone(
            entities_service.get_temporal_entity_type_by_name("Edit")
        )

    def test_is_edit(self):
        edit_type = entities_service.get_temporal_entity_type_by_name("Edit")

        self.assertTrue(
            entities_service.is_edit({"entity_type_id": edit_type["id"]})
        )
        self.assertFalse(
            entities_service.is_edit(
                {"entity_type_id": str(self.asset_type.id)}
            )
        )


class EntityTestCase(ApiDBTestCase):
    """
    The entity lookups every other service builds on, and the one write
    this service owns: setting an entity's main preview.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_task()
        self.generate_fixture_preview_file()
        self.asset_id = str(self.asset.id)
        self.preview_file_id = str(self.preview_file.id)

    def test_get_entity_raw(self):
        self.assertEqual(
            entities_service.get_entity_raw(self.asset.id).id, self.asset.id
        )

        with pytest.raises(EntityNotFoundException):
            entities_service.get_entity_raw(UNKNOWN)

    def test_get_entity(self):
        self.assertEqual(
            entities_service.get_entity(self.asset.id),
            self.asset.serialize(),
        )

        with pytest.raises(EntityNotFoundException):
            entities_service.get_entity(UNKNOWN)

    def test_a_renamed_entity_is_read_again_after_the_cache_is_dropped(self):
        # Warmed with the id read off the row, dropped with its string
        # form: the memoization keys on the argument, and the two callers
        # must not end up on two entries.
        entities_service.get_entity(self.asset.id)
        entities_service.get_entity(self.asset_id)

        self.asset.update({"name": "Rock"})
        entities_service.clear_entity_cache(self.asset_id)

        self.assertEqual(
            entities_service.get_entity(self.asset.id)["name"], "Rock"
        )
        self.assertEqual(
            entities_service.get_entity(self.asset_id)["name"], "Rock"
        )

    def test_update_entity_preview(self):
        entities_service.update_entity_preview(
            self.asset_id, self.preview_file_id
        )

        asset = assets_service.get_asset(self.asset_id)
        self.assertEqual(asset["preview_file_id"], self.preview_file_id)

    def test_update_entity_preview_refuses_what_it_cannot_find(self):
        with pytest.raises(EntityNotFoundException):
            entities_service.update_entity_preview(
                self.preview_file_id, self.preview_file_id
            )

        with pytest.raises(PreviewFileNotFoundException):
            entities_service.update_entity_preview(
                self.asset_id, self.asset_id
            )

    def test_setting_a_preview_announces_it_under_the_entity_kind(self):
        """
        Two events: the generic one, and one named after the kind of
        entity, which is what each listing subscribes to. An asset type is
        any name the studio invented, so it is announced as "asset".
        """
        main = self.capture_events("preview-file:set-main")

        entities_service.update_entity_preview(
            self.asset_id, self.preview_file_id
        )

        self.assertEqual(
            [
                (
                    event["entity_id"],
                    event["preview_file_id"],
                    event["project_id"],
                )
                for event in main
            ],
            [
                (
                    self.asset_id,
                    self.preview_file_id,
                    str(self.asset.project_id),
                )
            ],
        )

    def test_a_shot_is_announced_as_a_shot(self):
        captured = self.capture_events("shot:update")
        shot_id = str(self.shot.id)

        entities_service.update_entity_preview(shot_id, self.preview_file_id)

        self.assertEqual([event["shot_id"] for event in captured], [shot_id])

    def test_an_asset_is_announced_as_an_asset(self):
        captured = self.capture_events("asset:update")

        entities_service.update_entity_preview(
            self.asset_id, self.preview_file_id
        )

        self.assertEqual(
            [event["asset_id"] for event in captured], [self.asset_id]
        )

    def test_get_for_entity_from_task(self):
        """
        The name of the kind of entity a task hangs on. Every asset type a
        studio invents comes back as "Asset"; the temporal ones keep their
        own name.
        """
        shot_task = self.generate_fixture_shot_task()

        self.assertEqual(
            entities_service.get_for_entity_from_task(self.task.serialize()),
            "Asset",
        )
        self.assertEqual(
            entities_service.get_for_entity_from_task(shot_task.serialize()),
            "Shot",
        )


class EntityListingTestCase(ApiDBTestCase):
    """
    The entities of one production, of one type.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

    def test_get_entities_for_project(self):
        self.generate_fixture_project_standard()
        # Named to sort first while created last, and one asset of the same
        # name in another production, which must not show up.
        self.generate_fixture_asset("Anvil")
        self.generate_fixture_asset(
            "Anvil", project_id=self.project_standard.id
        )

        assets = entities_service.get_entities_for_project(
            str(self.project.id), str(self.asset_type.id), obj_type="Asset"
        )

        self.assertEqual(
            [asset["name"] for asset in assets], ["Anvil", "Tree"]
        )
        self.assertEqual(assets[0]["type"], "Asset")

    def test_get_entities_for_project_is_scoped_to_its_type(self):
        # The shot shares the production, not the type.
        assets = entities_service.get_entities_for_project(
            str(self.project.id), str(self.asset_type.id)
        )

        self.assertEqual([asset["name"] for asset in assets], ["Tree"])

    def test_get_entities_for_project_holds_one_episode(self):
        # Both generators repoint the attribute they name, so what belongs
        # to the first episode has to be read before the second is made.
        here, here_episode_id = self.sequence.name, str(self.episode.id)
        elsewhere = self.generate_fixture_episode("E02")
        self.generate_fixture_sequence("S02", episode_id=elsewhere.id)

        sequences = entities_service.get_entities_for_project(
            str(self.project.id),
            str(self.sequence_type.id),
            episode_id=here_episode_id,
        )

        self.assertEqual([sequence["name"] for sequence in sequences], [here])


class EntityTasksTestCase(ApiDBTestCase):
    """
    The tasks hanging off an entity, dispatched to the listing of the right
    kind.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()

    def assert_the_tasks_of_the_entity_are_listed(self, entity_id):
        """
        The listing carries every task of that entity and nothing else,
        whatever kind of entity it is.
        """
        entity = entities_service.get_entity(str(entity_id))

        tasks = entities_service.get_entity_tasks(entity)

        self.assertGreater(len(tasks), 0)
        for task in tasks:
            self.assertEqual(task["entity_id"], str(entity_id))
            self.assertIn("task_type_name", task)
            self.assertIn("id", task)

    def test_get_entity_tasks_shot(self):
        self.assert_the_tasks_of_the_entity_are_listed(self.shot.id)

    def test_get_entity_tasks_asset(self):
        self.assert_the_tasks_of_the_entity_are_listed(self.asset.id)

    def test_get_entity_tasks_no_tasks(self):
        shot = entities_service.get_entity(str(self.shot.id))
        deletion_service.remove_task(str(self.shot_task.id), force=True)

        self.assertEqual(entities_service.get_entity_tasks(shot), [])

    def test_get_entities_and_tasks(self):
        self.generate_fixture_sequence_task()

        sequences = entities_service.get_entities_and_tasks()

        # Every entity carrying a task, of whatever kind, each with its
        # own tasks and no other.
        by_name = {entity["name"]: entity for entity in sequences}
        self.assertEqual(sorted(by_name), ["P01", "S01", "Tree"])
        for name, entity in by_name.items():
            with self.subTest(name=name):
                self.assertEqual(
                    [task["entity_id"] for task in entity["tasks"]],
                    [entity["id"]],
                )


class EntityLinkTestCase(ApiDBTestCase):
    """
    The casting links between entities: which asset appears in which shot.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.project_id = str(self.project.id)

    def a_link(self, nb_occurences=1, label=""):
        return EntityLink.create(
            entity_in_id=self.shot.id,
            entity_out_id=self.asset.id,
            nb_occurences=nb_occurences,
            label=label,
        )

    def test_get_entity_link(self):
        link = self.a_link(nb_occurences=3, label="hero")

        result = entities_service.get_entity_link(str(link.id))

        self.assertEqual(result["entity_in_id"], str(self.shot.id))
        self.assertEqual(result["entity_out_id"], str(self.asset.id))
        self.assertEqual(result["nb_occurences"], 3)
        self.assertEqual(result["label"], "hero")

    def test_get_entity_link_that_is_not_there(self):
        with pytest.raises(EntityLinkNotFoundException):
            entities_service.get_entity_link(UNKNOWN)

    def test_remove_entity_link(self):
        link = self.a_link()

        removed = entities_service.remove_entity_link(str(link.id))

        self.assertEqual(removed["id"], str(link.id))
        with pytest.raises(EntityLinkNotFoundException):
            entities_service.get_entity_link(str(link.id))

    def test_remove_entity_link_that_is_not_there(self):
        with pytest.raises(EntityLinkNotFoundException):
            entities_service.remove_entity_link(UNKNOWN)

    def test_get_entity_links_for_project(self):
        link = self.a_link(nb_occurences=2, label="hero")

        links = entities_service.get_entity_links_for_project(self.project_id)

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["id"], link.id)
        self.assertEqual(links[0]["nb_occurences"], 2)
        self.assertEqual(links[0]["label"], "hero")
        self.assertEqual(links[0]["type"], "EntityLink")

    def test_get_entity_links_for_project_is_scoped_to_its_production(self):
        self.a_link()
        elsewhere = self.generate_fixture_project_standard()

        self.assertEqual(
            entities_service.get_entity_links_for_project(str(elsewhere.id)),
            [],
        )

    def test_get_entity_links_for_project_is_bounded(self):
        self.a_link()
        second_shot = self.generate_fixture_shot("S02")
        EntityLink.create(
            entity_in_id=second_shot.id, entity_out_id=self.asset.id
        )

        self.assertEqual(
            len(
                entities_service.get_entity_links_for_project(
                    self.project_id, limit=1
                )
            ),
            1,
        )
        # The paged branch answers with the envelope the listings use.
        paged = entities_service.get_entity_links_for_project(
            self.project_id, page=1, limit=1
        )
        self.assertEqual(len(paged["data"]), 1)
        self.assertEqual(paged["nb_pages"], 2)


class VendorMetadataTestCase(ApiDBTestCase):
    """
    A vendor sees the custom fields of their own departments only. The two
    halves are separate on purpose: one reads the descriptors of the
    production, the other strips a payload with what it was handed.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_department()
        self.project_id = str(self.project.id)
        self.own_department = str(self.department.id)
        self.other_department = str(self.department_animation.id)

    def a_descriptor(self, name, entity_type="Asset", departments=None):
        return projects_service.add_metadata_descriptor(
            self.project_id,
            entity_type,
            name,
            "string",
            [],
            False,
            departments=departments or [],
        )

    def test_a_descriptor_of_no_department_is_visible_to_everyone(self):
        self.a_descriptor("Contractor")

        self.assertEqual(
            entities_service.get_not_allowed_descriptors_fields_for_vendor(
                departments=[], projects_ids=[self.project_id]
            ),
            {self.project_id: []},
        )

    def test_a_descriptor_of_another_department_is_hidden(self):
        self.a_descriptor("Rig Notes", departments=[self.other_department])

        self.assertEqual(
            entities_service.get_not_allowed_descriptors_fields_for_vendor(
                departments=[self.own_department],
                projects_ids=[self.project_id],
            ),
            {self.project_id: ["rig_notes"]},
        )

    def test_a_descriptor_of_ones_own_department_stays_visible(self):
        self.a_descriptor("Rig Notes", departments=[self.own_department])

        self.assertEqual(
            entities_service.get_not_allowed_descriptors_fields_for_vendor(
                departments=[self.own_department],
                projects_ids=[self.project_id],
            ),
            {self.project_id: []},
        )

    def test_the_kind_of_entity_is_taken_into_account(self):
        self.a_descriptor(
            "Rig Notes",
            entity_type="Shot",
            departments=[self.other_department],
        )

        self.assertEqual(
            entities_service.get_not_allowed_descriptors_fields_for_vendor(
                entity_type="Asset",
                departments=[self.own_department],
                projects_ids=[self.project_id],
            ),
            {self.project_id: []},
        )

    def test_remove_not_allowed_fields_from_metadata(self):
        data = {"rig_notes": "secret", "contractor": "Acme"}

        self.assertEqual(
            entities_service.remove_not_allowed_fields_from_metadata(
                ["rig_notes"], data
            ),
            {"contractor": "Acme"},
        )
        self.assertEqual(
            entities_service.remove_not_allowed_fields_from_metadata([], data),
            data,
        )
        self.assertEqual(
            entities_service.remove_not_allowed_fields_from_metadata(), {}
        )
