from datetime import datetime, timedelta

from freezegun import freeze_time

from tests.base import ApiDBTestCase
from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog
from zou.app.models.person import Person
from zou.app.models.project import Project

from zou.app.services import assets_service


# Frozen mid-day time: these tests build date-boundary filters (before/
# after) from now(), which flakes around midnight otherwise.
@freeze_time("2026-07-06T12:00:00")
class EventsRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(EventsRoutesTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()

    def test_get_last_events(self):
        now = datetime.now().replace(microsecond=0)
        for name in ["test 1", "test 2", "test 3", "test 4"]:
            assets_service.create_asset(
                self.project.id, self.asset_type.id, name, "", {}
            )

        events_db = ApiEvent.query.order_by(ApiEvent.created_at).all()
        for i, event in enumerate(events_db):
            event.update({"created_at": now - timedelta(seconds=4 - i)})

        after = (now - timedelta(seconds=5)).isoformat()
        before = (now - timedelta(seconds=2)).isoformat()

        events = self.get("/data/events/last")
        self.assertEqual(len(events), 4)
        events = self.get("/data/events/last?limit=2")
        self.assertEqual(len(events), 2)
        events = self.get(f"/data/events/last?before={before}")
        self.assertEqual(len(events), 2)
        events = self.get(f"/data/events/last?before={before}&after={after}")
        self.assertEqual(len(events), 2)

        ApiEvent.create(name="preview-file:add-file")
        ApiEvent.create(name="person:set-thumbnail")
        events = self.get("/data/events/last")
        self.assertEqual(len(events), 6)
        events = self.get("/data/events/last?only_files=true")
        self.assertEqual(len(events), 2)

    def test_get_last_events_serializes_project_id(self):
        ApiEvent.create(name="task:update", project_id=self.project.id)
        events = self.get("/data/events/last")
        self.assertEqual(events[0]["project_id"], str(self.project.id))

    def test_get_last_events_person_ids(self):
        self.generate_fixture_user_manager()
        self.generate_fixture_user_cg_artist()
        ApiEvent.create(name="task:update", user_id=self.user["id"])
        ApiEvent.create(name="task:update", user_id=self.user_manager["id"])
        ApiEvent.create(name="task:update", user_id=self.user_cg_artist["id"])

        events = self.get(
            f"/data/events/last?person_ids={self.user['id']}"
            f"&person_ids={self.user_manager['id']}"
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(
            {event["user_id"] for event in events},
            {str(self.user["id"]), str(self.user_manager["id"])},
        )

    def test_get_last_events_invalid_person_ids(self):
        self.get("/data/events/last?person_ids=invalid", 400)

    def test_get_last_events_name_prefixes(self):
        ApiEvent.create(name="task:update")
        ApiEvent.create(name="comment:new")
        ApiEvent.create(name="asset:delete")

        events = self.get("/data/events/last?name_prefixes=task")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "task:update")

        events = self.get(
            "/data/events/last?name_prefixes=task&name_prefixes=comment"
        )
        self.assertEqual(len(events), 2)

    def test_get_last_events_name_suffixes(self):
        ApiEvent.create(name="task:update")
        ApiEvent.create(name="comment:new")
        ApiEvent.create(name="asset:new")

        events = self.get("/data/events/last?name_suffixes=new")
        self.assertEqual(len(events), 2)

    def test_get_last_events_name_prefixes_and_suffixes(self):
        ApiEvent.create(name="task:update")
        ApiEvent.create(name="task:new")
        ApiEvent.create(name="comment:new")

        events = self.get(
            "/data/events/last?name_prefixes=task&name_suffixes=new"
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "task:new")

    def test_get_last_events_name_parts_reject_like_wildcards(self):
        ApiEvent.create(name="task:update")
        # "%" and "_" must never reach the LIKE pattern as wildcards.
        self.get("/data/events/last?name_prefixes=%25", 400)
        self.get("/data/events/last?name_suffixes=_", 400)
        self.get("/data/events/last?name_prefixes=Task", 400)

    def test_get_last_events_manager_is_scoped_to_his_projects(self):
        other_project = Project.create(
            name="Other project", project_status_id=self.open_status.id
        )
        self.generate_fixture_user_manager()
        self.project.team.append(Person.get(self.user_manager["id"]))
        self.project.save()

        ApiEvent.create(name="task:update", project_id=self.project.id)
        ApiEvent.create(name="task:update", project_id=other_project.id)
        ApiEvent.create(name="person:update")

        events = self.get("/data/events/last")
        self.assertEqual(len(events), 3)

        self.log_in_manager()
        events = self.get("/data/events/last")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["project_id"], str(self.project.id))

    def test_get_last_events_manager_cannot_target_other_project(self):
        other_project = Project.create(
            name="Other project", project_status_id=self.open_status.id
        )
        self.generate_fixture_user_manager()
        self.project.team.append(Person.get(self.user_manager["id"]))
        self.project.save()

        self.log_in_manager()
        self.get(f"/data/events/last?project_id={other_project.id}", 403)
        self.get(f"/data/events/last?project_id={self.project.id}", 200)

    def test_get_event_names(self):
        ApiEvent.create(name="task:update")
        ApiEvent.create(name="comment:new")
        ApiEvent.create(name="task:update")

        names = self.get("/data/events/names")
        self.assertEqual(names, ["comment:new", "task:update"])

    def test_get_event_names_permissions(self):
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.get("/data/events/names", 403)


class LoginLogsRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(LoginLogsRoutesTestCase, self).setUp()
        LoginLog.query.delete()

    def create_login_logs(self, count):
        base = datetime.now() - timedelta(seconds=count)
        for i in range(count):
            LoginLog.create(
                person_id=self.user["id"],
                ip_address=f"192.168.1.{i}",
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
        now = datetime.now().replace(microsecond=0)
        for i in range(3):
            LoginLog.create(
                person_id=self.user["id"],
                ip_address=f"192.168.1.{i}",
                origin="web",
                created_at=now - timedelta(seconds=3 - i),
            )
        before = (now - timedelta(seconds=1)).isoformat()
        logs = self.get(f"/data/events/login-logs/last?before={before}")
        self.assertEqual(len(logs), 2)

    def test_get_last_login_logs_after(self):
        now = datetime.now().replace(microsecond=0)
        for i in range(3):
            LoginLog.create(
                person_id=self.user["id"],
                ip_address=f"192.168.1.{i}",
                origin="web",
                created_at=now - timedelta(seconds=3 - i),
            )
        after = (now - timedelta(seconds=2)).isoformat()
        logs = self.get(f"/data/events/login-logs/last?after={after}")
        self.assertEqual(len(logs), 1)

    def test_get_last_login_logs_cursor(self):
        self.create_login_logs(3)
        logs = self.get("/data/events/login-logs/last?limit=2")
        cursor = logs[-1]["id"]
        logs = self.get(
            f"/data/events/login-logs/last?cursor_login_log_id={cursor}"
        )
        self.assertEqual(len(logs), 1)

    def test_get_last_login_logs_invalid_cursor(self):
        self.get(
            "/data/events/login-logs/last?cursor_login_log_id=invalid",
            400,
        )

    def test_get_last_login_logs_person_ids(self):
        self.generate_fixture_user_manager()
        LoginLog.create(
            person_id=self.user["id"], ip_address="192.168.1.1", origin="web"
        )
        LoginLog.create(
            person_id=self.user_manager["id"],
            ip_address="192.168.1.2",
            origin="web",
        )

        logs = self.get(
            f"/data/events/login-logs/last?person_ids={self.user_manager['id']}"
        )
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["person_id"], str(self.user_manager["id"]))

    def test_get_last_login_logs_invalid_person_ids(self):
        self.get("/data/events/login-logs/last?person_ids=invalid", 400)

    def test_get_last_login_logs_permissions(self):
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.get("/data/events/login-logs/last", 403)

    def test_get_last_login_logs_are_admin_only(self):
        # Login logs expose everyone's IP address: managers are denied.
        self.generate_fixture_user_manager()
        self.log_in_manager()
        self.get("/data/events/login-logs/last", 403)
