import os
import tempfile

from tests.base import ApiDBTestCase
from zou.app.models.entity import EntityLink
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.task import Task
from zou.app.services import (
    organisation_service,
)


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

        # Scoped on the first episode on purpose: both shots are P01 of an S01
        # sequence, so without the scoping the row would match both and be
        # refused.
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
        organisation = organisation_service.get_organisation()
        organisation_service.update_organisation(
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

    def test_invalid_value_names_its_column(self):
        self.generate_fixture_task()
        path = (
            f"/import/csv/projects/{self.project.id}"
            f"/task-types/{self.task_type.id}/estimations"
        )
        cases = [
            ("Start date", "02/11/2026", "YYYY-MM-DD"),
            ("Due date", "2026-13-01", "YYYY-MM-DD"),
            ("Estimation", "1,5", "a number with a dot, such as 1.5"),
            ("Difficulty", "x", "a whole number"),
            ("Drawings", "2.5", "a whole number"),
        ]
        for column, value, expected in cases:
            with self.subTest(column=column):
                content = f'Parent,Entity,{column}\nProps,Tree,"{value}"\n'
                result = self.upload_file(
                    path, self.write_csv(content), code=400
                )
                self.assertEqual(
                    result["message"],
                    f"Invalid value in column '{column}': '{value}' "
                    f"(expected {expected})",
                )
                self.assertEqual(result["line_number"], 2)
                self.assertEqual(result["imported_rows"], 0)

    def test_rows_before_an_invalid_value_stay_imported(self):
        self.generate_fixture_task()
        path = (
            f"/import/csv/projects/{self.project.id}"
            f"/task-types/{self.task_type.id}/estimations"
        )
        content = (
            "Parent,Entity,Start date\n"
            "Props,Tree,2024-01-05\n"
            "Props,Tree,05/01/2024\n"
        )
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(result["line_number"], 3)
        self.assertEqual(result["imported_rows"], 1)
        task = Task.get(self.task.id)
        self.assertEqual(task.start_date.strftime("%Y-%m-%d"), "2024-01-05")

    def test_entity_without_task_is_named(self):
        self.generate_fixture_task()
        self.generate_fixture_asset(name="Rock")
        path = (
            f"/import/csv/projects/{self.project.id}"
            f"/task-types/{self.task_type.id}/estimations"
        )
        content = (
            "Parent,Entity,Start date\n"
            "Props,Tree,2024-01-05\n"
            "Props,Rock,2024-01-05\n"
        )
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(
            result["message"],
            "Entity 'Rock' with parent 'Props' has no 'Shaders' task",
        )
        self.assertEqual(result["line_number"], 3)
        self.assertEqual(result["imported_rows"], 1)

    def estimations_path(self, task_type_id, episode_id=None):
        episode_part = f"/episodes/{episode_id}" if episode_id else ""
        return (
            f"/import/csv/projects/{self.project.id}{episode_part}"
            f"/task-types/{task_type_id}/estimations"
        )

    def get_start_date(self, task_id):
        start_date = Task.get(task_id).start_date
        return start_date.strftime("%Y-%m-%d") if start_date else None

    def generate_asset_task(self, name):
        asset = self.generate_fixture_asset(name=name)
        task = self.generate_fixture_task(entity_id=asset.id)
        task.update({"start_date": None})
        return task

    def generate_shot_task(self, sequence, name):
        shot = self.generate_fixture_shot(name, sequence_id=sequence.id)
        return self.generate_fixture_shot_task(
            shot_id=shot.id, task_type_id=self.task_type_animation.id
        )

    def test_key_does_not_join_parent_and_name(self):
        """
        Parent and name are compared apart: joined, 'SQ01' + '0010' read as
        'SQ010' + '010', and 'SQ01' with an empty name as 'SQ' + '01'.
        """
        sequence = self.generate_fixture_sequence("SQ010")
        task = self.generate_shot_task(sequence, "010")
        short_sequence = self.generate_fixture_sequence("SQ")
        short_task = self.generate_shot_task(short_sequence, "01")
        path = self.estimations_path(self.task_type_animation.id)

        for content in [
            "Parent,Entity,Start date\nSQ01,0010,2024-01-05\n",
            "Parent,Entity,Start date\nSQ01,,2024-01-05\n",
        ]:
            with self.subTest(content=content):
                result = self.upload_file(
                    path, self.write_csv(content), code=400
                )
                self.assertIn("not found", result["message"])
        self.assertIsNone(self.get_start_date(task.id))
        self.assertIsNone(self.get_start_date(short_task.id))

        sequence = self.generate_fixture_sequence("SQ01")
        other_task = self.generate_shot_task(sequence, "0010")
        content = "Parent,Entity,Start date\nSQ01,0010,2024-01-05\n"
        self.upload_file(path, self.write_csv(content))
        self.assertEqual(self.get_start_date(other_task.id), "2024-01-05")
        self.assertIsNone(self.get_start_date(task.id))

    def test_key_ignores_case_spaces_and_accents(self):
        tree_task = self.generate_fixture_task()
        dash_task = self.generate_asset_task("-Hero")
        path = self.estimations_path(self.task_type.id)
        content = (
            "Parent,Entity,Start date\n"
            " props ,TREE,2024-01-05\n"
            "Props,-Hero,2024-01-06\n"
        )
        self.upload_file(path, self.write_csv(content))

        self.assertEqual(self.get_start_date(tree_task.id), "2024-01-05")
        self.assertEqual(self.get_start_date(dash_task.id), "2024-01-06")
        content = "Parent,Entity,Start date\nPROPS,Trée,2024-01-07\n"
        self.upload_file(path, self.write_csv(content))
        self.assertEqual(self.get_start_date(tree_task.id), "2024-01-07")

    def test_key_prefers_the_exact_name(self):
        upper_task = self.generate_asset_task("Hero")
        lower_task = self.generate_asset_task("hero")
        path = self.estimations_path(self.task_type.id)
        content = (
            "Parent,Entity,Start date\n"
            "Props,Hero,2024-01-05\n"
            "Props,hero,2024-01-06\n"
        )
        self.upload_file(path, self.write_csv(content))

        self.assertEqual(self.get_start_date(upper_task.id), "2024-01-05")
        self.assertEqual(self.get_start_date(lower_task.id), "2024-01-06")

    def test_key_prefers_the_entity_not_canceled(self):
        # The canceled asset comes last, where the old map kept it.
        live_task = self.generate_asset_task("HERO")
        canceled_task = self.generate_asset_task("Hero")
        self.asset.update({"canceled": True})
        path = self.estimations_path(self.task_type.id)
        content = "Parent,Entity,Start date\nProps,hero,2024-01-05\n"
        self.upload_file(path, self.write_csv(content))

        self.assertEqual(self.get_start_date(live_task.id), "2024-01-05")
        self.assertIsNone(self.get_start_date(canceled_task.id))

        # The exact name comes first: a row naming the canceled asset
        # exactly still reaches it.
        content = "Parent,Entity,Start date\nProps,Hero,2024-01-06\n"
        self.upload_file(path, self.write_csv(content))

        self.assertEqual(self.get_start_date(canceled_task.id), "2024-01-06")
        self.assertEqual(self.get_start_date(live_task.id), "2024-01-05")

    def test_missing_column_is_named(self):
        self.generate_fixture_task()
        without_parent = "Entity,Start date\nTree,2024-01-05\n"
        without_entity = "Parent,Start date\nProps,2024-01-05\n"
        cases = [
            (self.task_type, without_parent, "Parent"),
            (self.task_type_animation, without_parent, "Parent"),
            (self.task_type, without_entity, "Entity"),
        ]
        for task_type, content, column in cases:
            with self.subTest(task_type=task_type.name, column=column):
                path = self.estimations_path(task_type.id)
                result = self.upload_file(
                    path, self.write_csv(content), code=400
                )
                self.assertIn(f"missing: '{column}'", result["message"])
                self.assertEqual(result["line_number"], 2)

    def test_short_row_message_has_no_none(self):
        self.generate_fixture_task()
        path = self.estimations_path(self.task_type.id)
        # The csv sniffer needs enough full rows to read the delimiter
        # despite the short one.
        content = (
            "Parent,Entity,Start date\n"
            + "Props,Tree,2024-01-05\n" * 9
            + "Rocks\n"
        )
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(
            result["message"], "Entity '' with parent 'Rocks' not found"
        )
        self.assertEqual(result["line_number"], 11)

    def generate_episode_shot_task(self, episode_name, sequence_name, name):
        episode = self.generate_fixture_episode(episode_name)
        sequence = self.generate_fixture_sequence(
            sequence_name, episode_id=episode.id
        )
        return self.generate_shot_task(sequence, name)

    def test_shot_matching_several_episodes_is_refused(self):
        first_task = self.generate_episode_shot_task("E01", "S01", "P01")
        second_task = self.generate_episode_shot_task("E02", "S01", "P01")
        unique_task = self.generate_episode_shot_task("E03", "S02", "P01")
        content = (
            "Parent,Entity,Start date\n"
            "S02,P01,2024-01-05\n"
            "S01,P01,2024-01-06\n"
        )
        for episode_id in [None, "all"]:
            with self.subTest(episode_id=episode_id):
                path = self.estimations_path(
                    self.task_type_animation.id, episode_id
                )
                result = self.upload_file(
                    path, self.write_csv(content), code=400
                )

                self.assertEqual(
                    result["message"],
                    "Entity 'P01' with parent 'S01' matches 2 shots, "
                    "in episodes E01 and E02",
                )
                self.assertEqual(result["line_number"], 3)
                self.assertEqual(result["imported_rows"], 1)
        self.assertEqual(self.get_start_date(unique_task.id), "2024-01-05")
        self.assertIsNone(self.get_start_date(first_task.id))
        self.assertIsNone(self.get_start_date(second_task.id))

    def test_asset_matching_an_episode_and_the_main_pack_is_refused(self):
        main_task = self.generate_asset_task("Tree")
        episode = self.generate_fixture_episode("E01")
        episode_task = self.generate_asset_task("tree")
        self.asset.update({"source_id": episode.id})
        path = self.estimations_path(self.task_type.id, "all")
        content = "Parent,Entity,Start date\nProps,TREE,2024-01-05\n"
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(
            result["message"],
            "Entity 'TREE' with parent 'Props' matches 2 assets, "
            "in episodes E01 and main pack",
        )
        self.assertIsNone(self.get_start_date(main_task.id))
        self.assertIsNone(self.get_start_date(episode_task.id))

    def test_asset_matching_several_entities_is_refused(self):
        # Without episodes, the message can only count the candidates.
        upper_task = self.generate_asset_task("Hero")
        lower_task = self.generate_asset_task("hero")
        path = self.estimations_path(self.task_type.id)
        content = "Parent,Entity,Start date\nProps,HERO,2024-01-05\n"
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(
            result["message"],
            "Entity 'HERO' with parent 'Props' matches 2 assets",
        )
        self.assertIsNone(self.get_start_date(upper_task.id))
        self.assertIsNone(self.get_start_date(lower_task.id))

    def test_assets_matching_in_one_episode_name_it_once(self):
        self.generate_fixture_episode("E01")
        self.generate_asset_task("Tree")
        self.generate_asset_task("tree")
        path = self.estimations_path(self.task_type.id, "all")
        content = "Parent,Entity,Start date\nProps,TREE,2024-01-05\n"
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(
            result["message"],
            "Entity 'TREE' with parent 'Props' matches 2 assets, "
            "all in main pack",
        )

    def test_asset_cast_into_the_episode_is_imported(self):
        """
        The task type page of an episode lists the assets cast into it,
        whatever their source: the main pack or another episode.
        """
        first_episode = self.generate_fixture_episode("E01")
        second_episode = self.generate_fixture_episode("E02")
        main_task = self.generate_asset_task("Tree")
        EntityLink.create(
            entity_in_id=first_episode.id, entity_out_id=self.asset.id
        )
        other_task = self.generate_asset_task("Rock")
        self.asset.update({"source_id": second_episode.id})
        EntityLink.create(
            entity_in_id=first_episode.id, entity_out_id=self.asset.id
        )
        path = self.estimations_path(self.task_type.id, first_episode.id)
        content = (
            "Parent,Entity,Start date\n"
            "Props,Tree,2024-01-05\n"
            "Props,Rock,2024-01-06\n"
        )
        self.upload_file(path, self.write_csv(content))

        self.assertEqual(self.get_start_date(main_task.id), "2024-01-05")
        self.assertEqual(self.get_start_date(other_task.id), "2024-01-06")

    def test_asset_of_the_episode_wins_over_a_cast_one(self):
        """
        The import used to match the assets of the episode only: a homonym
        cast into it from the main pack must not make that row ambiguous.
        """
        episode = self.generate_fixture_episode("E01")
        own_task = self.generate_asset_task("Rock")
        self.asset.update({"source_id": episode.id})
        cast_task = self.generate_asset_task("Rock")
        EntityLink.create(entity_in_id=episode.id, entity_out_id=self.asset.id)
        path = self.estimations_path(self.task_type.id, episode.id)
        content = "Parent,Entity,Start date\nProps,Rock,2024-01-05\n"
        self.upload_file(path, self.write_csv(content))

        self.assertEqual(self.get_start_date(own_task.id), "2024-01-05")
        self.assertIsNone(self.get_start_date(cast_task.id))

    def test_asset_outside_the_episode_is_not_found(self):
        first_episode = self.generate_fixture_episode("E01")
        second_episode = self.generate_fixture_episode("E02")
        task = self.generate_asset_task("Rock")
        self.asset.update({"source_id": second_episode.id})
        path = self.estimations_path(self.task_type.id, first_episode.id)
        content = "Parent,Entity,Start date\nProps,Rock,2024-01-05\n"
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(
            result["message"], "Entity 'Rock' with parent 'Props' not found"
        )
        self.assertIsNone(self.get_start_date(task.id))

    def test_malformed_episode_id_is_refused(self):
        self.generate_fixture_task()
        content = "Parent,Entity,Start date\nProps,Tree,2024-01-05\n"
        for task_type in [self.task_type, self.task_type_animation]:
            with self.subTest(task_type=task_type.name):
                path = self.estimations_path(task_type.id, "E01")
                self.upload_file(path, self.write_csv(content), code=400)

    def test_main_pack_imports_the_assets_without_episode(self):
        episode = self.generate_fixture_episode("E01")
        main_task = self.generate_asset_task("Tree")
        episode_task = self.generate_asset_task("tree")
        self.asset.update({"source_id": episode.id})
        EntityLink.create(entity_in_id=episode.id, entity_out_id=self.asset.id)
        path = self.estimations_path(self.task_type.id, "main")
        content = "Parent,Entity,Start date\nProps,TREE,2024-01-05\n"
        self.upload_file(path, self.write_csv(content))

        self.assertEqual(self.get_start_date(main_task.id), "2024-01-05")
        self.assertIsNone(self.get_start_date(episode_task.id))

        self.generate_asset_task("Rock")
        self.asset.update({"source_id": episode.id})
        content = "Parent,Entity,Start date\nProps,Rock,2024-01-05\n"
        result = self.upload_file(path, self.write_csv(content), code=400)
        self.assertEqual(
            result["message"], "Entity 'Rock' with parent 'Props' not found"
        )
