import os
import tempfile

from tests.base import ApiDBTestCase
from zou.app.models.comment import Comment
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.services import projects_service, shots_service


class ImportCsvSequencesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.path = f"/import/csv/projects/{self.project.id}/sequences"

    def write_csv(self, content):
        descriptor, file_path = tempfile.mkstemp(suffix=".csv")
        self.addCleanup(os.remove, file_path)
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as f:
            f.write(content)
        return file_path

    def get_sequences(self):
        return shots_service.get_sequences({"project_id": self.project.id})

    def get_episodes(self):
        return shots_service.get_episodes({"project_id": self.project.id})

    def test_import_sequences(self):
        self.upload_file(
            self.path,
            self.write_csv("Name,Description\nSQ01,The first sequence\n"),
        )

        sequences = self.get_sequences()
        self.assertEqual(
            [
                (sequence["name"], sequence["description"])
                for sequence in sequences
            ],
            [("SQ01", "The first sequence")],
        )
        self.assertIsNone(sequences[0]["parent_id"])

    def test_import_creates_the_missing_episodes_of_a_tv_show(self):
        """
        A name repeats from one episode to the next: each episode gets its
        own sequence.
        """
        self.project.update({"production_type": "tvshow"})
        self.upload_file(
            self.path,
            self.write_csv("Episode,Name\nE01,SQ01\nE01,SQ02\nE02,SQ01\n"),
        )

        episode_ids = {
            episode["name"]: episode["id"] for episode in self.get_episodes()
        }
        self.assertEqual(sorted(episode_ids), ["E01", "E02"])
        self.assertEqual(
            sorted(
                (sequence["parent_id"], sequence["name"])
                for sequence in self.get_sequences()
            ),
            sorted(
                [
                    (episode_ids["E01"], "SQ01"),
                    (episode_ids["E01"], "SQ02"),
                    (episode_ids["E02"], "SQ01"),
                ]
            ),
        )

    def test_a_line_without_episode_is_refused_in_a_tv_show(self):
        # A sequence outside any episode shows on no episode page.
        self.project.update({"production_type": "tvshow"})
        result = self.upload_file(
            self.path,
            self.write_csv("Episode,Name\nE01,SQ01\n,SQ02\n"),
            code=400,
        )

        self.assertEqual(result["line_number"], 3)
        self.assertEqual(result["message"], "Episode cannot be empty")
        self.assertEqual(result["imported_rows"], 1)
        self.assertEqual(
            [sequence["name"] for sequence in self.get_sequences()], ["SQ01"]
        )

    def test_a_film_reads_no_episode(self):
        """
        A film has no episode: an empty Episode column is fine, a filled
        one is a mistake worth reporting rather than a value to ignore.
        """
        self.upload_file(self.path, self.write_csv("Name,Episode\nSQ01,\n"))
        self.upload_file(
            self.path, self.write_csv("Name,Episode\nSQ02,E01\n"), code=400
        )

        self.assertEqual(
            [
                (sequence["name"], sequence["parent_id"])
                for sequence in self.get_sequences()
            ],
            [("SQ01", None)],
        )
        self.assertEqual(self.get_episodes(), [])

    def test_a_line_without_name_is_refused(self):
        result = self.upload_file(
            self.path, self.write_csv("Name,Description\n,Night\n"), code=400
        )

        self.assertEqual(result["message"], "Name cannot be empty")
        self.assertEqual(self.get_sequences(), [])

    def test_an_existing_sequence_changes_with_the_update_option_only(self):
        self.upload_file(
            self.path, self.write_csv("Name,Description\nSQ01,First\n")
        )
        self.upload_file(
            self.path, self.write_csv("Name,Description\nSQ01,Second\n")
        )
        self.assertEqual(
            [sequence["description"] for sequence in self.get_sequences()],
            ["First"],
        )

        self.upload_file(
            f"{self.path}?update=true",
            self.write_csv("Name,Description\nSQ01,Third\n"),
        )
        self.assertEqual(
            [
                (sequence["name"], sequence["description"])
                for sequence in self.get_sequences()
            ],
            [("SQ01", "Third")],
        )

    def test_import_reads_the_metadata_columns(self):
        self.generate_fixture_metadata_descriptor(entity_type="Sequence")
        self.upload_file(
            self.path, self.write_csv("Name,Contractor\nSQ01,value 1\n")
        )

        self.assertEqual(
            self.get_sequences()[0]["data"], {"contractor": "value 1"}
        )

    def test_import_sets_the_status_comment_and_assignees_of_a_task(self):
        task_type = TaskType.create(
            name="Storyboard",
            short_name="sb",
            color="#FFFFFF",
            for_entity="Sequence",
        )
        projects_service.add_task_type_setting(self.project.id, task_type.id)
        self.generate_fixture_task_status_wip()
        self.generate_fixture_person()
        self.upload_file(
            self.path,
            self.write_csv(
                "Name,Storyboard,Storyboard comment,Storyboard assignations\n"
                "SQ01,wip,First pass,John Doe\n"
                "SQ02,,,\n"
            ),
        )

        tasks = {
            shots_service.get_sequence(str(task.entity_id))["name"]: task
            for task in Task.query.all()
        }
        self.assertEqual(sorted(tasks), ["SQ01", "SQ02"])
        self.assertEqual(tasks["SQ01"].task_type_id, task_type.id)
        self.assertEqual(tasks["SQ01"].task_status_id, self.task_status_wip.id)
        self.assertEqual(
            [person.id for person in tasks["SQ01"].assignees],
            [self.person.id],
        )
        self.assertEqual(
            [comment.text for comment in Comment.query.all()], ["First pass"]
        )

    def test_an_update_assigns_only_the_people_not_yet_assigned(self):
        task_type = TaskType.create(
            name="Storyboard",
            short_name="sb",
            color="#FFFFFF",
            for_entity="Sequence",
        )
        projects_service.add_task_type_setting(self.project.id, task_type.id)
        self.generate_fixture_person()
        self.upload_file(
            self.path,
            self.write_csv("Name,Storyboard assignations\nSQ01,John Doe\n"),
        )

        assigned = self.capture_events("task:assign")
        self.upload_file(
            f"{self.path}?update=true",
            self.write_csv(
                'Name,Storyboard assignations\nSQ01,"John Doe, John Did"\n'
            ),
        )

        self.assertEqual(
            [str(event["person_id"]) for event in assigned], [self.user["id"]]
        )
        self.assertEqual(
            sorted(str(person.id) for person in Task.query.one().assignees),
            sorted([str(self.person.id), self.user["id"]]),
        )
