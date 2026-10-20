from tests.base import ApiDBTestCase
from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.comment import Comment
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)
from zou.app.models.task import Task
from zou.app.models.time_spent import TimeSpent
from zou.app.services import breakdown_service, comments_service


class ProjectSyncRouteTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_shot_suite()
        self.generate_assigned_task()
        self.generate_fixture_shot_task()
        self.project_id = str(self.project.id)
        self.task_type_id = str(self.task_type.id)
        self.task_type_animation_id = str(self.task_type_animation.id)
        self.sequence_id = str(self.sequence.id)
        self.episode_id = str(self.episode.id)
        self.asset_type_id = str(self.asset_type.id)

        self.generate_fixture_subscription()
        self.generate_fixture_comment()
        self.generate_fixture_notification()
        self.generate_fixture_preview_file()
        self.generate_fixture_playlist("test")
        self.generate_fixture_build_job("2019-08-01T12:00:00")
        self.generate_fixture_milestone()
        breakdown_service.create_casting_link(self.shot.id, self.asset.id)

        self.generate_fixture_project_standard()
        self.generate_fixture_asset_standard()
        self.generate_fixture_task_standard()
        self.generate_fixture_sequence_standard()
        self.generate_fixture_shot_standard()
        self.task = self.task_standard
        self.project = self.project_standard
        self.generate_fixture_comment()
        self.generate_fixture_preview_file()
        self.generate_fixture_playlist("test 2")
        self.generate_fixture_build_job("2019-08-01T13:00:00")
        breakdown_service.create_casting_link(
            self.shot_standard.id, self.asset_standard.id
        )

    def test_get_build_jobs(self):
        jobs = self.get(f"/data/projects/{self.project_id}/build-jobs")
        self.assertEqual(len(jobs), 1)

    def test_get_subscriptions(self):
        subscriptions = self.get(
            f"/data/projects/{self.project_id}/subscriptions"
        )
        self.assertEqual(len(subscriptions), 1)

    def test_get_comments(self):
        comments = self.get(f"/data/projects/{self.project_id}/comments")
        self.assertEqual(len(comments), 1)

    def test_get_notifications(self):
        notitfications = self.get(
            f"/data/projects/{self.project_id}/notifications"
        )
        self.assertEqual(len(notitfications), 1)

    def test_get_preview_files(self):
        preview_files = self.get(
            f"/data/projects/{self.project_id}/preview-files"
        )
        self.assertEqual(len(preview_files), 1)

    def test_get_entity_links(self):
        links = self.get(f"/data/projects/{self.project_id}/entity-links")
        self.assertEqual(len(links), 2)

    def test_get_milestones(self):
        milestones = self.get(f"/data/projects/{self.project_id}/milestones")
        self.assertEqual(len(milestones), 1)

    def generate_extra_project_rows(self):
        """
        Give the first project at least two rows on every listing tested
        for pagination.
        """
        tasks = Task.query.filter_by(project_id=self.project_id).all()
        self.assertGreaterEqual(len(tasks), 2)
        comments_service.new_comment(
            tasks[1].id, self.task_status.id, self.person.id, "second"
        )
        comment = (
            Comment.query.filter(Comment.object_id == tasks[0].id)
            .order_by(Comment.created_at)
            .first()
        )
        if comment is None:
            comment = Comment.get(
                comments_service.new_comment(
                    tasks[0].id, self.task_status.id, self.person.id, "first"
                )["id"]
            )
        version = ProductionScheduleVersion.create(
            name="v1", project_id=self.project_id
        )
        for index, task in enumerate(tasks[:2]):
            TimeSpent.create(
                person_id=self.person.id,
                task_id=task.id,
                date=f"2024-01-1{index}",
                duration=60,
            )
            AttachmentFile.create(
                name=f"file{index}",
                extension="png",
                mimetype="image/png",
                comment_id=comment.id,
            )
            ProductionScheduleVersionTaskLink.create(
                production_schedule_version_id=version.id, task_id=task.id
            )
        self.generate_fixture_output_type()
        self.generate_fixture_output_file(revision=1)
        self.generate_fixture_output_file(revision=2)
        return comment.object_id, version.id

    def test_project_listings_paginate_on_demand(self):
        task_id, version_id = self.generate_extra_project_rows()
        project_path = f"/data/projects/{self.project_id}"
        for path in [
            f"{project_path}/tasks",
            f"{project_path}/comments",
            f"{project_path}/preview-files",
            f"{project_path}/notifications",
            f"{project_path}/time-spents",
            f"{project_path}/playlists/all",
            f"{project_path}/subscriptions",
            f"{project_path}/attachment-files",
            f"/data/tasks/{task_id}/attachment-files",
            f"{project_path}/output-files",
            f"{project_path}/build-jobs",
            f"/data/production-schedule-versions/{version_id}/task-links",
        ]:
            with self.subTest(path=path):
                self.assert_opt_in_pagination(path)

    def test_entity_links_page_path_forwards_limit(self):
        path = f"/data/projects/{self.project_id}/entity-links"
        result = self.get(f"{path}?page=1&limit=1")
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["data"]), 1)
        second = self.get(f"{path}?page=2&limit=1")
        self.assertNotEqual(result["data"][0]["id"], second["data"][0]["id"])
        # A limit alone keeps its own meaning there: a truncated plain list.
        self.assertEqual(len(self.get(f"{path}?limit=1")), 1)
