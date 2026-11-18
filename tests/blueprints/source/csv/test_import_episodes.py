import os
import tempfile

from tests.base import ApiDBTestCase
from zou.app.models.comment import Comment
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.services import projects_service, shots_service


class ImportCsvEpisodesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.project.update({"production_type": "tvshow"})
        self.path = f"/import/csv/projects/{self.project.id}/episodes"

    def write_csv(self, content):
        descriptor, file_path = tempfile.mkstemp(suffix=".csv")
        self.addCleanup(os.remove, file_path)
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as f:
            f.write(content)
        return file_path

    def get_episodes(self):
        return shots_service.get_episodes({"project_id": self.project.id})

    def test_import_episodes(self):
        self.upload_file(
            self.path, self.write_csv("Name,Description\nE01,Pilot\n")
        )

        self.assertEqual(
            [
                (episode["name"], episode["description"], episode["status"])
                for episode in self.get_episodes()
            ],
            [("E01", "Pilot", "running")],
        )

    def test_import_reads_the_status_in_any_case(self):
        self.upload_file(
            self.path,
            self.write_csv("Name,Status\nE01,Complete\nE02, standby\nE03,\n"),
        )

        self.assertEqual(
            [
                (episode["name"], episode["status"])
                for episode in self.get_episodes()
            ],
            [("E01", "complete"), ("E02", "standby"), ("E03", "running")],
        )

    def test_an_unknown_status_is_refused(self):
        # It became "running" without a word.
        result = self.upload_file(
            self.path,
            self.write_csv("Name,Status\nE01,running\nE02,En cours\n"),
            code=400,
        )

        self.assertEqual(result["line_number"], 3)
        self.assertEqual(
            result["message"], "Episode status not found for En cours"
        )
        self.assertEqual(result["imported_rows"], 1)
        self.assertEqual(
            [episode["name"] for episode in self.get_episodes()], ["E01"]
        )

    def test_an_existing_episode_changes_with_the_update_option_only(self):
        self.upload_file(self.path, self.write_csv("Name,Status\nE01,\n"))
        self.upload_file(
            self.path, self.write_csv("Name,Status\nE01,canceled\n")
        )
        self.assertEqual(
            [episode["status"] for episode in self.get_episodes()],
            ["running"],
        )

        self.upload_file(
            f"{self.path}?update=true",
            self.write_csv("Name,Status\nE01,canceled\n"),
        )
        self.assertEqual(
            [episode["status"] for episode in self.get_episodes()],
            ["canceled"],
        )

        # An empty status cell leaves the status as it is.
        self.upload_file(
            f"{self.path}?update=true",
            self.write_csv("Name,Status,Description\nE01,,Night\n"),
        )
        self.assertEqual(
            [
                (episode["status"], episode["description"])
                for episode in self.get_episodes()
            ],
            [("canceled", "Night")],
        )

    def test_import_is_refused_outside_a_tv_show(self):
        self.project.update({"production_type": "short"})
        result = self.upload_file(
            self.path, self.write_csv("Name\nE01\n"), code=400
        )

        self.assertEqual(
            result["message"], "Episodes can only be imported in a TV show"
        )
        self.assertEqual(self.get_episodes(), [])

    def test_a_line_without_name_is_refused(self):
        result = self.upload_file(
            self.path, self.write_csv("Name,Description\n,Pilot\n"), code=400
        )

        self.assertEqual(result["message"], "Name cannot be empty")
        self.assertEqual(self.get_episodes(), [])

    def test_import_reads_the_metadata_columns(self):
        self.generate_fixture_metadata_descriptor(entity_type="Episode")
        self.upload_file(
            self.path, self.write_csv("Name,Contractor\nE01,value 1\n")
        )

        self.assertEqual(
            self.get_episodes()[0]["data"], {"contractor": "value 1"}
        )

    def test_import_sets_the_status_comment_and_assignees_of_a_task(self):
        task_type = TaskType.create(
            name="Script",
            short_name="scr",
            color="#FFFFFF",
            for_entity="Episode",
        )
        projects_service.add_task_type_setting(self.project.id, task_type.id)
        self.generate_fixture_task_status_wip()
        self.generate_fixture_person()
        self.upload_file(
            self.path,
            self.write_csv(
                "Name,Script,Script comment,Script assignations\n"
                "E01,wip,First draft,John Doe\n"
                "E02,,,\n"
            ),
        )

        tasks = {
            shots_service.get_episode(str(task.entity_id))["name"]: task
            for task in Task.query.all()
        }
        self.assertEqual(sorted(tasks), ["E01", "E02"])
        self.assertEqual(tasks["E01"].task_type_id, task_type.id)
        self.assertEqual(tasks["E01"].task_status_id, self.task_status_wip.id)
        self.assertEqual(
            [person.id for person in tasks["E01"].assignees],
            [self.person.id],
        )
        self.assertEqual(
            [comment.text for comment in Comment.query.all()], ["First draft"]
        )

    def test_an_update_assigns_only_the_people_not_yet_assigned(self):
        task_type = TaskType.create(
            name="Script",
            short_name="scr",
            color="#FFFFFF",
            for_entity="Episode",
        )
        projects_service.add_task_type_setting(self.project.id, task_type.id)
        self.generate_fixture_person()
        self.upload_file(
            self.path,
            self.write_csv("Name,Script assignations\nE01,John Doe\n"),
        )

        assigned = self.capture_events("task:assign")
        self.upload_file(
            f"{self.path}?update=true",
            self.write_csv(
                'Name,Script assignations\nE01,"John Doe, John Did"\n'
            ),
        )

        self.assertEqual(
            [str(event["person_id"]) for event in assigned], [self.user["id"]]
        )
        self.assertEqual(
            sorted(str(person.id) for person in Task.query.one().assignees),
            sorted([str(self.person.id), self.user["id"]]),
        )
