from zou.app.models.build_job import BuildJob
from zou.app.models.day_off import DayOff
from zou.app.models.milestone import Milestone
from zou.app.models.notification import Notification
from zou.app.models.playlist import Playlist
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task


class ScheduleFactories:
    """
    Playlists, build jobs, subscriptions, notifications and schedule.
    """

    def generate_fixture_playlist(
        self,
        name,
        project_id=None,
        episode_id=None,
        for_entity="shot",
        for_client=False,
        is_for_all=False,
        task_type_id=None,
    ):
        if project_id is None:
            project_id = self.project.id
        self.playlist = Playlist.create(
            name=name,
            project_id=project_id,
            episode_id=episode_id,
            for_entity=for_entity,
            is_for_all=is_for_all,
            for_client=for_client,
            task_type_id=task_type_id,
            shots=[],
        )
        return self.playlist.serialize()

    def generate_fixture_build_job(self, ended_at, playlist_id=None):
        if playlist_id is None:
            playlist_id = self.playlist.id
        self.build_job = BuildJob.create(
            status="succeeded",
            job_type="movie",
            ended_at=ended_at,
            playlist_id=playlist_id,
        )
        return self.build_job.serialize()

    def generate_fixture_subscription(self, task_id=None):
        task = self.task
        if task_id is not None:
            task = Task.get(task_id)

        self.subscription = Subscription.create(
            person_id=self.user["id"],
            task_id=task.id,
            entity_id=task.entity_id,
            task_type_id=task.task_type_id,
        )
        return self.subscription.serialize()

    def generate_fixture_notification(self):
        self.notification = Notification.create(
            type="comment",
            person_id=self.user["id"],
            author_id=self.person.id,
            comment_id=self.comment["id"],
            task_id=self.task.id,
        )
        return self.notification.serialize()

    def generate_fixture_milestone(self):
        self.milestone = Milestone.create(
            name="Test Milestone",
            project_id=self.project.id,
            task_type_id=self.task_type.id,
        )
        return self.milestone.serialize()

    def generate_fixture_schedule_item(
        self, task_type_id=None, object_id=None
    ):
        if task_type_id is None:
            task_type_id = self.task_type.id
        self.schedule_item = ScheduleItem.create(
            project_id=self.project.id,
            task_type_id=self.task_type.id,
            object_id=object_id,
        )
        return self.schedule_item.serialize()

    def generate_fixture_day_off(self, date, end_date=None, person_id=None):
        if person_id is None:
            person_id = self.person.id
        self.day_off = DayOff.create(
            date=date, end_date=end_date or date, person_id=person_id
        )
        return self.day_off.serialize()
