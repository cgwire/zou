from datetime import datetime, timedelta

from freezegun import freeze_time

from tests.base import ApiDBTestCase

from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog
from zou.app.services import events_service
from zou.app.services.exception import WrongParameterException
from zou.app.utils import events

UNKNOWN = "00000000-0000-0000-0000-000000000000"


# Frozen mid-day: these cases place rows at explicit distances from now(),
# and the date filters are built from it, which flakes around midnight.
@freeze_time("2026-07-06T12:00:00")
class EventLogTestCase(ApiDBTestCase):
    """
    The activity log the administration screen reads: newest first, one page
    at a time, with a filter for each column it offers.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_person()

    def an_event(self, name="task:update", seconds_ago=0, **kwargs):
        """
        One line of the log. The distances are explicit because the listing
        is ordered on them, and rows sharing a timestamp have no order.
        """
        event = ApiEvent.create(name=name, **kwargs)
        event.update(
            {"created_at": datetime.now() - timedelta(seconds=seconds_ago)}
        )
        return event

    def seconds_ago(self, seconds):
        return datetime.now() - timedelta(seconds=seconds)

    def names(self, **kwargs):
        return [
            event["name"] for event in events_service.get_last_events(**kwargs)
        ]

    def test_the_log_is_newest_first(self):
        self.an_event("task:update", seconds_ago=1)
        self.an_event("comment:new", seconds_ago=3)
        self.an_event("person:update", seconds_ago=2)

        self.assertEqual(
            self.names(), ["task:update", "person:update", "comment:new"]
        )

    def test_a_line_of_the_log_carries_what_the_screen_shows(self):
        self.an_event(
            "task:update",
            project_id=self.project.id,
            user_id=self.person.id,
            data={"task_id": "1234"},
        )

        line = events_service.get_last_events()[0]

        self.assertEqual(
            sorted(line),
            sorted(
                ["id", "created_at", "name", "user_id", "project_id", "data"]
            ),
        )
        self.assertEqual(line["name"], "task:update")
        self.assertEqual(line["project_id"], str(self.project.id))
        self.assertEqual(line["user_id"], str(self.person.id))
        self.assertEqual(line["data"], {"task_id": "1234"})

    def test_the_log_is_paged(self):
        for second in range(3):
            self.an_event(f"task:step-{second}", seconds_ago=second)

        self.assertEqual(self.names(limit=2), ["task:step-0", "task:step-1"])

    def test_the_log_is_bounded_by_dates(self):
        self.an_event("task:new", seconds_ago=3)
        self.an_event("task:update", seconds_ago=1)

        self.assertEqual(self.names(before=self.seconds_ago(2)), ["task:new"])
        self.assertEqual(
            self.names(after=self.seconds_ago(2)), ["task:update"]
        )

    def test_the_log_resumes_from_a_cursor(self):
        newest = self.an_event("task:update", seconds_ago=1)
        self.an_event("comment:new", seconds_ago=3)

        self.assertEqual(
            self.names(cursor_event_id=str(newest.id)), ["comment:new"]
        )

    def test_the_log_refuses_a_cursor_it_cannot_place(self):
        with self.assertRaises(WrongParameterException):
            events_service.get_last_events(cursor_event_id=UNKNOWN)

    def test_the_log_holds_the_events_that_moved_a_file(self):
        self.an_event("preview-file:add-file", seconds_ago=1)
        self.an_event("person:set-thumbnail", seconds_ago=2)
        self.an_event("task:update", seconds_ago=3)

        self.assertEqual(
            self.names(only_files=True),
            ["preview-file:add-file", "person:set-thumbnail"],
        )

    def test_the_log_holds_the_events_of_one_production(self):
        self.an_event("task:update", project_id=self.project.id)
        self.an_event("person:update")

        self.assertEqual(
            self.names(project_id=str(self.project.id)), ["task:update"]
        )

    def test_the_log_is_held_to_the_allowed_productions(self):
        ApiEvent.create(name="task:update", project_id=self.project.id)
        ApiEvent.create(name="person:update")

        self.assertEqual(len(self.names()), 2)

        # An IN clause never matches NULL, so scoping on projects also hides
        # the events carrying no project at all.
        self.assertEqual(
            self.names(project_ids=[str(self.project.id)]), ["task:update"]
        )
        self.assertEqual(self.names(project_ids=[]), [])

    def test_the_log_holds_the_events_of_one_person(self):
        self.an_event("task:update", user_id=self.person.id)
        self.an_event("person:update")

        self.assertEqual(
            self.names(person_ids=[str(self.person.id)]), ["task:update"]
        )

    def test_the_log_refuses_a_person_id_of_the_wrong_shape(self):
        for values in [["not-a-uuid"], [str(self.person.id), ""]]:
            with self.subTest(values=values):
                with self.assertRaises(WrongParameterException):
                    events_service.get_last_events(person_ids=values)
                with self.assertRaises(WrongParameterException):
                    events_service.get_last_login_logs(person_ids=values)

    def test_the_log_holds_one_named_event(self):
        self.an_event("task:update")
        self.an_event("task:new")

        self.assertEqual(self.names(name="task:update"), ["task:update"])

    def test_the_log_holds_the_events_of_one_object_or_one_action(self):
        """
        A name is "<object>:<action>", so the object filter is a prefix and
        the action filter a suffix. Both take several values at once.
        """
        self.an_event("task:update", seconds_ago=1)
        self.an_event("comment:update", seconds_ago=2)
        self.an_event("person:new", seconds_ago=3)
        self.an_event("task:brand-new", seconds_ago=4)

        self.assertEqual(
            self.names(name_prefixes=["task", "comment"]),
            ["task:update", "comment:update", "task:brand-new"],
        )
        # Both sides are anchored on the colon: the object is the whole
        # object, and the action the whole action.
        self.assertEqual(self.names(name_suffixes=["new"]), ["person:new"])
        self.assertEqual(self.names(name_prefixes=["tas"]), [])

    def test_the_log_refuses_like_wildcards(self):
        # "task\n" is the fullmatch case: "$" alone would accept it.
        for value in ["%", "_", "task:", "Task", "", "task\n"]:
            with self.subTest(value=value):
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


class EventNamesTestCase(ApiDBTestCase):
    """
    The list of names the log filters are built from. It is memoized for an
    hour and shared by every caller, so what matters is when it is dropped.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()

    def test_get_event_names(self):
        ApiEvent.create(name="task:update")
        ApiEvent.create(name="task:update")
        ApiEvent.create(name="comment:new")

        self.assertEqual(
            events_service.get_event_names(), ["comment:new", "task:update"]
        )

    def test_invalidate_event_names_cache(self):
        names = events_service.get_event_names()
        self.assertNotIn("tests:brand-new", names)

        ApiEvent.create(name="tests:brand-new")
        # The memoized list still ignores the fresh name.
        self.assertEqual(events_service.get_event_names(), names)

        self.assertTrue(
            events_service.invalidate_event_names_cache("tests:brand-new")
        )
        self.assertIn("tests:brand-new", events_service.get_event_names())

        # A name already in the list costs a cache hit and nothing else.
        self.assertFalse(
            events_service.invalidate_event_names_cache("tests:brand-new")
        )

    def test_get_event_names_reflects_a_freshly_emitted_event(self):
        self.assertNotIn("tests:brand-new", events_service.get_event_names())

        events.emit("tests:brand-new", project_id=str(self.project.id))

        self.assertIn("tests:brand-new", events_service.get_event_names())


