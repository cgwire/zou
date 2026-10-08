"""
Base test cases shared by several service test files: each sets up the
fixtures its tests need and holds no test of its own.
"""

from sqlalchemy import event
from tests.base import ApiDBTestCase
from contextlib import contextmanager
from flask import g
from flask_jwt_extended import verify_jwt_in_request

from zou.app import db, app
from zou.app.services import comments_service
from zou.app.models.person import Person
from zou.app.models.notification import Notification


class TaskTestCase(ApiDBTestCase):
    """
    An asset and a shot, each carrying one task. Holds no test of its own.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_to_review()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()

        self.project_id = str(self.project.id)
        self.task_id = str(self.task.id)
        self.person_id = str(self.person.id)
        self.open_status_id = str(self.task_status.id)
        self.wip_status_id = str(self.task_status_wip.id)
        self.to_review_status_id = str(self.task_status_to_review.id)

    def collect_statements(self):
        """
        Record every statement the session sends until the returned context
        manager exits. Used to catch the queries a reader must not run.
        """
        statements = []

        def collect(conn, cursor, statement, *args, **kwargs):
            statements.append(statement)

        engine = db.session.get_bind()

        class Recorder:
            def __enter__(inner):
                event.listen(engine, "before_cursor_execute", collect)
                return statements

            def __exit__(inner, *args):
                event.remove(engine, "before_cursor_execute", collect)

        return Recorder()


class PreviewFileTestCase(ApiDBTestCase):
    """
    One task to hang preview files from. Holds no test of its own.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.project_id = str(self.project.id)
        self.user_id = self.user["id"]
        self.generate_fixture_asset()
        self.generate_fixture_task()

    def tearDown(self):
        super().tearDown()
        self.delete_test_folder()


class AssetsTestCase(ApiDBTestCase):
    """
    One production with a single asset type and a shot to cast into.
    Holds no test of its own.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

    def a_character(self):
        """
        A second asset, of a second type, so that a reading has something
        to order and something to leave out.
        """
        self.generate_fixture_asset_types()
        return self.generate_fixture_asset_character()


class ShotsTestCase(ApiDBTestCase):
    """
    One production holding an episode, a sequence, a shot, a scene and an
    asset: the five kinds this service tells apart.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()
        self.generate_fixture_asset()

    def generate_shot_task(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        return self.generate_fixture_shot_task()


class PersonsTestCase(ApiDBTestCase):
    """
    The admin the base class logs in as, plus one studio member.
    Holds no test of its own.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_person()
        self.generate_fixture_department()
        self.person_id = str(self.person.id)
        self.person_email = self.person.email
        self.person_desktop_login = self.person.desktop_login

    def a_guest(self):
        """
        A person created by the shared playlist flow: not part of the
        studio, and left out of every team listing.
        """
        return Person.create(
            first_name="Guest",
            last_name="Reviewer",
            email="guest-reviewer@guest.kitsu",
            role="client",
            is_guest=True,
        )


class NotificationsTestCase(ApiDBTestCase):
    """
    One production with a sequence and a shot, and a task on that shot.
    Holds no test of its own.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.sequence_dict = self.sequence.serialize()

        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.task_type_dict = self.task_type_animation.serialize()
        self.generate_fixture_task_status()
        self.task = self.generate_fixture_shot_task()
        self.task_dict = self.task.serialize(relations=True)
        # generate_fixture_shot_task assigned the first person to the task
        # and generate_fixture_person repoints self.person, so both are
        # named here rather than read off the attribute afterwards.
        self.assignee_id = str(self.person.id)
        self.outsider_id = str(
            self.generate_fixture_person(
                first_name="Jane", email="jane.doe@gmail.com"
            ).id
        )
        self.admin_id = self.user["id"]

        self.comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.admin_id, "first comment"
        )

    def kinds(self):
        """
        Every notification as a (type, recipient) pair, which is what these
        functions are really deciding.
        """
        return sorted(
            (str(notification.type.code), str(notification.person_id))
            for notification in Notification.get_all()
        )


class UserContextTestCase(ApiDBTestCase):
    """
    Every function of this service answers for whoever is on the request,
    so each case runs inside one carrying their token rather than patching
    get_current_user: the permission helpers read the token, not the patch.
    """

    @contextmanager
    def as_user(self, user=None):
        user = user or self.user
        self.log_in(user["email"])
        with app.test_request_context(headers=self.auth_headers):
            # flask.g lives on the application context, which the test case
            # pushed once and test_request_context reuses: the project role
            # resolved for an earlier caller has to go, the way it does
            # between two real requests. Pushing a fresh application
            # context instead would hand out a new database session and
            # detach everything the fixtures hold.
            g.pop("project_role", None)
            verify_jwt_in_request()
            yield user


class SpyProgress:
    """
    Records what a command reports so the tests can check the counting
    without a terminal.
    """

    def __init__(self):
        self.total = None
        self.advanced = 0
        self.stopped = False

    def start(self, total):
        self.total = total

    def advance(self):
        self.advanced += 1

    def stop(self):
        self.stopped = True
