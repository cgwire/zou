import unittest

from unittest import mock

from zou.app.services import sync_service


class FetchEventsTestCase(unittest.TestCase):
    def test_paginates_until_short_page(self):
        pages = [
            [{"id": "ev-0"}, {"id": "ev-1"}, {"id": "ev-2"}],
            [{"id": "ev-3"}, {"id": "ev-4"}],
        ]
        calls = []

        def fake_fetch_all(path):
            calls.append(path)
            return pages[len(calls) - 1]

        with mock.patch.object(
            sync_service.gazu.client, "fetch_all", side_effect=fake_fetch_all
        ):
            events = sync_service._fetch_events(
                "events/last?limit=3", 3, paginate=True
            )
        self.assertEqual(len(events), 5)
        self.assertEqual(len(calls), 2)
        self.assertIn("cursor_event_id=ev-2", calls[1])

    def test_single_fetch_when_not_paginated(self):
        full_page = [{"id": "ev-0"}, {"id": "ev-1"}, {"id": "ev-2"}]
        with mock.patch.object(
            sync_service.gazu.client, "fetch_all", return_value=full_page
        ) as fetch_all:
            events = sync_service._fetch_events(
                "events/last?limit=3", 3, paginate=False
            )
        self.assertEqual(len(events), 3)
        fetch_all.assert_called_once()
