from tests.base import ApiDBTestCase
from zou.app.models.working_file import WorkingFile
from zou.app.services import projects_service, tasks_service
from zou.app.utils import fields


class WorkingFileTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.generate_data(
            WorkingFile,
            3,
            task_id=self.task.id,
            entity_id=self.asset.id,
            person_id=self.person.id,
            outputs=[],
        )

    def test_get_working_files(self):
        working_files = self.get("data/working-files")
        self.assertEqual(len(working_files), 3)

    def test_get_working_file(self):
        self.generate_fixture_user_cg_artist()
        user_cg_artist_id = self.user_cg_artist["id"]
        working_file = self.get_first("data/working-files")
        working_file["outputs"] = []
        working_file_again = self.get(
            f"data/working-files/{working_file['id']}"
        )
        self.assertEqual(working_file, working_file_again)
        self.get_404(f"data/working-files/{fields.gen_uuid()}")

        self.log_in_cg_artist()
        working_file_again = self.get(
            f"data/working-files/{working_file['id']}", 403
        )
        projects_service.add_team_member(self.project_id, user_cg_artist_id)
        working_file_again = self.get(
            f"data/working-files/{working_file['id']}"
        )

    def test_create_working_file(self):
        data = {
            "name": "Modeling working_file 1",
            "revision": 2,
            "comment": "Test comment",
            "size": 1024,
            "task_id": self.task.id,
            "entity_id": self.asset.id,
            "person_id": self.person.id,
        }
        self.working_file = self.post("data/working-files", data)
        self.assertIsNotNone(self.working_file["id"])

        working_files = self.get("data/working-files")
        self.assertEqual(len(working_files), 4)

    def test_update_working_file(self):
        working_file = self.get_first("data/working-files")
        data = {"name": "Super modeling working_file 2"}
        self.put(f"data/working-files/{working_file['id']}", data)
        working_file_again = self.get(
            f"data/working-files/{working_file['id']}"
        )
        self.assertEqual(data["name"], working_file_again["name"])
        self.put_404(f"data/working-files/{fields.gen_uuid()}", data)

    def test_update_validation_status(self):
        working_file = self.get_first("data/working-files")
        self.assertEqual(working_file["validation_status"], "neutral")
        data = {"validation_status": "validated"}
        self.put(f"data/working-files/{working_file['id']}", data)
        working_file_again = self.get(
            f"data/working-files/{working_file['id']}"
        )
        self.assertEqual(working_file_again["validation_status"], "validated")

    def test_update_validation_status_wrong_value(self):
        working_file = self.get_first("data/working-files")
        self.put(
            f"data/working-files/{working_file['id']}",
            {"validation_status": "maybe"},
            400,
        )

    def test_update_validation_status_permissions(self):
        self.generate_fixture_user_cg_artist()
        user_cg_artist_id = self.user_cg_artist["id"]
        projects_service.add_team_member(self.project_id, user_cg_artist_id)
        working_file = self.get_first("data/working-files")
        data = {"validation_status": "rejected"}

        self.log_in_cg_artist()
        self.put(f"data/working-files/{working_file['id']}", data, 403)
        tasks_service.assign_task(str(self.task.id), user_cg_artist_id)
        self.put(f"data/working-files/{working_file['id']}", data)

    def test_an_update_keeps_the_task_and_the_entity(self):
        working_file = self.get_first("data/working-files")
        self.generate_fixture_shot_task()
        path = f"data/working-files/{working_file['id']}"
        self.put(
            path,
            {
                "task_id": str(self.shot_task.id),
                "entity_id": str(self.shot.id),
            },
        )
        working_file_again = self.get(path)
        self.assertEqual(
            working_file_again["task_id"], working_file["task_id"]
        )
        self.assertEqual(
            working_file_again["entity_id"], working_file["entity_id"]
        )

    def test_an_update_keeps_the_output_files_on_their_source(self):
        working_file, other = self.get("data/working-files")[:2]
        self.generate_fixture_output_type()
        output_file = self.generate_fixture_output_file()
        output_file.update({"source_file_id": working_file["id"]})
        other_output_file = self.generate_fixture_output_file(name="other")
        other_output_file.update({"source_file_id": other["id"]})
        self.put(
            f"data/working-files/{working_file['id']}",
            {"outputs": [str(other_output_file.id)]},
        )
        sources = [
            self.get(f"data/output-files/{output.id}")["source_file_id"]
            for output in [output_file, other_output_file]
        ]
        self.assertEqual(sources, [working_file["id"], other["id"]])

    def author_is_changed_by(self, role=None):
        """
        Have an assignee of the task, with given role on the project, set
        themselves as the author of a working file.
        """
        working_file = self.get_first("data/working-files")
        member_id = self.generate_fixture_user_cg_artist()["id"]
        projects_service.add_team_member(self.project_id, member_id, role)
        tasks_service.assign_task(str(self.task.id), member_id)
        self.log_in_cg_artist()
        path = f"data/working-files/{working_file['id']}"
        self.put(path, {"person_id": member_id})
        return self.get(path)["person_id"] == member_id

    def test_an_artist_keeps_the_author_of_a_working_file(self):
        self.assertFalse(self.author_is_changed_by())

    def test_a_project_manager_changes_the_author_of_a_working_file(self):
        self.assertTrue(self.author_is_changed_by("manager"))

    def test_delete_working_file(self):
        working_files = self.get("data/working-files")
        self.assertEqual(len(working_files), 3)
        working_file = working_files[0]
        self.delete(f"data/working-files/{working_file['id']}")
        working_files = self.get("data/working-files")
        self.assertEqual(len(working_files), 2)
        self.delete_404(f"data/working-files/{fields.gen_uuid()}")
