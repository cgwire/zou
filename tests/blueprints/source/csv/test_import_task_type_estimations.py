import os
import tempfile
import uuid

from tests.base import ApiDBTestCase
from zou.app.models.entity import EntityLink
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
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
        self.addCleanup(os.remove, file_path)
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

    def test_main_pack_imports_the_shots_without_episode(self):
        main_task = self.generate_shot_task(
            self.generate_fixture_sequence("SQ01"), "P01"
        )
        episode_task = self.generate_episode_shot_task("E01", "SQ01", "P01")
        path = self.estimations_path(self.task_type_animation.id, "main")
        content = "Parent,Entity,Start date\nSQ01,P01,2024-01-05\n"
        self.upload_file(path, self.write_csv(content))

        self.assertEqual(self.get_start_date(main_task.id), "2024-01-05")
        self.assertIsNone(self.get_start_date(episode_task.id))

    def test_main_pack_does_not_find_the_shots_of_episodes(self):
        task = self.generate_episode_shot_task("E01", "SQ01", "P01")
        path = self.estimations_path(self.task_type_animation.id, "main")
        content = "Parent,Entity,Start date\nSQ01,P01,2024-01-05\n"
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(
            result["message"], "Entity 'P01' with parent 'SQ01' not found"
        )
        self.assertIsNone(self.get_start_date(task.id))

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

    def generate_entity_task_type(self, for_entity):
        return TaskType.create(
            name=f"{for_entity} Layout",
            short_name=f"{for_entity[:3].lower()}lay",
            color="#FFFFFF",
            for_entity=for_entity,
            department_id=self.department.id,
        )

    def generate_entity_task(self, entity, task_type):
        task = self.generate_fixture_task(
            entity_id=entity.id, task_type_id=task_type.id
        )
        task.update({"start_date": None})
        return task

    def test_import_episode_task_dates(self):
        task_type = self.generate_entity_task_type("Episode")
        first_task = self.generate_entity_task(
            self.generate_fixture_episode("E01"), task_type
        )
        second_task = self.generate_entity_task(
            self.generate_fixture_episode("E02"), task_type
        )
        path = self.estimations_path(task_type.id)
        content = "Entity,Start date\nE01,2024-01-05\n"
        self.upload_file(path, self.write_csv(content))

        self.assertEqual(self.get_start_date(first_task.id), "2024-01-05")
        self.assertIsNone(self.get_start_date(second_task.id))

    def test_import_episode_task_ignores_the_route_episode(self):
        """
        Older Kitsu versions post the import of an episode task type under
        the current episode: the row still names any episode of the
        project, and a Parent cell is ignored.
        """
        task_type = self.generate_entity_task_type("Episode")
        task = self.generate_entity_task(
            self.generate_fixture_episode("E01"), task_type
        )
        second_episode = self.generate_fixture_episode("E02")
        self.generate_entity_task(second_episode, task_type)
        cases = [
            (
                second_episode.id,
                "Entity,Start date\nE01,2024-01-05\n",
                "2024-01-05",
            ),
            ("all", "Entity,Start date\nE01,2024-01-06\n", "2024-01-06"),
            (
                "main",
                "Parent,Entity,Start date\nE02,e01,2024-01-07\n",
                "2024-01-07",
            ),
        ]
        for episode_id, content, start_date in cases:
            # xdist workers cannot send a UUID back in a subtest report.
            with self.subTest(episode_id=str(episode_id)):
                path = self.estimations_path(task_type.id, episode_id)
                self.upload_file(path, self.write_csv(content))
                self.assertEqual(self.get_start_date(task.id), start_date)

    def test_import_episode_task_prefers_the_episode_not_canceled(self):
        task_type = self.generate_entity_task_type("Episode")
        canceled_task = self.generate_entity_task(
            self.generate_fixture_episode("E01"), task_type
        )
        self.episode.update({"status": "canceled"})
        live_task = self.generate_entity_task(
            self.generate_fixture_episode("E01"), task_type
        )
        path = self.estimations_path(task_type.id)
        content = "Entity,Start date\nE01,2024-01-05\n"
        self.upload_file(path, self.write_csv(content))

        self.assertEqual(self.get_start_date(live_task.id), "2024-01-05")
        self.assertIsNone(self.get_start_date(canceled_task.id))

    def test_import_episode_task_refuses_a_shared_name(self):
        task_type = self.generate_entity_task_type("Episode")
        first_task = self.generate_entity_task(
            self.generate_fixture_episode("E01"), task_type
        )
        second_task = self.generate_entity_task(
            self.generate_fixture_episode("E01"), task_type
        )
        path = self.estimations_path(task_type.id)
        content = "Entity,Start date\nE01,2024-01-05\nE09,2024-01-05\n"
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(result["message"], "Entity 'E01' matches 2 episodes")
        self.assertEqual(result["imported_rows"], 0)
        self.assertIsNone(self.get_start_date(first_task.id))
        self.assertIsNone(self.get_start_date(second_task.id))

    def test_import_episode_task_names_the_missing_episode(self):
        task_type = self.generate_entity_task_type("Episode")
        self.generate_entity_task(
            self.generate_fixture_episode("E01"), task_type
        )
        path = self.estimations_path(task_type.id)
        content = "Entity,Start date\nE01,2024-01-05\nE09,2024-01-05\n"
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(result["message"], "Entity 'E09' not found")
        self.assertEqual(result["line_number"], 3)
        self.assertEqual(result["imported_rows"], 1)

    def generate_tv_sequence_tasks(self):
        """
        Create S01 in E01 and in E02, each with a task of a sequence task
        type, and return the task type and both tasks.
        """
        task_type = self.generate_entity_task_type("Sequence")
        self.first_episode = self.generate_fixture_episode("E01")
        first_task = self.generate_entity_task(
            self.generate_fixture_sequence(
                "S01", episode_id=self.first_episode.id
            ),
            task_type,
        )
        self.second_episode = self.generate_fixture_episode("E02")
        second_task = self.generate_entity_task(
            self.generate_fixture_sequence(
                "S01", episode_id=self.second_episode.id
            ),
            task_type,
        )
        return task_type, first_task, second_task

    def test_import_sequence_task_in_episode(self):
        task_type, first_task, second_task = self.generate_tv_sequence_tasks()
        path = self.estimations_path(task_type.id, self.first_episode.id)
        for content, start_date in [
            ("Parent,Entity,Start date\n,S01,2024-01-05\n", "2024-01-05"),
            ("Entity,Start date\nS01,2024-01-06\n", "2024-01-06"),
            ("Parent,Entity,Start date\ne01,S01,2024-01-07\n", "2024-01-07"),
        ]:
            with self.subTest(content=content):
                self.upload_file(path, self.write_csv(content))
                self.assertEqual(
                    self.get_start_date(first_task.id), start_date
                )
        self.assertIsNone(self.get_start_date(second_task.id))

        content = "Parent,Entity,Start date\nE02,S01,2024-01-08\n"
        result = self.upload_file(path, self.write_csv(content), code=400)
        self.assertEqual(
            result["message"], "Entity 'S01' with parent 'E02' not found"
        )
        self.assertIsNone(self.get_start_date(second_task.id))

    def test_import_sequence_task_with_episode_parent(self):
        task_type, first_task, second_task = self.generate_tv_sequence_tasks()
        content = "Parent,Entity,Start date\nE02,S01,2024-01-05\n"
        for episode_id in [None, "all"]:
            with self.subTest(episode_id=episode_id):
                path = self.estimations_path(task_type.id, episode_id)
                self.upload_file(path, self.write_csv(content))
                self.assertEqual(
                    self.get_start_date(second_task.id), "2024-01-05"
                )
                self.assertIsNone(self.get_start_date(first_task.id))

    def test_import_sequence_task_without_parent_is_refused_if_shared(self):
        task_type, first_task, second_task = self.generate_tv_sequence_tasks()
        path = self.estimations_path(task_type.id, "all")
        content = "Parent,Entity,Start date\n,S01,2024-01-05\n"
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(
            result["message"],
            "Entity 'S01' matches 2 sequences, in episodes E01 and E02",
        )
        self.assertEqual(result["imported_rows"], 0)
        self.assertIsNone(self.get_start_date(first_task.id))
        self.assertIsNone(self.get_start_date(second_task.id))

    def test_import_sequence_task_without_episodes(self):
        task_type = self.generate_entity_task_type("Sequence")
        first_task = self.generate_entity_task(
            self.generate_fixture_sequence("S01"), task_type
        )
        second_task = self.generate_entity_task(
            self.generate_fixture_sequence("S02"), task_type
        )
        # Without an episode as parent, two sequences can share a name.
        for _ in range(2):
            self.generate_entity_task(
                self.generate_fixture_sequence("S03"), task_type
            )
        path = self.estimations_path(task_type.id)
        content = (
            "Entity,Start date\nS01,2024-01-05\nS02,2024-01-06\n"
            "S03,2024-01-07\n"
        )
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(self.get_start_date(first_task.id), "2024-01-05")
        self.assertEqual(self.get_start_date(second_task.id), "2024-01-06")
        self.assertEqual(result["message"], "Entity 'S03' matches 2 sequences")
        self.assertEqual(result["imported_rows"], 2)

    def test_import_edit_task_in_episode(self):
        task_type = self.task_type_edit
        first_episode = self.generate_fixture_episode("E01")
        first_task = self.generate_entity_task(
            self.generate_fixture_edit("Trailer", parent_id=first_episode.id),
            task_type,
        )
        second_episode = self.generate_fixture_episode("E02")
        second_task = self.generate_entity_task(
            self.generate_fixture_edit("Trailer", parent_id=second_episode.id),
            task_type,
        )
        path = self.estimations_path(task_type.id, second_episode.id)
        content = "Parent,Entity,Start date\n,Trailer,2024-01-05\n"
        self.upload_file(path, self.write_csv(content))

        self.assertEqual(self.get_start_date(second_task.id), "2024-01-05")
        self.assertIsNone(self.get_start_date(first_task.id))

        path = self.estimations_path(task_type.id, "all")
        content = "Parent,Entity,Start date\nE01,Trailer,2024-01-06\n"
        self.upload_file(path, self.write_csv(content))
        self.assertEqual(self.get_start_date(first_task.id), "2024-01-06")

    def test_import_edit_task_without_episode(self):
        task_type = self.task_type_edit
        episode = self.generate_fixture_episode("E01")
        task = self.generate_entity_task(
            self.generate_fixture_edit("Trailer"), task_type
        )
        episode_task = self.generate_entity_task(
            self.generate_fixture_edit("Teaser", parent_id=episode.id),
            task_type,
        )
        content = "Parent,Entity,Start date\n,Trailer,2024-01-05\n"
        for episode_id in [None, "main"]:
            with self.subTest(episode_id=episode_id):
                path = self.estimations_path(task_type.id, episode_id)
                self.upload_file(path, self.write_csv(content))
                self.assertEqual(self.get_start_date(task.id), "2024-01-05")
                task.update({"start_date": None})

        content = "Parent,Entity,Start date\nE01,Trailer,2024-01-05\n"
        path = self.estimations_path(task_type.id)
        result = self.upload_file(path, self.write_csv(content), code=400)
        self.assertEqual(
            result["message"], "Entity 'Trailer' with parent 'E01' not found"
        )
        self.assertIsNone(self.get_start_date(task.id))
        self.assertIsNone(self.get_start_date(episode_task.id))

    def test_main_pack_imports_the_sequences_and_edits_without_episode(self):
        sequence_task_type = self.generate_entity_task_type("Sequence")
        main_sequence_task = self.generate_entity_task(
            self.generate_fixture_sequence("SQ01"), sequence_task_type
        )
        main_edit_task = self.generate_entity_task(
            self.generate_fixture_edit("Trailer"), self.task_type_edit
        )
        episode = self.generate_fixture_episode("E01")
        episode_sequence_task = self.generate_entity_task(
            self.generate_fixture_sequence("SQ01", episode_id=episode.id),
            sequence_task_type,
        )
        episode_edit_task = self.generate_entity_task(
            self.generate_fixture_edit("Trailer", parent_id=episode.id),
            self.task_type_edit,
        )
        cases = [
            (sequence_task_type, "SQ01", main_sequence_task),
            (self.task_type_edit, "Trailer", main_edit_task),
        ]
        for task_type, name, task in cases:
            with self.subTest(for_entity=task_type.for_entity):
                path = self.estimations_path(task_type.id, "main")
                content = f"Parent,Entity,Start date\n,{name},2024-01-05\n"
                self.upload_file(path, self.write_csv(content))
                self.assertEqual(self.get_start_date(task.id), "2024-01-05")
        self.assertIsNone(self.get_start_date(episode_sequence_task.id))
        self.assertIsNone(self.get_start_date(episode_edit_task.id))

    def test_main_pack_does_not_find_the_sequences_and_edits_of_episodes(
        self,
    ):
        sequence_task_type = self.generate_entity_task_type("Sequence")
        episode = self.generate_fixture_episode("E01")
        sequence_task = self.generate_entity_task(
            self.generate_fixture_sequence("SQ01", episode_id=episode.id),
            sequence_task_type,
        )
        edit_task = self.generate_entity_task(
            self.generate_fixture_edit("Trailer", parent_id=episode.id),
            self.task_type_edit,
        )
        cases = [
            (sequence_task_type, "SQ01", sequence_task),
            (self.task_type_edit, "Trailer", edit_task),
        ]
        for task_type, name, task in cases:
            path = self.estimations_path(task_type.id, "main")
            for parent, message in [
                ("E01", f"Entity '{name}' with parent 'E01' not found"),
                ("", f"Entity '{name}' not found"),
            ]:
                with self.subTest(
                    for_entity=task_type.for_entity, parent=parent
                ):
                    content = (
                        "Parent,Entity,Start date\n"
                        f"{parent},{name},2024-01-05\n"
                    )
                    result = self.upload_file(
                        path, self.write_csv(content), code=400
                    )
                    self.assertEqual(result["message"], message)
                    self.assertIsNone(self.get_start_date(task.id))

    def test_concept_task_type_is_not_imported(self):
        task_type = self.generate_entity_task_type("Concept")
        path = self.estimations_path(task_type.id)
        content = "Parent,Entity,Start date\n,Sketch,2024-01-05\n"
        result = self.upload_file(path, self.write_csv(content), code=400)

        self.assertEqual(
            result["message"], "Entity 'Sketch' with parent '' not found"
        )

    def test_request_without_token_answers_401(self):
        self.base_headers = {}
        content = "Parent,Entity,Start date\nProps,Tree,2024-01-05\n"
        for task_type_id in [self.task_type.id, uuid.uuid4()]:
            for episode_id in [None, "all"]:
                with self.subTest(
                    task_type_id=str(task_type_id), episode_id=episode_id
                ):
                    path = self.estimations_path(task_type_id, episode_id)
                    self.upload_file(path, self.write_csv(content), code=401)
