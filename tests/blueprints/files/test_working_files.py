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

    def test_an_artist_files_as_themselves(self):
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project.id, self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()
        working_file = self.post(
            f"/data/tasks/{self.task_id}/working-files/new",
            {"name": "theirs", "person_id": self.user["id"]},
        )
        self.assertEqual(working_file["person_id"], self.user_cg_artist["id"])

    def test_a_client_creates_no_working_file(self):
        client_id = self.generate_fixture_user_cg_artist()["id"]
        projects_service.add_team_member(self.project.id, client_id, "client")
        self.log_in_cg_artist()
        self.post(
            f"/data/tasks/{self.task_id}/working-files/new",
            {"name": "theirs"},
            403,
        )
        task = Task.get(self.task_id)
        self.assertNotIn(
            client_id, [str(person.id) for person in task.assignees]
        )

    def test_a_client_creates_no_default_software(self):
        Software.get_by(name="Blender").update({"name": "Blender 4"})
        client_id = self.generate_fixture_user_cg_artist()["id"]
        projects_service.add_team_member(self.project.id, client_id, "client")
        self.log_in_cg_artist()
        self.post(
            f"/data/tasks/{self.task_id}/working-files/new",
            {"name": "theirs"},
            403,
        )
        self.assertIsNone(Software.get_by(name="Blender"))

    def test_new_working_file(self):
        task = Task.get(self.task_id)
        self.assertEqual(len(task.assignees), 1)
        self.assertNotEqual(self.user["id"], str(task.assignees[0].id))

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

        assignees = [person.serialize() for person in task.assignees]
        assignees = sorted(assignees, key=lambda x: x["last_name"])

        self.assertEqual(self.user["id"], assignees[0]["id"])

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

    def test_new_working_file_with_a_separator(self):
        working_file = self.post(
            f"/data/tasks/{self.task_id}/working-files/new",
            {"name": "main", "sep": "\\"},
        )
        self.assertEqual(
            working_file["path"],
            "/simple\\productions\\cosmos_landromat\\assets\\props\\tree\\"
            "shaders\\blender\\cosmos_landromat_props_tree_shaders_main_v001",
        )

    def test_create_same_working_file(self):
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
        path = f"/data/working-files/{working_file.id}/file"
        fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )

        self.assertIsNone(working_file.uploaded_at)
        uploaded = self.upload_file(path, fixture)
        self.assertIsNotNone(uploaded["uploaded_at"])
        self.assertEqual(uploaded["size"], os.path.getsize(fixture))
        stored = self.get(f"data/working-files/{working_file.id}")
        self.assertEqual(stored["uploaded_at"], uploaded["uploaded_at"])

        response = self.app.get(path, headers=self.base_headers)
        self.assertEqual(response.status_code, 200)
        with open(fixture, "rb") as f:
            self.assertEqual(response.data, f.read())

    def test_a_working_file_without_binary_is_a_404(self):
        # The storage lookup used to sit outside the try, so a missing
        # binary surfaced as a 500.
        working_file = self.generate_fixture_working_file()
        self.get(f"/data/working-files/{working_file.id}/file", 404)

    def test_working_file_needs_project_access(self):
        working_file = self.generate_fixture_working_file()
        path = f"/data/working-files/{working_file.id}/file"

        # Assigned, but out of the team: the team check alone refuses.
        artist = self.generate_fixture_user_cg_artist()
        self.assign_task(self.task.id, artist["id"])
        self.log_in_cg_artist()
        self.get(path, 403)

    def download_as_artist(self, role=None, task_id=None, cast=False):
        import os

        from zou.app.services import breakdown_service, tasks_service

        working_file = self.generate_fixture_working_file()
        path = f"/data/working-files/{working_file.id}/file"
        fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        self.upload_file(path, fixture)
        if cast:
            breakdown_service.update_casting(
                self.shot.id, [{"asset_id": self.asset.id, "nb_occurences": 1}]
            )
        artist_id = self.generate_fixture_user_cg_artist()["id"]
        projects_service.add_team_member(self.project.id, artist_id, role)
        if task_id is not None:
            tasks_service.assign_task(task_id, artist_id)
        self.log_in_cg_artist()
        return self.app.get(path, headers=self.base_headers).status_code

    def test_an_artist_downloads_any_working_file_of_the_project(self):
        self.assertEqual(
            self.download_as_artist(task_id=self.shot_task.id), 200
        )

    def test_a_vendor_downloads_the_working_file_of_their_entity(self):
        self.assertEqual(
            self.download_as_artist("vendor", task_id=self.task.id), 200
        )

    def test_a_vendor_downloads_the_working_file_of_an_asset_cast(self):
        self.assertEqual(
            self.download_as_artist(
                "vendor", task_id=self.shot_task.id, cast=True
            ),
            200,
        )

    def test_a_vendor_downloads_no_working_file_of_an_asset_not_cast(self):
        self.assertEqual(
            self.download_as_artist("vendor", task_id=self.shot_task.id), 403
        )

    def test_a_client_downloads_no_working_file(self):
        self.assertEqual(
            self.download_as_artist("client", task_id=self.task.id), 403
        )

    def test_a_supervisor_of_the_project_downloads_any_working_file(self):
        self.assertEqual(self.download_as_artist("supervisor"), 200)

    def upload_as_artist(self, role=None, task_id=None):
        import os

        working_file = self.generate_fixture_working_file()
        path = f"/data/working-files/{working_file.id}/file"
        fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        artist_id = self.generate_fixture_user_cg_artist()["id"]
        projects_service.add_team_member(self.project.id, artist_id, role)
        if task_id is not None:
            self.assign_task(task_id, artist_id)
        self.log_in_cg_artist()
        with open(fixture, "rb") as file_content:
            response = self.app.post(
                path,
                data={"file": (file_content, "th01.png")},
                headers=self.base_headers,
            )
        return response.status_code

    def test_an_artist_stores_the_working_file_of_their_task(self):
        self.assertEqual(self.upload_as_artist(task_id=self.task.id), 201)

    def test_an_artist_stores_no_working_file_of_another_task(self):
        self.assertEqual(self.upload_as_artist(task_id=self.shot_task.id), 403)

    def test_a_client_stores_no_working_file(self):
        self.assertEqual(
            self.upload_as_artist("client", task_id=self.task.id), 403
        )

    def test_a_supervisor_with_no_department_stores_any_working_file(self):
        self.assertEqual(self.upload_as_artist("supervisor"), 201)

    def test_a_manager_of_the_project_stores_any_working_file(self):
        self.assertEqual(self.upload_as_artist("manager"), 201)
