from datetime import datetime, timedelta

from tests.base import ApiDBTestCase

from zou.app.models.event import ApiEvent
from zou.app.services import events_service, assets_service


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
