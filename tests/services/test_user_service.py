# -*- coding: UTF-8 -*-


from sqlalchemy import event

from zou.app import db
from zou.app.models.entity import Entity
from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.services import (
    comments_service,
    projects_service,
    tasks_service,
    user_service,
)
from zou.app.exceptions import (
    NotificationNotFoundException,
    WrongParameterException,
)
from tests.services.cases import UserContextTestCase

UNKNOWN = "00000000-0000-0000-0000-000000000000"


class RelatedProjectsTestCase(UserContextTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_task_status_to_review()
        self.generate_fixture_task()
        self.generate_fixture_user_client()
        self.task_id = str(self.task.id)
        self.project_id = str(self.project.id)

    def test_related_projects(self):
        with self.as_user():
            self.assertEqual(user_service.related_projects(), [])

        projects_service.add_team_member(self.project_id, self.user["id"])

        with self.as_user():
            projects = user_service.related_projects()

        self.assertEqual(
            [project["id"] for project in projects], [self.project_id]
        )

        # A production that is over leaves the list, membership or not.
        projects_service.update_project(
            self.project_id,
            {"project_status_id": projects_service.get_closed_status()["id"]},
        )

        with self.as_user():
            self.assertEqual(user_service.related_projects(), [])


class NotificationTestCase(UserContextTestCase):
    """
    The bell of one artist: what lands in it, what it can be narrowed on,
    and what a filter the driver cannot read answers.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_task_status_to_review()
        self.generate_fixture_task()
        self.generate_fixture_user_cg_artist()
        self.generate_fixture_user_client()
        self.artist = self.user_cg_artist
        self.task_id = str(self.task.id)
        self.project_id = str(self.project.id)
        projects_service.add_team_member(self.project_id, self.artist["id"])
        tasks_service.assign_task(self.task_id, self.artist["id"])

    def a_comment(self, author=None, text="A note"):
        """
        A comment on the task the artist holds, which rings their bell.
        """
        return comments_service.create_comment(
            (author or self.user)["id"],
            self.task_id,
            str(self.task_status_to_review.id),
            text,
            [],
            {},
            None,
        )

    def bell(self, **kwargs):
        with self.as_user(self.artist):
            return user_service.get_last_notifications(**kwargs)

    def texts(self, **kwargs):
        return [
            notification["comment_text"]
            for notification in self.bell(**kwargs)
        ]

    def test_the_bell_is_empty_until_someone_writes(self):
        self.assertEqual(self.bell(), [])

    def test_a_comment_on_a_held_task_rings_newest_first(self):
        self.a_comment(text="Lets go")
        self.a_comment(text="And again")

        self.assertEqual(self.texts(), ["And again", "Lets go"])

    def test_a_client_comment_comes_back_without_its_text(self):
        """
        An artist may not read what a client wrote, so the text is blanked
        rather than the notification hidden: the bell still rings.
        """
        self.a_comment(text="Lets go")
        self.a_comment(self.user_client, text="Wrong picture")

        self.assertEqual(self.texts(), ["", "Lets go"])

    def test_the_bell_holds_one_notification(self):
        self.a_comment(text="Lets go")
        self.a_comment(text="And again")
        first = self.bell()[1]

        self.assertEqual(self.texts(notification_id=first["id"]), ["Lets go"])

    def test_the_bell_names_the_playlist_of_a_playlist_notification(self):
        self.generate_fixture_playlist("Dailies")
        Notification.create(
            type="playlist-ready",
            person_id=self.artist["id"],
            author_id=self.user["id"],
            playlist_id=self.playlist.id,
        )
        notification = self.bell()[0]
        self.assertEqual(notification["playlist_id"], str(self.playlist.id))
        self.assertEqual(notification["playlist_name"], "Dailies")
        self.assertEqual(notification["project_id"], self.project_id)
        self.assertEqual(notification["project_name"], self.project.name)
        self.assertEqual(notification["playlist_for_entity"], "shot")
        self.assertEqual(notification["full_entity_name"], "")

    def test_the_bell_reads_the_comments_in_a_fixed_number_of_queries(self):
        """
        The comment, its previews, its mentions, and the entity name of
        every row used to be read one by one: a bell of a hundred
        notifications cost hundreds of queries on a listing the clients
        poll.
        """

        def count_queries(action):
            statements = []
            engine = db.engine

            def record(conn, cursor, statement, parameters, context, many):
                statements.append(statement)

            event.listen(engine, "before_cursor_execute", record)
            try:
                action()
            finally:
                event.remove(engine, "before_cursor_execute", record)
            return len(statements)

        # Count a second read each time: the first one fills the memoized
        # lookups (the person logging in, the organisation, the entity
        # types), and those misses would offset queries made per row.
        self.a_comment(text="One")
        self.assertEqual(len(self.bell()), 1)
        one = count_queries(self.bell)
        for text in ["Two", "Three", "Four", "Five", "Six"]:
            self.a_comment(text=text)
        self.assertEqual(len(self.bell()), 6)
        six = count_queries(self.bell)
        self.assertEqual(six, one)

    def test_the_bell_is_bounded_by_dates(self):
        self.a_comment(text="Lets go")

        self.assertEqual(self.texts(after="2020-01-01"), ["Lets go"])
        self.assertEqual(self.texts(before="2020-01-01"), [])
        self.assertEqual(self.texts(after="2100-01-01"), [])
        self.assertEqual(self.texts(before="2100-01-01"), ["Lets go"])

    def test_the_bell_holds_one_task_type(self):
        self.a_comment(text="Lets go")
        task_type_id = str(self.task.task_type_id)

        self.assertEqual(self.texts(task_type_id=task_type_id), ["Lets go"])
        self.assertEqual(self.texts(task_type_id=UNKNOWN), [])

    def test_the_bell_holds_one_task_status(self):
        self.a_comment(text="Lets go")
        status_id = str(self.task_status_to_review.id)

        self.assertEqual(self.texts(task_status_id=status_id), ["Lets go"])
        self.assertEqual(self.texts(task_status_id=UNKNOWN), [])

    def test_the_bell_holds_one_kind(self):
        self.a_comment(text="Lets go")

        self.assertEqual(self.texts(notification_type="comment"), ["Lets go"])
        self.assertEqual(self.texts(notification_type="mention"), [])

    def test_the_bell_holds_what_has_been_read(self):
        self.a_comment(text="Lets go")
        notification = self.bell()[0]

        self.assertEqual(self.texts(read=False), ["Lets go"])
        self.assertEqual(self.texts(read=True), [])

        with self.as_user(self.artist):
            user_service.update_notification(notification["id"], True)

        self.assertEqual(self.texts(read=False), [])
        self.assertEqual(self.texts(read=True), ["Lets go"])

    def test_the_bell_holds_what_is_being_watched(self):
        self.a_comment(text="Lets go")

        self.assertEqual(self.texts(watching=True), [])
        self.assertEqual(self.texts(watching=False), ["Lets go"])

        with self.as_user(self.artist):
            user_service.subscribe_to_task(self.task_id)

        self.assertEqual(self.texts(watching=True), ["Lets go"])
        self.assertEqual(self.texts(watching=False), [])

    def test_a_malformed_id_is_answered_as_a_wrong_parameter(self):
        """
        These reach the query as raw values, so the driver used to reject
        them and the route answered 500 where the caller made the mistake.
        """
        for field in ["notification_id", "task_type_id", "task_status_id"]:
            with self.subTest(field=field):
                with self.assertRaises(WrongParameterException):
                    self.bell(**{field: "notanid"})

    def test_a_date_the_driver_refuses_is_a_wrong_parameter(self):
        """
        The bounds are cast in SQL, so the driver is what refuses them and
        it only speaks when the query runs. One value per case: the failed
        statement leaves a transaction to roll back, and the rollback takes
        the fixtures this class logs in with.
        """
        with self.assertRaises(WrongParameterException):
            self.bell(after="notadate")

    def test_an_empty_date_bound_is_a_wrong_parameter(self):
        # A screen that drops its filter tends to send it empty rather
        # than leave it out, and empty is not a date either.
        with self.assertRaises(WrongParameterException):
            self.bell(before="")

    def test_get_notification(self):
        self.a_comment(text="Lets go")
        notification = self.bell()[0]

        with self.as_user(self.artist):
            again = user_service.get_notification(notification["id"])
        self.assertEqual(again, notification)

    def test_get_notification_of_someone_else(self):
        """
        The listing it runs is already scoped to the caller, so a
        notification of another person reads as missing rather than leaking.
        """
        self.a_comment(text="Lets go")
        notification = self.bell()[0]

        with self.as_user():
            with self.assertRaises(NotificationNotFoundException):
                user_service.get_notification(notification["id"])

    def test_update_notification_announces_both_ways(self):
        self.a_comment(text="Lets go")
        notification = self.bell()[0]

        events = self.capture_events("notification:read")
        with self.as_user(self.artist):
            read = user_service.update_notification(notification["id"], True)
        self.assertTrue(read["read"])
        self.assertEqual(len(events), 1)

        events = self.capture_events("notification:unread")
        with self.as_user(self.artist):
            unread = user_service.update_notification(
                notification["id"], False
            )
        self.assertFalse(unread["read"])
        self.assertEqual(len(events), 1)

    def test_update_notification_of_someone_else(self):
        self.a_comment(text="Lets go")
        notification = self.bell()[0]

        with self.as_user():
            with self.assertRaises(NotificationNotFoundException):
                user_service.update_notification(notification["id"], True)

    def test_the_unread_count_and_marking_them_all(self):
        self.a_comment(text="Lets go")
        self.a_comment(text="And again")

        with self.as_user(self.artist):
            self.assertEqual(user_service.get_unread_notifications_count(), 2)
            user_service.mark_notifications_as_read()
            self.assertEqual(user_service.get_unread_notifications_count(), 0)


class UserVisibleEntitiesTestCase(UserContextTestCase):
    """
    What the four listings behind the user context answer: the assets,
    asset types, sequences and episodes of one production the caller has a
    task on. Each is scoped three ways, by the production, by the caller's
    assignments, and by the production being open.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset_types()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_assigner()

        # Each production owns an asset of its own type plus one of the
        # shared Props type, so both asset listings have a row of the other
        # production to leave out.
        self.project = self.build_production(
            "Watched", self.asset_type_character
        )
        self.other = self.build_production(
            "Unwatched", self.asset_type_environment
        )

    def build_production(self, name, asset_type):
        """
        A production with one asset and one shot under a sequence and an
        episode, each carrying a task assigned to the caller.
        """
        project = Project.create(
            name=name, project_status_id=self.open_status.id
        )
        me = Person.get(self.user["id"])
        rows = {}
        for entity_name, entity_type_id, parent in [
            ("asset", asset_type.id, None),
            # Both productions also own a props asset, so the asset listing
            # has a row of the same type to leave out.
            ("props", self.asset_type.id, None),
            ("episode", self.episode_type.id, None),
            ("sequence", self.sequence_type.id, "episode"),
            ("shot", self.shot_type.id, "sequence"),
        ]:
            rows[entity_name] = Entity.create(
                name=f"{name} {entity_name}",
                project_id=project.id,
                entity_type_id=entity_type_id,
                parent_id=rows[parent].id if parent else None,
            )
        for entity_name in ["asset", "props", "shot"]:
            Task.create(
                name=f"{name} {entity_name} task",
                project_id=project.id,
                task_type_id=self.task_type.id,
                task_status_id=self.task_status.id,
                entity_id=rows[entity_name].id,
                assignees=[me],
                assigner_id=self.assigner.id,
            )
        project.team.append(me)
        project.save()
        self.__dict__.setdefault("rows", {})[name] = rows
        return project

    def test_the_listings_answer_for_one_production_only(self):
        project_id = str(self.project.id)
        watched = self.rows["Watched"]

        with self.as_user():
            assets = user_service.get_assets_for_asset_type(
                project_id, str(self.asset_type.id)
            )
            asset_types = user_service.get_asset_types_for_project(project_id)
            sequences = user_service.get_sequences_for_project(project_id)
            episodes = user_service.get_project_episodes(project_id)

        self.assertEqual(
            [asset["id"] for asset in assets], [str(watched["props"].id)]
        )
        self.assertEqual(
            sorted(asset_type["id"] for asset_type in asset_types),
            sorted(
                [str(self.asset_type.id), str(self.asset_type_character.id)]
            ),
        )
        self.assertEqual(
            [sequence["id"] for sequence in sequences],
            [str(watched["sequence"].id)],
        )
        self.assertEqual(
            [episode["id"] for episode in episodes],
            [str(watched["episode"].id)],
        )
