import datetime

from tests.base import ApiDBTestCase

from zou.app.models.software import Software
from zou.app.models.task import Task
from zou.app.services import projects_service


class WorkingFilesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        self.generate_fixture_shot_working_file()
        self.generate_fixture_output_type()
        self.generate_fixture_output_file()
        self.maxDiff = None
        self.task_id = self.task.id

    def test_get_last_working_files(self):
        self.generate_fixture_working_file(name="main", revision=1)
        self.generate_fixture_working_file(name="main", revision=2)
        self.generate_fixture_working_file(name="main", revision=3)
        self.generate_fixture_working_file(name="main", revision=4)
        working_file_main = self.generate_fixture_working_file(
            name="main", revision=5
        )

        self.generate_fixture_working_file(name="hotfix", revision=1)
        self.generate_fixture_working_file(name="hotfix", revision=2)
        working_file_hotfix = self.generate_fixture_working_file(
            name="hotfix", revision=3
        )
        working_file_wip = self.generate_fixture_working_file(
            name="wip", revision=1
        )

        working_files = self.get(
            f"/data/tasks/{self.task.id}/working-files/last-revisions"
        )
        self.assertEqual(working_files["main"], working_file_main.serialize())
        self.assertEqual(
            working_files["hotfix"], working_file_hotfix.serialize()
        )
        self.assertEqual(working_files["wip"], working_file_wip.serialize())

    def test_new_working_file(self):
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.assign_task(self.task_id, self.user_cg_artist["id"])
        self.log_in_cg_artist()

        path = f"/data/tasks/{self.task_id}/working-files/new"
        working_file = self.post(
            path,
            {
                "name": "main",
                "description": "description test",
                "comment": "comment test",
            },
        )
        self.assertEqual(working_file["revision"], 1)
        task = Task.get(self.task_id)

        self.assertEqual(len(task.assignees), 2)

        task = Task.get(self.task_id)
        path = f"/data/tasks/{self.task_id}/working-files/new"
        working_file = self.post(
            path,
            {
                "name": "main",
                "description": "description test",
                "comment": "comment test",
            },
        )
        self.assertEqual(working_file["revision"], 2)

        working_file = self.post(
            path,
            {
                "name": "main",
                "description": "description test",
                "comment": "comment test",
            },
        )
        self.assertEqual(working_file["revision"], 3)
        self.assertEqual(
            working_file["path"],
            "/simple/productions/cosmos_landromat/assets/props/tree/shaders/"
            "blender/cosmos_landromat_props_tree_shaders_main_v003",
        )

        working_file = self.post(
            path,
            {
                "name": "main",
                "description": "description test",
                "comment": "comment test",
                "revision": 66,
            },
        )
        self.assertEqual(working_file["revision"], 66)
        self.assertEqual(
            working_file["path"],
            "/simple/productions/cosmos_landromat/assets/props/tree/shaders/"
            "blender/cosmos_landromat_props_tree_shaders_main_v066",
        )

    def test_create_same_working_file(self):
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.assign_task(self.task_id, self.user_cg_artist["id"])
        self.log_in_cg_artist()
        path = f"/data/tasks/{self.task_id}/working-files/new"
        self.post(
            path,
            {
                "name": "main",
                "description": "description test",
                "comment": "comment test",
                "revision": 66,
            },
        )
        self.post(
            path,
            {
                "name": "main",
                "description": "description test",
                "comment": "comment test",
                "revision": 66,
            },
            400,
        )

    def test_update_modification_date(self):
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.assign_task(self.working_file.task_id, self.user_cg_artist["id"])
        self.log_in_cg_artist()
        path = f"/actions/working-files/{self.working_file.id}/modified"
        past = datetime.datetime.now(tz=datetime.timezone.utc).replace(
            microsecond=0, tzinfo=None
        ) - datetime.timedelta(seconds=2)
        self.working_file.update({"updated_at": past})
        previous_date = self.working_file.serialize()["updated_at"]
        working_file = self.put(path, {})
        current_date = working_file["updated_at"]
        self.assertLess(previous_date, current_date)

        now = self.now()
        self.assertLessEqual(current_date, now)

    def test_get_untyped_file(self):
        working_file_id = str(self.working_file.id)
        output_file_id = str(self.output_file.id)

        path = f"/data/files/{working_file_id}"
        remote_file = self.get(path)
        self.assertEqual(remote_file["id"], working_file_id)
        self.assertEqual(remote_file["type"], "WorkingFile")

        path = f"/data/files/{output_file_id}"
        remote_file = self.get(path)
        self.assertEqual(remote_file["id"], output_file_id)
        self.assertEqual(remote_file["type"], "OutputFile")

        path = f"/data/files/{self.task_id}"
        self.get(path, 404)

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        path = f"/data/files/{output_file_id}"
        self.get(path, 403)
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.get(path)

    def test_comment_working_file(self):
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.assign_task(self.working_file.task_id, self.user_cg_artist["id"])
        self.log_in_cg_artist()
        comment_data = {"comment": "test working file comment"}
        self.put(
            f"/actions/working-files/{self.working_file.id}/comment",
            comment_data,
        )
        working_file = self.get(f"data/working-files/{self.working_file.id}")
        self.assertEqual(working_file["comment"], comment_data["comment"])

    def test_update_working_file_permission(self):
        working_file = self.working_file.serialize()
        self.generate_fixture_user_cg_artist()
        user = self.user_cg_artist
        self.log_in_cg_artist()
        comment_data = {"comment": "test working file comment"}

        self.put(
            f"/actions/working-files/{working_file['id']}/comment",
            comment_data,
            403,
        )
        projects_service.add_team_member(self.project_id, user["id"])
        self.assign_task(working_file["task_id"], user["id"])
        self.put(
            f"/actions/working-files/{working_file['id']}/comment",
            comment_data,
        )
        working_file = self.get(f"data/working-files/{working_file['id']}")
        self.assertEqual(working_file["comment"], comment_data["comment"])

    def test_comment_working_wrong_data(self):
        comment_data = {"comment_wrong": "test working file comment"}
        self.put(
            f"/actions/working-files/{self.working_file.id}/comment",
            comment_data,
            400,
        )

    def test_get_working_files_for_entity(self):
        entity_id = str(self.asset.id)
        self.generate_fixture_working_file(name="test_file_for_entity")
        self.generate_fixture_working_file(name="test_file_for_entity_02")
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()
        self.asset = self.asset_character
        self.generate_fixture_task()
        self.generate_fixture_working_file(name="test_file_for_character")

        new_files = self.get(f"/data/entities/{entity_id}/working-files")

        self.assertEqual(len(new_files), 2)
        for new_file in new_files:
            self.assertEqual(new_file["entity_id"], entity_id)

    def test_working_file_round_trip(self):
        """
        The two verbs of the file route: the DCC pushes the scene file, then
        anyone with access to the task pulls it back.
        """
        import os

        working_file = self.generate_fixture_working_file()
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.assign_task(working_file.task_id, self.user_cg_artist["id"])
        self.log_in_cg_artist()
        path = f"/data/working-files/{working_file.id}/file"
        fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )

        self.upload_file(path, fixture)

        response = self.app.get(path, headers=self.base_headers)
        self.assertEqual(response.status_code, 200)
        with open(fixture, "rb") as f:
            self.assertEqual(response.data, f.read())

    def test_a_working_file_without_binary_is_a_404(self):
        # The storage lookup used to sit outside the try, so a missing
        # binary surfaced as a 500.
        working_file = self.generate_fixture_working_file()
        self.get(f"/data/working-files/{working_file.id}/file", 404)

    def test_working_file_needs_task_access(self):
        import os

        working_file = self.generate_fixture_working_file()
        path = f"/data/working-files/{working_file.id}/file"

        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()
        self.get(path, 403)
        fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        self.upload_file(path, fixture, 403)

    def test_unassigned_project_artist_cannot_read_or_submit_working_files(
        self,
    ):
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()

        three_ds_max_count = Software.query.filter_by(name="3ds Max").count()
        self.get(
            f"/data/tasks/{self.task_id}/working-files", 403
        )
        self.get(
            f"/data/tasks/{self.task_id}/working-files/last-revisions", 403
        )
        self.get(f"/data/entities/{self.asset.id}/working-files", 403)
        self.get(f"/data/working-files?entity_id={self.asset.id}", 403)
        self.post(
            f"/data/tasks/{self.task_id}/working-file-path",
            {"name": "unauthorized"},
            403,
        )
        self.assertEqual(
            Software.query.filter_by(name="3ds Max").count(),
            three_ds_max_count,
        )
        self.post(
            f"/data/tasks/{self.task_id}/working-files/new",
            {"name": "main", "description": "description test"},
            403,
        )
        self.assertNotIn(
            self.user_cg_artist["id"],
            [str(person.id) for person in Task.get(self.task_id).assignees],
        )

    def assert_working_file_upload_denied(self):
        import os

        fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        path = f"/data/working-files/{self.working_file.id}/file"
        self.upload_file(path, fixture, 403)

    def test_client_cannot_read_or_submit_working_files(self):
        self.generate_fixture_user_client()
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        self.log_in_client()

        self.get(
            f"/data/tasks/{self.task_id}/working-files", 403
        )
        self.get(
            f"/data/tasks/{self.task_id}/working-files/last-revisions", 403
        )
        self.post(
            f"/data/tasks/{self.task_id}/working-files/new",
            {"name": "main", "description": "description test"},
            403,
        )
        self.assert_working_file_upload_denied()

    def test_project_manager_can_read_but_cannot_submit_working_files(self):
        self.generate_fixture_user_manager()
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        self.log_in_manager()

        self.get("/data/working-files", 403)
        self.assertEqual(
            self.get(f"/data/tasks/{self.task_id}/working-files"), []
        )
        self.post(
            f"/data/tasks/{self.task_id}/working-files/new",
            {"name": "main", "description": "description test"},
            403,
        )
        self.assert_working_file_upload_denied()

    def test_supervisor_without_task_assignment_is_denied(self):
        self.generate_fixture_user_supervisor()
        projects_service.add_team_member(
            self.project_id, self.user_supervisor["id"]
        )
        self.log_in_supervisor()

        self.get(f"/data/tasks/{self.task_id}/working-files", 403)
        self.get(f"/data/working-files?entity_id={self.asset.id}", 403)
        self.post(
            f"/data/tasks/{self.task_id}/working-files/new",
            {"name": "main", "description": "description test"},
            403,
        )
        self.assert_working_file_upload_denied()

    def test_assigned_supervisor_can_read_but_cannot_write_working_files(
        self,
    ):
        import os

        working_file = self.generate_fixture_working_file()
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.assign_task(self.task_id, self.user_cg_artist["id"])
        self.log_in_cg_artist()
        fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        file_path = f"/data/working-files/{working_file.id}/file"
        self.upload_file(file_path, fixture)

        self.generate_fixture_user_supervisor()
        projects_service.add_team_member(
            self.project_id, self.user_supervisor["id"]
        )
        self.assign_task(self.task_id, self.user_supervisor["id"])
        self.log_in_supervisor()

        self.get(f"/data/tasks/{self.task_id}/working-files")
        self.get(f"/data/working-files/{working_file.id}")
        response = self.app.get(file_path, headers=self.base_headers)
        self.assertEqual(response.status_code, 200)
        with open(fixture, "rb") as file_handle:
            self.assertEqual(response.data, file_handle.read())
        self.put(
            f"/data/working-files/{working_file.id}",
            {"comment": "supervisor write denied"},
            403,
        )
        self.post(
            f"/data/tasks/{self.task_id}/working-files/new",
            {"name": "main", "description": "description test"},
            403,
        )
        self.assert_working_file_upload_denied()

    def test_admin_can_read_but_cannot_submit_working_files(self):
        self.get(f"/data/tasks/{self.task_id}/working-files")
        self.post(
            f"/data/tasks/{self.task_id}/working-files/new",
            {"name": "main", "description": "description test"},
            403,
        )
        self.post(
            "/data/working-files",
            {"task_id": self.task_id, "entity_id": self.asset.id},
            403,
        )
        self.assert_working_file_upload_denied()

    def test_assigned_artist_can_read_and_create_without_auto_assignment(
        self,
    ):
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.assign_task(self.task_id, self.user_cg_artist["id"])
        self.log_in_cg_artist()

        self.assertEqual(
            self.get(f"/data/tasks/{self.task_id}/working-files"), []
        )
        self.assertEqual(
            self.get(
                f"/data/entities/{self.asset.id}/working-files"
                f"?task_id={self.task_id}"
            ),
            [],
        )
        path_result = self.post(
            f"/data/tasks/{self.task_id}/working-file-path",
            {"name": "main"},
        )
        self.assertIn("path", path_result)
        self.post(
            f"/data/tasks/{self.task_id}/working-files/new",
            {
                "name": "main",
                "description": "description test",
                "person_id": self.user_cg_artist["id"],
            },
        )
        self.assertEqual(len(Task.get(self.task_id).assignees), 2)

    def test_assigned_artist_cannot_spoof_working_file_owner(self):
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.assign_task(self.task_id, self.user_cg_artist["id"])
        self.log_in_cg_artist()

        self.post(
            f"/data/tasks/{self.task_id}/working-files/new",
            {
                "name": "main",
                "description": "description test",
                "person_id": self.user["id"],
            },
            403,
        )

    def test_working_file_id_is_authorized_against_its_own_task(self):
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.assign_task(self.task_id, self.user_cg_artist["id"])
        self.generate_fixture_task(name="Other task")
        other_working_file = self.generate_fixture_working_file(name="other")
        self.log_in_cg_artist()

        self.get(f"/data/files/{other_working_file.id}", 403)
        self.get(f"/data/working-files/{other_working_file.id}", 403)
        self.put(
            f"/data/working-files/{other_working_file.id}",
            {"comment": "cross-task update"},
            403,
        )
        self.get(
            f"/data/working-files/{other_working_file.id}/file", 403
        )

    def test_generic_working_file_api_requires_task_assignment_scope(self):
        working_file = self.generate_fixture_working_file()
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()

        self.get("/data/working-files", 403)
        self.get(f"/data/working-files?task_id={self.task_id}", 403)
        self.get(f"/data/working-files/{working_file.id}", 403)
        self.put(
            f"/data/working-files/{working_file.id}",
            {"comment": "unauthorized"},
            403,
        )

        self.assign_task(self.task_id, self.user_cg_artist["id"])
        self.get("/data/working-files", 403)
        self.get(f"/data/working-files?task_id={self.task_id}")
        self.get(f"/data/working-files/{working_file.id}")

    def test_manager_can_query_working_files_by_entity(self):
        self.generate_fixture_working_file()
        self.generate_fixture_user_manager()
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        self.log_in_manager()

        self.get(f"/data/working-files?entity_id={self.asset.id}")

    def test_client_cannot_query_generic_working_file_api(self):
        self.generate_fixture_user_client()
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        self.log_in_client()

        self.get("/data/working-files", 403)
        self.get(f"/data/working-files?task_id={self.task_id}", 403)
        self.get(f"/data/working-files/{self.working_file.id}", 403)
