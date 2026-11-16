from tests.base import ApiDBTestCase
from zou.app.models.output_file import OutputFile
from zou.app.services import projects_service, tasks_service
from zou.app.utils import events, fields


class OutputFileTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.generate_fixture_file_status()
        self.generate_data(
            OutputFile,
            3,
            task_id=self.task.id,
            entity_id=self.asset.id,
            person_id=self.person.id,
            file_status_id=self.file_status.id,
        )

        self.project_id = str(self.project.id)
        events.register("output-file:new", "handle_event", self)
        events.register("output-file:update", "handle_event", self)
        events.register("output-file:delete", "handle_event", self)

    def handle_event(self, data={}):
        self.last_event_data = data

    def test_get_output_files(self):
        output_files = self.get("data/output-files")
        self.assertEqual(len(output_files), 3)

    def test_get_output_files_as_a_vendor_of_this_project_only(self):
        artist_id = self.generate_fixture_user_cg_artist()["id"]
        projects_service.add_team_member(self.project.id, artist_id, "vendor")
        self.log_in_cg_artist()
        self.assertEqual(self.get("data/output-files"), [])

    def test_get_output_file(self):
        output_file = self.get_first("data/output-files")
        output_file_again = self.get(f"data/output-files/{output_file['id']}")
        self.assertEqual(output_file, output_file_again)
        self.get_404(f"data/output-files/{fields.gen_uuid()}")

    def test_create_output_file(self):
        data = {
            "name": "Modeling output_file 1",
            "revision": 2,
            "comment": "Test comment",
            "size": 1024,
            "person_id": self.person.id,
            "file_status_id": self.file_status.id,
            "entity_id": self.asset.id,
        }
        self.file_status_id = self.file_status.id
        self.output_file = self.post("data/output-files", data)
        self.assertIsNotNone(self.output_file["id"])

        output_files = self.get("data/output-files")
        self.assertEqual(len(output_files), 4)
        self.assertEqual(
            self.last_event_data["output_file_id"], self.output_file["id"]
        )
        self.assertEqual(self.last_event_data["project_id"], self.project_id)

    def test_update_quality(self):
        output_file = self.get_first("data/output-files")
        self.assertIsNone(output_file["quality"])
        self.put(f"data/output-files/{output_file['id']}", {"quality": "high"})
        output_file_again = self.get(f"data/output-files/{output_file['id']}")
        self.assertEqual(output_file_again["quality"], "high")

        self.put(f"data/output-files/{output_file['id']}", {"quality": None})
        output_file_again = self.get(f"data/output-files/{output_file['id']}")
        self.assertIsNone(output_file_again["quality"])

    def test_update_quality_wrong_value(self):
        output_file = self.get_first("data/output-files")
        self.put(
            f"data/output-files/{output_file['id']}", {"quality": "ultra"}, 400
        )

    def test_update_quality_permissions(self):
        self.generate_fixture_user_cg_artist()
        user_cg_artist_id = self.user_cg_artist["id"]
        projects_service.add_team_member(self.project_id, user_cg_artist_id)
        output_file = self.get_first("data/output-files")
        data = {"quality": "low"}

        self.log_in_cg_artist()
        self.put(f"data/output-files/{output_file['id']}", data, 403)
        tasks_service.assign_task(str(self.task.id), user_cg_artist_id)
        self.put(f"data/output-files/{output_file['id']}", data)

    def update_as_assignee(self, code, role=None, in_team=True):
        output_file = self.get_first("data/output-files")
        member_id = self.generate_fixture_user_cg_artist()["id"]
        if in_team:
            projects_service.add_team_member(self.project_id, member_id, role)
        tasks_service.assign_task(str(self.task.id), member_id)
        self.log_in_cg_artist()
        self.put(
            f"data/output-files/{output_file['id']}", {"quality": "low"}, code
        )

    def test_an_assignee_out_of_the_team_updates_no_output_file(self):
        self.update_as_assignee(403, in_team=False)

    def test_a_client_of_the_project_updates_no_output_file(self):
        self.update_as_assignee(403, role="client")

    def test_update_output_file(self):
        output_file = self.get_first("data/output-files")
        data = {"name": "Super modeling output_file 2"}
        self.put(f"data/output-files/{output_file['id']}", data)
        output_file_again = self.get(f"data/output-files/{output_file['id']}")
        self.assertEqual(data["name"], output_file_again["name"])
        self.assertEqual(
            self.last_event_data["output_file_id"], output_file["id"]
        )
        self.assertEqual(self.last_event_data["project_id"], self.project_id)

        self.put_404(f"data/output-files/{fields.gen_uuid()}", data)

    def test_an_update_keeps_the_links_of_an_output_file(self):
        output_file = self.get_first("data/output-files")
        self.generate_fixture_scene()
        self.generate_fixture_scene_asset_instance()
        working_file = self.generate_fixture_working_file()
        path = f"data/output-files/{output_file['id']}"
        self.put(
            path,
            {
                "entity_id": str(self.shot.id),
                "temporal_entity_id": str(self.shot.id),
                "asset_instance_id": str(self.asset_instance.id),
                "source_file_id": str(working_file.id),
            },
        )
        output_file_again = self.get(path)
        for field in [
            "entity_id",
            "temporal_entity_id",
            "asset_instance_id",
            "source_file_id",
        ]:
            self.assertEqual(output_file_again[field], output_file[field])

    def author_is_changed_by(self, role=None):
        """
        Have an assignee of a task of the entity, with given role on the
        project, set themselves as the author of an output file.
        """
        output_file = self.get_first("data/output-files")
        member_id = self.generate_fixture_user_cg_artist()["id"]
        projects_service.add_team_member(self.project_id, member_id, role)
        tasks_service.assign_task(str(self.task.id), member_id)
        self.log_in_cg_artist()
        path = f"data/output-files/{output_file['id']}"
        self.put(path, {"person_id": member_id})
        return self.get(path)["person_id"] == member_id

    def test_an_artist_keeps_the_author_of_an_output_file(self):
        self.assertFalse(self.author_is_changed_by())

    def test_a_project_manager_changes_the_author_of_an_output_file(self):
        self.assertTrue(self.author_is_changed_by("manager"))

    def test_delete_output_file(self):
        output_files = self.get("data/output-files")
        self.assertEqual(len(output_files), 3)
        output_file = output_files[0]
        self.delete(f"data/output-files/{output_file['id']}")
        output_files = self.get("data/output-files")
        self.assertEqual(len(output_files), 2)
        self.assertEqual(
            self.last_event_data["output_file_id"], output_file["id"]
        )
        self.assertEqual(self.last_event_data["project_id"], self.project_id)

        self.delete_404(f"data/output-files/{fields.gen_uuid()}")

    def test_get_output_file_permission(self):
        output_file_id = self.get_first("data/output-files")["id"]
        self.generate_fixture_user_cg_artist()
        cg_artist_id = self.user_cg_artist["id"]
        self.log_in_cg_artist()
        output_files = self.get("data/output-files")
        self.assertEqual(output_files, [])
        self.get(f"data/output-files/{output_file_id}", 403)

        projects_service.add_team_member(self.project_id, cg_artist_id)
        self.get(f"data/output-files/{output_file_id}")
        output_files = self.get("data/output-files")
        self.assertEqual(len(output_files), 3)
