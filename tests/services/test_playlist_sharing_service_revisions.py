import json

from tests.blueprints.shared.base import BaseSharedRevisionTestCase
from zou.app.services import playlist_sharing_service


class SharedPlaylistRevisionsTestCase(BaseSharedRevisionTestCase):
    def test_the_other_guest_routes_read_the_same_revisions(self):
        """
        The guest routes that check a comment or an attachment against the
        playlist of the link read it through get_shared_playlist, which
        still returned every revision.
        """
        link = self.post(self.share_path(), {}, 201)
        payload = json.dumps(
            playlist_sharing_service.get_shared_playlist(link["token"]),
            default=str,
        )

        for row in (self.revision_2, self.layout_preview):
            self.assertNotIn(str(row.id), payload)
        self.assertNotIn("hidden-stroke", payload)
