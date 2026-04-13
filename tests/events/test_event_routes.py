import time
from datetime import datetime, timedelta

from tests.base import ApiDBTestCase
from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog

from zou.app.services import assets_service, events_service


class EventsRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(EventsRoutesTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()

    def test_get_last_events(self):
        asset = assets_service.create_asset(
            self.project.id, self.asset_type.id, "test 1", "", {}
        )
        after = asset["created_at"]
        time.sleep(1)
        asset = assets_service.create_asset(
            self.project.id, self.asset_type.id, "test 2", "", {}
        )
        time.sleep(1)
        asset = assets_service.create_asset(
            self.project.id, self.asset_type.id, "test 3", "", {}
        )
        before = asset["created_at"]
        time.sleep(1)
        asset = assets_service.create_asset(
            self.project.id, self.asset_type.id, "test 4", "", {}
        )

        events = self.get("/data/events/last")
        self.assertEqual(len(events), 4)
        events = self.get("/data/events/last?limit=2")
        self.assertEqual(len(events), 2)
        events = self.get("/data/events/last?before=%s" % before)
        self.assertEqual(len(events), 2)
        events = self.get(
            "/data/events/last?before=%s&after=%s" % (before, after)
        )
        self.assertEqual(len(events), 2)

        ApiEvent.create(name="preview-file:add-file")
        ApiEvent.create(name="person:set-thumbnail")
        events = self.get("/data/events/last")
        self.assertEqual(len(events), 6)
        events = self.get("/data/events/last?only_files=true")
        self.assertEqual(len(events), 2)


class LoginLogsRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(LoginLogsRoutesTestCase, self).setUp()
        LoginLog.query.delete()

    def create_login_logs(self, count):
        base = datetime.now() - timedelta(seconds=count)
        for i in range(count):
            LoginLog.create(
                person_id=self.user["id"],
                ip_address="192.168.1.%d" % i,
                origin="web",
                created_at=base + timedelta(seconds=i),
            )

    def test_get_last_login_logs(self):
        self.create_login_logs(3)
        logs = self.get("/data/events/login-logs/last")
        self.assertEqual(len(logs), 3)
        self.assertIn("id", logs[0])
        self.assertIn("created_at", logs[0])
        self.assertIn("ip_address", logs[0])
        self.assertIn("person_id", logs[0])
        self.assertIn("origin", logs[0])

    def test_get_last_login_logs_limit(self):
        self.create_login_logs(3)
        logs = self.get("/data/events/login-logs/last?limit=2")
        self.assertEqual(len(logs), 2)

    def test_get_last_login_logs_before(self):
        self.create_login_logs(2)
        before = self.get("/data/events/login-logs/last")[0]["created_at"]
        time.sleep(0.5)
        self.create_login_logs(1)
        logs = self.get("/data/events/login-logs/last?before=%s" % before)
        self.assertEqual(len(logs), 1)

    def test_get_last_login_logs_after(self):
        self.create_login_logs(1)
        after = self.get("/data/events/login-logs/last")[0]["created_at"]
        time.sleep(0.5)
        self.create_login_logs(2)
        logs = self.get("/data/events/login-logs/last?after=%s" % after)
        self.assertEqual(len(logs), 2)

    def test_get_last_login_logs_cursor(self):
        self.create_login_logs(3)
        logs = self.get("/data/events/login-logs/last?limit=2")
        cursor = logs[-1]["id"]
        logs = self.get(
            "/data/events/login-logs/last?cursor_login_log_id=%s" % cursor
        )
        self.assertEqual(len(logs), 1)

    def test_get_last_login_logs_invalid_cursor(self):
        self.get(
            "/data/events/login-logs/last?cursor_login_log_id=invalid",
            400,
        )

    def test_get_last_login_logs_permissions(self):
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.get("/data/events/login-logs/last", 403)
