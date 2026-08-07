from flask_jwt_extended import verify_jwt_in_request

from tests.base import ApiDBTestCase

from zou.app import app
from zou.app.models.entity import Entity
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.services import comments_service, stats_service, tasks_service


class MainStatsTestCase(ApiDBTestCase):
    """
    The four counts sent out by the telemetry. They are counted by preview
    extension, so the only thing that can go wrong is a count wired to the
    wrong one.
    """

    def test_get_main_stats_of_an_empty_studio(self):
        self.assertEqual(
            stats_service.get_main_stats(),
            {
                "number_of_video_previews": 0,
                "number_of_picture_previews": 0,
                "number_of_model_previews": 0,
                "number_of_comments": 0,
            },
        )

    def test_get_main_stats(self):
        # Three distinct counts, so a count read off the wrong extension
        # cannot pass.
        for extension, number in [("mp4", 1), ("png", 2), ("obj", 3)]:
            for _ in range(number):
                PreviewFile.create(name="main", extension=extension)
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        task = self.generate_fixture_task()
        comments_service.new_comment(
            task.id, self.task_status.id, self.user["id"], "comment"
        )

        self.assertEqual(
            stats_service.get_main_stats(),
            {
                "number_of_video_previews": 1,
                "number_of_picture_previews": 2,
                "number_of_model_previews": 3,
                "number_of_comments": 1,
            },
        )


class StatsWalkTestCase(ApiDBTestCase):
    """
    The two pure functions the episode stats are built from. They are given
    one query row at a time and fold it into the nested result.
    """

    def add_entry(self, add, results, **overrides):
        """
        One row of the stats walk, with the parts a case does not care about
        filled in.
        """
        payload = {
            "project_id": "p1",
            "episode_id": "e1",
            "task_type_id": "tt1",
            "task_status_id": "ts1",
            "task_status_short_name": "wip",
            "task_status_color": "#FFFFFF",
            "task_count": 5,
            "task_nb_drawings": 10,
            "entity_nb_frames": 100,
        }
        payload.update(overrides)
        add(results, **payload)

    def test_add_entry_to_stats(self):
        """
        A row lands under its own task type, and the episode's "all" bucket
        sums every task type of that episode. Two rows, because one cannot
        tell a sum from an assignment.
        """
        results = {}
        self.add_entry(stats_service.add_entry_to_stats, results)
        self.add_entry(
            stats_service.add_entry_to_stats,
            results,
            task_type_id="tt2",
            task_count=2,
            task_nb_drawings=4,
            entity_nb_frames=20,
        )

        self.assertEqual(
            results["e1"]["tt1"]["ts1"],
            {
                "name": "wip",
                "color": "#FFFFFF",
                "count": 5,
                "frames": 100,
                "drawings": 10,
            },
        )
        self.assertEqual(results["e1"]["tt2"]["ts1"]["count"], 2)
        self.assertEqual(results["e1"]["all"]["ts1"]["count"], 7)
        self.assertEqual(results["e1"]["all"]["ts1"]["frames"], 120)
        self.assertEqual(results["e1"]["all"]["ts1"]["drawings"], 14)

    def test_add_entry_to_stats_keeps_the_episodes_apart(self):
        results = {}
        self.add_entry(stats_service.add_entry_to_stats, results)
        self.add_entry(
            stats_service.add_entry_to_stats,
            results,
            episode_id="e2",
            task_count=2,
        )

        self.assertEqual(results["e1"]["all"]["ts1"]["count"], 5)
        self.assertEqual(results["e2"]["all"]["ts1"]["count"], 2)

    def test_add_entry_to_stats_reads_a_missing_sum_as_zero(self):
        # An episode whose shots carry no frame count sums to null in SQL.
        results = {}
        self.add_entry(
            stats_service.add_entry_to_stats,
            results,
            entity_nb_frames=None,
            task_nb_drawings=None,
        )

        self.assertEqual(results["e1"]["tt1"]["ts1"]["frames"], 0)
        self.assertEqual(results["e1"]["tt1"]["ts1"]["drawings"], 0)
        self.assertEqual(results["e1"]["all"]["ts1"]["frames"], 0)

    def test_add_entry_to_all_stats(self):
        """
        The production wide bucket: per task type under "all", and summed
        across task types under "all"/"all", whatever episode the row came
        from.
        """
        results = {}
        self.add_entry(stats_service.add_entry_to_all_stats, results)
        self.add_entry(
            stats_service.add_entry_to_all_stats,
            results,
            episode_id="e2",
            task_type_id="tt2",
            task_count=2,
            task_nb_drawings=4,
            entity_nb_frames=20,
        )

        self.assertEqual(results["all"]["tt1"]["ts1"]["count"], 5)
        self.assertEqual(results["all"]["tt2"]["ts1"]["count"], 2)
        self.assertEqual(results["all"]["all"]["ts1"]["count"], 7)
        self.assertEqual(results["all"]["all"]["ts1"]["frames"], 120)
        self.assertEqual(results["all"]["all"]["ts1"]["drawings"], 14)

    def test_add_entry_to_all_stats_keeps_the_statuses_apart(self):
        results = {}
        self.add_entry(stats_service.add_entry_to_all_stats, results)
        self.add_entry(
            stats_service.add_entry_to_all_stats,
            results,
            task_status_id="ts2",
            task_status_short_name="done",
            task_count=2,
        )

        self.assertEqual(results["all"]["all"]["ts1"]["count"], 5)
        self.assertEqual(results["all"]["all"]["ts2"]["count"], 2)
        self.assertEqual(results["all"]["all"]["ts2"]["name"], "done")


