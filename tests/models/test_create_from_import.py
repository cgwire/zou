from unittest import mock

from sqlalchemy.exc import IntegrityError

from tests.base import ApiDBTestCase
from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.comment import Comment
from zou.app.models.entity import Entity, EntityLink
from zou.app.models.entity_type import EntityType, TaskTypeAssetTypeLink
from zou.app.models.person import Person
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import (
    Project,
    ProjectAssetTypeLink,
    ProjectPersonLink,
    ProjectPreviewBackgroundFileLink,
    ProjectStatusAutomationLink,
    ProjectTaskStatusLink,
    ProjectTaskTypeLink,
)
from zou.app.models.task import Task
from zou.app.utils import fields


class CreateFromImportTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_types()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_person()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_task()
        self.generate_fixture_comment()

    def test_create_from_import_list_skips_broken_rows(self):
        def entity_dict(entity_id, name, entity_type_id):
            return {
                "id": entity_id,
                "entities_out": [],
                "created_at": "2019-06-20T12:28:16",
                "updated_at": "2019-08-16T11:44:31",
                "name": name,
                "description": "",
                "canceled": False,
                "project_id": str(self.project.id),
                "entity_type_id": entity_type_id,
                "preview_file_id": None,
                "entities_in": [],
                "type": "Asset",
            }

        valid_type_id = str(self.asset_type_character.id)
        first_id = "11111111-3186-4405-8dc8-d6cb3a68ff1c"
        broken_id = "22222222-3186-4405-8dc8-d6cb3a68ff1c"
        last_id = "33333333-3186-4405-8dc8-d6cb3a68ff1c"

        # Simulate a broken row: a real FK violation would roll back the
        # test harness outer transaction, so raise from the import
        # instead (in production each row commits independently).
        original = Entity.create_from_import.__func__

        def flaky_import(data):
            if data["id"] == broken_id:
                raise IntegrityError("insert", {}, Exception("boom"))
            return original(Entity, data)

        with mock.patch.object(
            Entity, "create_from_import", side_effect=flaky_import
        ):
            Entity.create_from_import_list(
                [
                    entity_dict(first_id, "Lama", valid_type_id),
                    entity_dict(broken_id, "Broken", valid_type_id),
                    entity_dict(last_id, "Alpaga", valid_type_id),
                ]
            )
        self.assertIsNotNone(Entity.get(first_id))
        self.assertIsNone(Entity.get(broken_id))
        self.assertIsNotNone(Entity.get(last_id))

    def test_person(self):
        person_dict = {
            "departments": [],
            "id": "b86127df-909b-4bc2-983e-a959ea5a7319",
            "created_at": "2019-06-29T15:05:22",
            "updated_at": "2019-06-29T15:05:22",
            "first_name": "John",
            "last_name": "Doe",
            "email": "jhon01@example.com",
            "phone": "",
            "active": True,
            "desktop_login": "",
            "timezone": "Europe/Paris",
            "locale": "en_US",
            "role": "user",
            "has_avatar": True,
            "notifications_enabled": False,
            "notifications_slack_enabled": False,
            "notifications_slack_userid": None,
            "type": "Person",
            "full_name": "John Doe",
        }
        Person.create_from_import(person_dict)
        person = Person.get(person_dict["id"])
        self.assertEqual(person.first_name, person_dict["first_name"])

    def test_preview_file(self):
        preview_file_dict = {
            "id": "2b65b36d-a394-41f9-8415-9e92abeb0d49",
            "created_at": "2019-08-25T16:48:34",
            "updated_at": "2019-08-25T18:48:34",
            "name": "d7c1d6ec-b3e6",
            "original_name": "picture.png",
            "revision": 1,
            "source": "webgui",
            "extension": "png",
            "annotations": [],
            "task_id": str(self.task.id),
            "person_id": str(self.person.id),
            "source_file_id": None,
            "type": "PreviewFile",
            "comments": [self.comment["id"]],
            # Older Zou instances still send the dropped is_movie column.
            "is_movie": False,
        }
        PreviewFile.create_from_import(preview_file_dict)
        preview_file = PreviewFile.get(preview_file_dict["id"])
        self.assertEqual(preview_file.name, preview_file_dict["name"])

    def test_comment_keeps_its_person_mentions(self):
        comment_id = "5d3f6a2e-8b1c-4f0e-9a7d-2c4b6e8f0a1b"
        Comment.create_from_import(
            {
                "id": comment_id,
                "object_id": str(self.task.id),
                "object_type": "Task",
                "person_id": str(self.person.id),
                "task_status_id": str(self.task_status.id),
                "text": "hello",
                "mentions": [str(self.person.id)],
                "department_mentions": [],
                "type": "Comment",
            }
        )
        comment = Comment.get(comment_id)
        self.assertEqual(
            [str(person.id) for person in comment.mentions],
            [str(self.person.id)],
        )

    def test_comment_sets_its_relations_then_updates(self):
        preview_file = self.generate_fixture_preview_file()
        attachment_file = AttachmentFile.create(
            name="bug.png", size=42, extension="png", mimetype="image/png"
        )
        comment_id = str(fields.gen_uuid())

        def comment_dict(text):
            return {
                "id": comment_id,
                "object_id": str(self.task.id),
                "object_type": "Task",
                "person_id": str(self.person.id),
                "task_status_id": str(self.task_status.id),
                "text": text,
                "type": "Comment",
            }

        data = comment_dict("v1")
        data["previews"] = [str(preview_file.id), str(fields.gen_uuid())]
        data["acknowledgements"] = [str(self.person.id)]
        data["attachment_files"] = [str(attachment_file.id)]
        _, is_update = Comment.create_from_import(data)
        self.assertFalse(is_update)
        comment = Comment.get(comment_id)
        self.assertEqual(
            [str(p.id) for p in comment.previews], [str(preview_file.id)]
        )
        self.assertEqual(
            [str(p.id) for p in comment.acknowledgements],
            [str(self.person.id)],
        )
        self.assertEqual(
            [str(a.id) for a in comment.attachment_files],
            [str(attachment_file.id)],
        )

        data = comment_dict("v2")
        data["previews"] = []
        _, is_update = Comment.create_from_import(data)
        self.assertTrue(is_update)
        comment = Comment.get(comment_id)
        self.assertEqual(comment.text, "v2")
        self.assertEqual(comment.previews, [])
        # The keys left out of the payload keep their links.
        self.assertEqual(len(comment.acknowledgements), 1)
        self.assertEqual(len(comment.attachment_files), 1)

    def test_shot_sanitizes_its_import_data_then_updates(self):
        preview_file = self.generate_fixture_preview_file()
        shot_id = str(fields.gen_uuid())

        def shot_dict(name, entities_out):
            return {
                "id": shot_id,
                "name": name,
                "project_id": str(self.project.id),
                "project_name": "Cosmos Landromat",
                "episode_id": str(self.episode.id),
                "sequence_id": str(self.sequence.id),
                "sequence_name": "S01",
                "preview_file_id": str(preview_file.id),
                "data": {},
                "frame_in": 10,
                "frame_out": 50,
                "fps": 24,
                "entities_out": entities_out,
                "entities_in": [],
                "tasks": [],
                "type": "Shot",
            }

        _, is_update = Entity.create_from_import(
            shot_dict("P02", [str(self.asset.id), str(fields.gen_uuid())])
        )
        self.assertFalse(is_update)
        shot = Entity.get(shot_id)
        self.assertEqual(shot.entity_type_id, self.shot_type.id)
        self.assertEqual(shot.parent_id, self.sequence.id)
        self.assertEqual(shot.preview_file_id, preview_file.id)
        self.assertEqual(
            shot.data, {"frame_in": 10, "frame_out": 50, "fps": 24}
        )
        self.assertEqual(
            [str(e.id) for e in shot.entities_out], [str(self.asset.id)]
        )

        _, is_update = Entity.create_from_import(shot_dict("P02 bis", []))
        self.assertTrue(is_update)
        shot = Entity.get(shot_id)
        self.assertEqual(shot.name, "P02 bis")
        self.assertEqual(shot.entities_out, [])

    def test_asset_drops_an_unknown_or_empty_preview_file(self):
        def asset_dict(name, preview_file_id):
            return {
                "id": str(fields.gen_uuid()),
                "name": name,
                "project_id": str(self.project.id),
                "asset_type_id": str(self.asset_type_character.id),
                "asset_type_name": "Character",
                "preview_file_id": preview_file_id,
                "type": "Asset",
            }

        for name, preview_file_id in [
            ("Unknown preview", str(fields.gen_uuid())),
            ("Empty preview", ""),
        ]:
            asset, _ = Entity.create_from_import(
                asset_dict(name, preview_file_id)
            )
            asset = Entity.get(asset.id)
            self.assertEqual(
                asset.entity_type_id, self.asset_type_character.id
            )
            self.assertIsNone(asset.preview_file_id)

    def test_entity_link_drops_project_name_then_updates(self):
        def link_dict(label):
            return {
                "id": "726f9b44-526f-4fce-a979-6bf8bc8962a4",
                "entity_in_id": str(self.shot.id),
                "entity_out_id": str(self.asset.id),
                "nb_occurences": 1,
                "label": label,
                "project_name": "Cosmos Landromat",
                "type": "EntityLink",
            }

        _, is_update = EntityLink.create_from_import(link_dict("animation"))
        self.assertFalse(is_update)
        _, is_update = EntityLink.create_from_import(link_dict("layout"))
        self.assertTrue(is_update)
        links = EntityLink.get_all_by(entity_in_id=self.shot.id)
        self.assertEqual([link.label for link in links], ["layout"])

    def test_entity_type_sets_its_task_types_then_updates(self):
        entity_type_id = str(fields.gen_uuid())

        def entity_type_dict(name, task_type_ids):
            return {
                "id": entity_type_id,
                "name": name,
                "task_types": task_type_ids,
                "type": "AssetType",
            }

        def linked_task_type_ids():
            return {
                str(link.task_type_id)
                for link in TaskTypeAssetTypeLink.query.filter_by(
                    asset_type_id=entity_type_id
                )
            }

        _, is_update = EntityType.create_from_import(
            entity_type_dict(
                "Vehicle", [str(self.task_type.id), str(fields.gen_uuid())]
            )
        )
        self.assertFalse(is_update)
        self.assertEqual(linked_task_type_ids(), {str(self.task_type.id)})

        _, is_update = EntityType.create_from_import(
            entity_type_dict("Vehicles", [str(self.task_type_modeling.id)])
        )
        self.assertTrue(is_update)
        self.assertEqual(EntityType.get(entity_type_id).name, "Vehicles")
        self.assertEqual(
            linked_task_type_ids(), {str(self.task_type_modeling.id)}
        )

    def test_project_sets_its_links_then_updates(self):
        status_automation = self.generate_fixture_status_automation_to_status()
        background = self.generate_fixture_preview_background_file()
        project_id = str(fields.gen_uuid())

        def project_dict(name):
            return {
                "id": project_id,
                "name": name,
                "project_status_id": str(self.open_status.id),
                "project_status_name": "Open",
                "team": [str(self.person.id)],
                "task_types": [str(self.task_type.id)],
                "task_statuses": [str(self.task_status.id)],
                "asset_types": [str(self.asset_type_character.id)],
                "status_automations": [str(status_automation.id)],
                "preview_background_files": [str(background.id)],
                "type": "Project",
            }

        def linked_ids(link_class, column):
            return [
                str(getattr(link, column))
                for link in link_class.query.filter_by(project_id=project_id)
            ]

        _, is_update = Project.create_from_import(project_dict("Caminandes"))
        self.assertFalse(is_update)
        # Import twice: the links that exist must not be added again.
        _, is_update = Project.create_from_import(project_dict("Agent 327"))
        self.assertTrue(is_update)
        self.assertEqual(Project.get(project_id).name, "Agent 327")
        for link_class, column, expected_id in [
            (ProjectPersonLink, "person_id", self.person.id),
            (ProjectTaskTypeLink, "task_type_id", self.task_type.id),
            (ProjectTaskStatusLink, "task_status_id", self.task_status.id),
            (
                ProjectAssetTypeLink,
                "asset_type_id",
                self.asset_type_character.id,
            ),
            (
                ProjectStatusAutomationLink,
                "status_automation_id",
                status_automation.id,
            ),
            (
                ProjectPreviewBackgroundFileLink,
                "preview_background_file_id",
                background.id,
            ),
        ]:
            self.assertEqual(
                linked_ids(link_class, column), [str(expected_id)]
            )

    def test_task_skips_invalid_assignees_then_updates(self):
        task_id = str(fields.gen_uuid())

        def task_dict(name):
            return {
                "id": task_id,
                "name": name,
                "project_id": str(self.project.id),
                "task_type_id": str(self.task_type.id),
                "task_status_id": str(self.task_status.id),
                "entity_id": str(self.asset.id),
                "type": "Task",
            }

        data = task_dict("Import")
        data["assignees"] = [
            "unassigned",
            "not-an-id",
            str(fields.gen_uuid()),
            str(self.person.id),
        ]
        _, is_update = Task.create_from_import(data)
        self.assertFalse(is_update)
        self.assertEqual(
            [str(p.id) for p in Task.get(task_id).assignees],
            [str(self.person.id)],
        )

        # Without an assignees key, the update keeps the assignees.
        _, is_update = Task.create_from_import(task_dict("Import 2"))
        self.assertTrue(is_update)
        task = Task.get(task_id)
        self.assertEqual(task.name, "Import 2")
        self.assertEqual(
            [str(p.id) for p in task.assignees], [str(self.person.id)]
        )
