import time
from tests.base import ApiDBTestCase
from zou.app.models.event import ApiEvent

from zou.app.services import assets_service


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
