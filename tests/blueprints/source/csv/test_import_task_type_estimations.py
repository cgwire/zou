import os
import tempfile

from tests.base import ApiDBTestCase

from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.task import Task
from zou.app.services import persons_service


class ImportCsvTaskTypeEstimationsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_task_type()

    def write_csv(self, content):
        """
        Write CSV content to a temporary file and return its path.
        """
        descriptor, file_path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as f:
            f.write(content)
        return file_path

    def test_import_matches_asset_entity(self):
        # For assets, a row is matched on its asset type ("Props") as Parent
        # and its asset name ("Tree") as Entity.
        self.generate_fixture_task()
        path = (
            f"/import/csv/projects/{self.project.id}"
            f"/task-types/{self.task_type.id}/estimations"
        )
        content = "Parent,Entity,Start date\nProps,Tree,2024-01-05\n"
        self.upload_file(path, self.write_csv(content))

        task = Task.get(self.task.id)
        self.assertEqual(task.start_date.strftime("%Y-%m-%d"), "2024-01-05")

    def test_import_task_metadata(self):
        self.generate_fixture_task()
        MetadataDescriptor.create(
            project_id=self.project.id,
            name="Contractor",
            data_type="string",
            field_name="contractor",
            entity_type="Task",
            task_type_id=self.task_type.id,
        )
        MetadataDescriptor.create(
            project_id=self.project.id,
            name="Other",
            data_type="string",
            field_name="other",
            entity_type="Task",
            task_type_id=self.task_type_animation.id,
        )
        self.task.update({"data": {"note": "keep me"}})
        path = (
            f"/import/csv/projects/{self.project.id}"
            f"/task-types/{self.task_type.id}/estimations"
        )
        content = "Parent,Entity,Contractor,Other\nProps,Tree,value 1,nope\n"
        self.upload_file(path, self.write_csv(content))

        task = Task.get(self.task.id)
        self.assertEqual(task.data.get("contractor"), "value 1")
        # A descriptor bound to another task type must be ignored.
        self.assertIsNone(task.data.get("other"))
        # Metadata absent from the CSV must survive the import.
        self.assertEqual(task.data.get("note"), "keep me")

    def test_import_scoped_to_an_episode(self):
        """
        The episode variant of the route. A tv show repeats sequence and shot
        names across episodes, so the episode in the path is what tells two
        identically named shots apart.
        """
        self.generate_fixture_episode("E01")
        first_episode = self.episode
        self.generate_fixture_sequence("S01", episode_id=first_episode.id)
        first_shot = self.generate_fixture_shot("P01")
        # The lookup branches on task_type["for_entity"], so a shot import
        # needs a shot task type, not the asset one the other tests use.
        shot_task_type = self.task_type_animation
        first_task = self.generate_fixture_shot_task(
            "main", shot_id=first_shot.id, task_type_id=shot_task_type.id
        )

        self.generate_fixture_episode("E02")
        second_episode = self.episode
        self.generate_fixture_sequence("S01", episode_id=second_episode.id)
        second_shot = self.generate_fixture_shot("P01")
        second_task = self.generate_fixture_shot_task(
            "main", shot_id=second_shot.id, task_type_id=shot_task_type.id
        )

        # Scoped on the first episode on purpose. Both shots slugify to the
        # same key, and without the scoping the map keeps the last one built,
        # which is the second episode's: the row would then land on the wrong
        # shot and this assertion would fail.
        path = (
            f"/import/csv/projects/{self.project.id}"
            f"/episodes/{first_episode.id}"
            f"/task-types/{shot_task_type.id}/estimations"
        )
        content = "Parent,Entity,Start date\nS01,P01,2024-03-08\n"
        self.upload_file(path, self.write_csv(content))

        self.assertEqual(
            Task.get(first_task.id).start_date.strftime("%Y-%m-%d"),
            "2024-03-08",
        )
        self.assertIsNone(Task.get(second_task.id).start_date)

    def import_estimations(self, content):
        """
        Import CSV content on the asset task type and return the fixture task
        as stored afterwards.
        """
        path = (
            f"/import/csv/projects/{self.project.id}"
            f"/task-types/{self.task_type.id}/estimations"
        )
        self.upload_file(path, self.write_csv(content))
        return Task.get(self.task.id)

    def display_durations_in_hours(self, hours_by_day=8):
        organisation = persons_service.get_organisation()
        persons_service.update_organisation(
            organisation["id"],
            {"format_duration_in_hours": True, "hours_by_day": hours_by_day},
        )

    def test_import_estimation_in_days(self):
        # Durations display in days by default: 1.5 days at 8 hours a day
        # are 720 minutes, spread over two business days from a Monday.
        self.generate_fixture_task()
        task = self.import_estimations(
            "Parent,Entity,Estimation,Start date\n"
            "Props,Tree,1.5,2024-01-08\n"
        )
        self.assertEqual(task.estimation, 720)
        self.assertEqual(task.due_date.strftime("%Y-%m-%d"), "2024-01-09")

    def test_import_estimation_in_hours(self):
        """
        An organisation that displays durations in hours sees and exports
        its estimations in hours, so the import reads them in hours too.
        """
        self.generate_fixture_task()
        self.display_durations_in_hours()
        task = self.import_estimations(
            "Parent,Entity,Estimation,Start date\n"
            "Props,Tree,12,2024-01-08\n"
        )
        self.assertEqual(task.estimation, 720)
        self.assertEqual(task.due_date.strftime("%Y-%m-%d"), "2024-01-09")

    def test_import_estimation_in_hours_unrounded(self):
        """
        Kitsu stores the hours typed in its lists unrounded and exports them
        with two decimals: rounded to whole minutes, 0.66 hours would come
        back as 40 minutes, shown as 0.67.
        """
        self.generate_fixture_task()
        self.display_durations_in_hours()
        task = self.import_estimations(
            "Parent,Entity,Estimation\nProps,Tree,0.66\n"
        )
        self.assertAlmostEqual(task.estimation, 39.6)

    def test_import_estimation_in_hours_of_whole_days(self):
        """
        22.8 hours at 7.6 hours a day divide into 3.0000000000000004 days
        in floating point: the due date must still be the third business
        day.
        """
        self.generate_fixture_task()
        self.display_durations_in_hours(hours_by_day=7.6)
        task = self.import_estimations(
            "Parent,Entity,Estimation,Start date\n"
            "Props,Tree,22.8,2024-01-08\n"
        )
        self.assertEqual(task.estimation, 1368)
        self.assertEqual(task.due_date.strftime("%Y-%m-%d"), "2024-01-10")
