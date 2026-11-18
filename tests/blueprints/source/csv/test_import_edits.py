import os
import tempfile

from tests.base import ApiDBTestCase
from zou.app.models.comment import Comment
from zou.app.models.task import Task
from zou.app.services import edits_service, projects_service, shots_service


class ImportCsvEditsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.path = f"/import/csv/projects/{self.project.id}/edits"

    def write_csv(self, content):
        descriptor, file_path = tempfile.mkstemp(suffix=".csv")
        self.addCleanup(os.remove, file_path)
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as f:
            f.write(content)
        return file_path

    def test_import_edits(self):
        self.upload_file(
            self.path,
            self.write_csv("Name,Description\nOpening,The first edit\n"),
        )

        edits = edits_service.get_edits_for_project(str(self.project.id))
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["name"], "Opening")
        self.assertEqual(edits[0]["description"], "The first edit")

    def test_import_creates_the_missing_episode_of_a_tv_show(self):
        """
        On a tv show the Episode column names where the edit belongs, and an
        episode that does not exist yet is created along the way, so a studio
        can seed a season from one file.
        """
        self.project.update({"production_type": "tvshow"})
        self.upload_file(
            self.path,
            self.write_csv("Name,Episode\nOpening,E01\nEnding,E01\n"),
        )

        episodes = shots_service.get_episodes({"project_id": self.project.id})
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["name"], "E01")

        edits = edits_service.get_edits_for_episode(episodes[0]["id"])
        self.assertEqual(
            sorted(edit["name"] for edit in edits), ["Ending", "Opening"]
        )

    def test_an_empty_episode_cell_means_no_episode(self):
        # DictReader reads an empty cell as "", which used to create an
        # episode named "".
        self.project.update({"production_type": "tvshow"})
        self.upload_file(
            self.path,
            self.write_csv("Name,Episode\nOpening,E01\nTeaser,\n"),
        )
        episodes = shots_service.get_episodes({"project_id": self.project.id})
        self.assertEqual([episode["name"] for episode in episodes], ["E01"])
        edits = {
            edit["name"]: edit
            for edit in edits_service.get_edits_for_project(
                str(self.project.id)
            )
        }
        self.assertEqual(edits["Opening"]["parent_id"], episodes[0]["id"])
        self.assertIsNone(edits["Teaser"]["parent_id"])

    def test_episode_column_is_refused_outside_a_tv_show(self):
        """
        A short has no episode to hang an edit from, so the column is a
        mistake worth reporting rather than a value to ignore.
        """
        self.upload_file(
            self.path,
            self.write_csv("Name,Episode\nOpening,E01\n"),
            code=400,
        )
        self.assertEqual(
            edits_service.get_edits_for_project(str(self.project.id)), []
        )

    def test_import_creates_the_tasks_of_rows_before_a_failure(self):
        # The tasks were created once the whole file was imported: a
        # rejected line left the edits imported before it without them,
        # and a new import does not create them.
        self.generate_fixture_task_type()
        projects_service.add_task_type_setting(
            self.project.id, self.task_type_edit.id
        )
        self.upload_file(
            self.path,
            self.write_csv("Name,Edit\nOpening,\nEnding,Unknown\n"),
            code=400,
        )

        edits = edits_service.get_edits_for_project(str(self.project.id))
        self.assertEqual([edit["name"] for edit in edits], ["Opening"])
        self.assertEqual(
            [
                (str(task.entity_id), str(task.task_type_id))
                for task in Task.query.all()
            ],
            [(edits[0]["id"], str(self.task_type_edit.id))],
        )

    def test_an_existing_edit_changes_with_the_update_option_only(self):
        self.upload_file(
            self.path, self.write_csv("Name,Description\nOpening,First\n")
        )
        self.upload_file(
            self.path, self.write_csv("Name,Description\nOpening,Second\n")
        )
        edits = edits_service.get_edits_for_project(str(self.project.id))
        self.assertEqual([edit["description"] for edit in edits], ["First"])

        self.upload_file(
            f"{self.path}?update=true",
            self.write_csv("Name,Description\nOpening,Third\n"),
        )
        edits = edits_service.get_edits_for_project(str(self.project.id))
        self.assertEqual(
            [(edit["name"], edit["description"]) for edit in edits],
            [("Opening", "Third")],
        )

    def test_import_reads_the_metadata_columns(self):
        self.generate_fixture_metadata_descriptor(entity_type="Edit")
        self.upload_file(
            self.path, self.write_csv("Name,Contractor\nOpening,value 1\n")
        )
        edits = edits_service.get_edits_for_project(str(self.project.id))
        self.assertEqual(edits[0]["data"], {"contractor": "value 1"})

    def test_import_sets_the_task_status_with_its_comment(self):
        self.generate_fixture_task_type()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_done()
        projects_service.add_task_type_setting(
            self.project.id, self.task_type_edit.id
        )
        self.upload_file(self.path, self.write_csv("Name,Edit\nOpening,wip\n"))
        task = Task.query.one()
        self.assertEqual(task.task_status_id, self.task_status_wip.id)
        self.assertEqual(Comment.query.count(), 1)

        # The same status again posts nothing.
        self.upload_file(
            f"{self.path}?update=true",
            self.write_csv("Name,Edit\nOpening,wip\n"),
        )
        self.assertEqual(Comment.query.count(), 1)

        self.upload_file(
            f"{self.path}?update=true",
            self.write_csv("Name,Edit,Edit comment\nOpening,Done,Approved\n"),
        )
        task = Task.get(task.id)
        self.assertEqual(task.task_status_id, self.task_status_done.id)
        self.assertEqual(
            sorted(comment.text for comment in Comment.query.all()),
            ["", "Approved"],
        )
