from datetime import datetime, timedelta

from freezegun import freeze_time

from tests.base import ApiDBTestCase

from zou.app.models.event import ApiEvent
from zou.app.services import events_service, assets_service
from zou.app.services.exception import WrongParameterException


# Frozen mid-day time: these tests build date-boundary filters (before/
# after) from now(), which flakes around midnight otherwise.
@freeze_time("2026-07-06T12:00:00")
class EventsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(EventsServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()

    def test_get_last_events(self):
        now = datetime.now().replace(microsecond=0)
        for name in ["test 1", "test 2", "test 3"]:
            assets_service.create_asset(
                self.project.id, self.asset_type.id, name, "", {}
            )

        events_db = ApiEvent.query.order_by(ApiEvent.created_at).all()
        for i, event in enumerate(events_db):
            event.update({"created_at": now - timedelta(seconds=3 - i)})

        events = events_service.get_last_events()
        self.assertEqual(len(events), 3)
        events = events_service.get_last_events(limit=2)
        self.assertEqual(len(events), 2)
        before = now - timedelta(seconds=1)
        events = events_service.get_last_events(before=before)
        self.assertEqual(len(events), 2)

    def test_get_last_events_project_ids_hides_global_events(self):
        ApiEvent.create(name="task:update", project_id=self.project.id)
        ApiEvent.create(name="person:update")

        events = events_service.get_last_events()
        self.assertEqual(len(events), 2)

        # An IN clause never matches NULL, so scoping on projects also hides
        # the events carrying no project at all.
        events = events_service.get_last_events(
            project_ids=[str(self.project.id)]
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "task:update")

        events = events_service.get_last_events(project_ids=[])
        self.assertEqual(len(events), 0)

    def test_get_last_events_rejects_like_wildcards(self):
        for value in ["%", "_", "task:", "Task", ""]:
            self.assertRaises(
                WrongParameterException,
                events_service.get_last_events,
                name_prefixes=[value],
            )
            self.assertRaises(
                WrongParameterException,
                events_service.get_last_events,
                name_suffixes=[value],
            )

    def test_get_event_names(self):
        ApiEvent.create(name="task:update")
        ApiEvent.create(name="task:update")
        ApiEvent.create(name="comment:new")
        self.assertEqual(
            events_service.get_event_names(), ["comment:new", "task:update"]
        )

    def test_get_last_login_logs(self):
        self.generate_fixture_person()
        login_logs = events_service.get_last_login_logs()
        self.assertEqual(len(login_logs), 1)

        events_service.create_login_log(self.person.id, "127.0.0.1", "web")
        events_service.create_login_log(self.person.id, "127.0.0.1", "web")
        events_service.create_login_log(self.person.id, "127.0.0.1", "web")
        login_logs = events_service.get_last_login_logs()
        self.assertEqual(len(login_logs), 4)
        login_logs = events_service.get_last_login_logs(limit=2)
        self.assertEqual(len(login_logs), 2)
