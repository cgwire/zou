from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.base import ApiDBTestCase
from zou.app.models.event import ApiEvent
from zou.app.services import events_service
from zou.app.utils import events


class EventsTestCase(ApiDBTestCase):
    __name__ = "test_handler"

    def setUp(self):
        super().setUp()
        self.counter = 1
        events.unregister_all()

    def handle_event(self, data={}):
        self.counter += 1

    def test_register(self):
        events.register("task:start", "inc_counter", self)
        events.emit("task:start")
        self.assertEqual(self.counter, 2)
        events.emit("task:stop")
        self.assertEqual(self.counter, 2)
        events.emit("task:start")
        self.assertEqual(self.counter, 3)

        event_models = events_service.get_last_events()
        self.assertEqual(len(event_models), 3)
        events.emit("task:start", persist=False)
        event_models = events_service.get_last_events()
        self.assertEqual(len(event_models), 3)

    def test_unregister(self):
        events.register("task:start", "inc_counter", self)
        events.unregister("task:start", "inc_counter")
        events.emit("task:start")
        self.assertEqual(self.counter, 1)

    def test_register_all(self):
        event_map = {"task:start": self, "task:new": self}
        events.register_all(event_map)
        events.emit("task:start")
        self.assertEqual(self.counter, 2)
        events.emit("task:stop")
        self.assertEqual(self.counter, 2)
        events.emit("task:start")
        self.assertEqual(self.counter, 3)
        events.emit("task:new")
        self.assertEqual(self.counter, 4)

        event_models = events_service.get_last_events()
        self.assertEqual(len(event_models), 4)
        self.assertEqual(event_models[0]["name"], "task:new")

    def test_failing_handler_does_not_stop_the_others(self):
        def fail(data):
            raise RuntimeError("boom")

        events.register("task:start", "inc_first", self)
        events.register(
            "task:start", "failing", SimpleNamespace(handle_event=fail)
        )
        events.register("task:start", "inc_last", self)
        events.emit("task:start")
        self.assertEqual(self.counter, 3)

    def test_handlers_are_enqueued_with_the_job_queue(self):
        events.register("task:start", "inc_counter", self)
        with patch("zou.app.config.ENABLE_JOB_QUEUE", True), patch(
            "zou.app.stores.queue_store.job_queue"
        ) as job_queue:
            events.emit("task:start", {"task_id": "abc"})
        self.assertEqual(self.counter, 1)
        job_queue.enqueue.assert_called_once()
        func, data = job_queue.enqueue.call_args.args
        self.assertEqual(func, self.handle_event)
        self.assertEqual(data["task_id"], "abc")
        self.assertIsNotNone(ApiEvent.get(data["id"]))

    def test_save_event_stores_the_none_string_as_null(self):
        api_event = events.save_event("task:start", {}, project_id="None")
        self.assertIsNone(ApiEvent.get(api_event.id).project_id)

    def test_save_hooks_run_once_and_a_failing_one_is_ignored(self):
        def fail(event):
            raise RuntimeError("boom")

        hook = MagicMock(__name__="hook")
        with patch.object(events, "save_hooks", []):
            events.add_save_hook(fail)
            events.add_save_hook(hook)
            events.add_save_hook(hook)
            api_event = events.save_event("task:start", {})
        hook.assert_called_once_with("task:start")
        self.assertIsNotNone(ApiEvent.get(api_event.id))