class EpisodeStatsTestCase(ApiDBTestCase):
    """
    How many tasks sit in each status, per episode and per task type, with
    the frames and drawings they carry.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.project_id = str(self.project.id)
        self.episode_id = str(self.episode.id)
        self.status_id = str(self.task_status.id)
        self.task_type_id = str(self.task_type_animation.id)

    def a_shot_with_a_task(self, name, nb_frames, nb_drawings=0):
        shot = self.generate_fixture_shot(name, nb_frames=nb_frames)
        task = self.generate_fixture_shot_task(name=f"task {name}")
        task.update({"nb_drawings": nb_drawings})
        return task

    def a_task_elsewhere(self):
        """
        The same shape in another production. Built by hand: the standard
        fixtures hang their sequence off no episode, and this walk only
        reaches shots that have one.
        """
        project = Project.create(name="Another Production")
        episode = Entity.create(
            name="E01",
            project_id=project.id,
            entity_type_id=self.episode_type.id,
        )
        sequence = Entity.create(
            name="S01",
            project_id=project.id,
            entity_type_id=self.sequence_type.id,
            parent_id=episode.id,
        )
        shot = Entity.create(
            name="P01",
            project_id=project.id,
            entity_type_id=self.shot_type.id,
            parent_id=sequence.id,
            nb_frames=99,
        )
        return Task.create(
            name="elsewhere",
            project_id=project.id,
            task_type_id=self.task_type_animation.id,
            task_status_id=self.task_status.id,
            entity_id=shot.id,
        )

    def test_a_production_with_no_task(self):
        self.assertEqual(
            stats_service.get_episode_stats_for_project(self.project_id), {}
        )

    def test_get_episode_stats_for_project_is_scoped_to_its_production(self):
        self.a_shot_with_a_task("P01", nb_frames=10)
        self.a_task_elsewhere()

        result = stats_service.get_episode_stats_for_project(self.project_id)

        self.assertEqual(list(result), [self.episode_id, "all"])
        self.assertEqual(result["all"]["all"][self.status_id]["frames"], 10)

    def test_get_episode_stats_for_project(self):
        self.a_shot_with_a_task("P01", nb_frames=10, nb_drawings=1)
        self.a_shot_with_a_task("P02", nb_frames=20, nb_drawings=2)

        result = stats_service.get_episode_stats_for_project(self.project_id)

        bucket = result[self.episode_id][self.task_type_id][self.status_id]
        self.assertEqual(bucket["name"], self.task_status.short_name)
        self.assertEqual(
            (bucket["count"], bucket["frames"], bucket["drawings"]),
            (2, 30, 3),
        )
        # The same numbers roll up into the episode and the production.
        self.assertEqual(
            result[self.episode_id]["all"][self.status_id]["count"], 2
        )
        self.assertEqual(result["all"]["all"][self.status_id]["frames"], 30)

    def test_get_episode_stats_for_project_holds_only_assigned_tasks(self):
        """
        The assignee filter reads the caller off the request, so this one
        runs in a request context the way a route does.
        """
        mine = self.a_shot_with_a_task("P01", nb_frames=10)
        self.a_shot_with_a_task("P02", nb_frames=20)
        tasks_service.assign_task(str(mine.id), self.user["id"])

        with app.test_request_context(headers=self.auth_headers):
            verify_jwt_in_request()
            result = stats_service.get_episode_stats_for_project(
                self.project_id, only_assigned=True
            )

        bucket = result[self.episode_id][self.task_type_id][self.status_id]
        self.assertEqual((bucket["count"], bucket["frames"]), (1, 10))


class RetakeStatsTestCase(ApiDBTestCase):
    """
    How many tasks were done, retaken, or neither, and how the production
    stood at each take. Statuses are sorted into three buckets, done first.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_retake()
        self.generate_fixture_task_status_done()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.project_id = str(self.project.id)
        self.episode_id = str(self.episode.id)
        self.task_type_id = str(self.task_type_animation.id)

    def a_task(self, name, status, retake_count=0, nb_frames=0):
        self.generate_fixture_shot(name, nb_frames=nb_frames)
        task = self.generate_fixture_shot_task(name=f"task {name}")
        task.update(
            {"task_status_id": status.id, "retake_count": retake_count}
        )
        return task

    def episode_stats(self):
        return stats_service.get_episode_retake_stats_for_project(
            self.project_id
        )[self.episode_id]["all"]

    def test_a_production_with_no_task(self):
        result = stats_service.get_episode_retake_stats_for_project(
            self.project_id
        )

        self.assertEqual(
            result["all"]["all"],
            {
                "max_retake_count": 0,
                "evolution": {},
                "done": {"count": 0, "frames": 0, "drawings": 0},
                "retake": {"count": 0, "frames": 0, "drawings": 0},
                "other": {"count": 0, "frames": 0, "drawings": 0},
            },
        )

    def test_the_tasks_are_sorted_into_three_buckets(self):
        self.a_task("P01", self.task_status_done, nb_frames=10)
        self.a_task("P02", self.task_status_retake, nb_frames=20)
        self.a_task("P03", self.task_status, nb_frames=30)

        stats = self.episode_stats()

        self.assertEqual(
            stats["done"], {"count": 1, "frames": 10, "drawings": 0}
        )
        self.assertEqual(
            stats["retake"], {"count": 1, "frames": 20, "drawings": 0}
        )
        self.assertEqual(
            stats["other"], {"count": 1, "frames": 30, "drawings": 0}
        )

    def test_a_task_both_done_and_retaken_counts_as_done(self):
        # The current stats prefer is_done over is_retake.
        self.task_status_done.update({"is_retake": True})
        self.a_task("P01", self.task_status_done, nb_frames=10)

        stats = self.episode_stats()

        self.assertEqual(stats["done"]["count"], 1)
        self.assertEqual(stats["retake"]["count"], 0)

    def test_the_highest_retake_count_is_kept(self):
        self.a_task("P01", self.task_status_retake, retake_count=1)
        self.a_task("P02", self.task_status_retake, retake_count=4)
        self.a_task("P03", self.task_status_retake, retake_count=2)

        self.assertEqual(self.episode_stats()["max_retake_count"], 4)

    def test_the_evolution_counts_every_take_up_to_the_highest(self):
        """
        One take per column, up to the highest of the episode: a task
        retaken twice is a retake at takes one and two, and whatever its
        status says from take three on.
        """
        self.a_task("P01", self.task_status_done, retake_count=2)
        self.a_task("P02", self.task_status_done, retake_count=0)

        evolution = self.episode_stats()["evolution"]

        self.assertEqual(sorted(evolution), ["1", "2"])
        self.assertEqual(evolution["1"]["retake"]["count"], 1)
        self.assertEqual(evolution["1"]["done"]["count"], 1)
        self.assertEqual(evolution["2"]["retake"]["count"], 1)
        self.assertEqual(evolution["2"]["done"]["count"], 1)

    def test_the_stats_are_scoped_to_their_production(self):
        self.a_task("P01", self.task_status_done)
        elsewhere = self.generate_fixture_project_standard()

        result = stats_service.get_episode_retake_stats_for_project(
            str(elsewhere.id)
        )

        self.assertEqual(result["all"]["all"]["done"]["count"], 0)