@freeze_time("2026-07-06T12:00:00")
class LoginLogTestCase(ApiDBTestCase):
    """
    Who logged in, from where, through what. Same cursor pagination as the
    event log, on its own table.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_person()
        # Logging the test case's admin in already wrote one line.
        self.person_id = str(self.person.id)

    def a_login(self, seconds_ago=0, person_id=None, origin="web"):
        log = events_service.create_login_log(
            person_id or self.person_id, "127.0.0.1", origin
        )
        row = LoginLog.get(log["id"])
        row.update(
            {"created_at": datetime.now() - timedelta(seconds=seconds_ago)}
        )
        return log

    def mine(self, **kwargs):
        return events_service.get_last_login_logs(
            person_ids=[self.person_id], **kwargs
        )

    def test_create_login_log(self):
        log = self.a_login(origin="script")

        self.assertEqual(log["person_id"], self.person_id)
        self.assertEqual(log["ip_address"], "127.0.0.1")
        self.assertEqual(log["origin"], "script")

    def test_the_logs_are_newest_first_and_paged(self):
        logs = {
            second: self.a_login(seconds_ago=second) for second in [3, 1, 2]
        }

        self.assertEqual(
            [log["id"] for log in self.mine()],
            [logs[1]["id"], logs[2]["id"], logs[3]["id"]],
        )
        self.assertEqual(
            [log["id"] for log in self.mine(limit=2)],
            [logs[1]["id"], logs[2]["id"]],
        )
        # The admin of the test case logged in too, and is not filtered out
        # of the unscoped listing.
        self.assertEqual(len(events_service.get_last_login_logs()), 4)

    def test_a_line_carries_what_the_screen_shows(self):
        self.a_login()

        line = self.mine()[0]

        self.assertEqual(
            sorted(line),
            sorted(["id", "created_at", "ip_address", "person_id", "origin"]),
        )

    def test_the_logs_are_bounded_by_dates(self):
        old = self.a_login(seconds_ago=3)
        recent = self.a_login(seconds_ago=1)
        boundary = datetime.now() - timedelta(seconds=2)

        self.assertEqual(
            [log["id"] for log in self.mine(before=boundary)], [old["id"]]
        )
        self.assertEqual(
            [log["id"] for log in self.mine(after=boundary)], [recent["id"]]
        )

    def test_the_logs_resume_from_a_cursor(self):
        old = self.a_login(seconds_ago=3)
        recent = self.a_login(seconds_ago=1)

        self.assertEqual(
            [log["id"] for log in self.mine(cursor_login_log_id=recent["id"])],
            [old["id"]],
        )

    def test_the_logs_refuse_a_cursor_they_cannot_place(self):
        with self.assertRaises(WrongParameterException):
            events_service.get_last_login_logs(cursor_login_log_id=UNKNOWN)
