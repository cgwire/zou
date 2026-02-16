# -*- coding: UTF-8 -*-
from tests.base import ApiDBTestCase

from zou.app.models.preview_file import PreviewFile
from zou.app.services import tasks_service
from zou.app.services.exception import RevisionAlreadyExistsException


class PreviewRevisionTestCase(ApiDBTestCase):
    """
    Test revision uniqueness check and propagation for preview files.
    """

    def setUp(self):
        super(PreviewRevisionTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()

        self.task_id = str(self.task.id)
        self.wip_status_id = str(self.task_status_wip.id)

    def create_comment(self):
        """Create a comment on the task and return it."""
        path = f"/actions/tasks/{self.task_id}/comment/"
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "test comment",
        }
        return self.post(path, data)

    def add_preview(self, comment_id, revision=None):
        """Add a preview to comment. Returns preview_file dict."""
        path = (
            f"/actions/tasks/{self.task_id}/comments/{comment_id}/add-preview"
        )
        data = {"revision": revision} if revision else {}
        return self.post(path, data)

    def add_extra_preview(self, comment_id, preview_file_id):
        """Add an extra preview to comment."""
        path = f"/actions/tasks/{self.task_id}/comments/{comment_id}/preview-files/{preview_file_id}"
        return self.post(path, {})

    def test_duplicate_revision_rejected(self):
        """Creating a new main preview with existing revision should fail."""
        # Create first comment with revision 1
        comment1 = self.create_comment()
        preview1 = self.add_preview(comment1["id"], revision=1)
        self.assertEqual(preview1["revision"], 1)

        # Create second comment and try to use revision 1 again
        comment2 = self.create_comment()
        path = f"/actions/tasks/{self.task_id}/comments/{comment2['id']}/add-preview"
        response = self.post(path, {"revision": 1}, code=400)
        self.assertIn("already exists", response.get("message", ""))

    def test_extra_preview_same_revision_allowed(self):
        """Extra previews should be allowed to share the same revision."""
        comment = self.create_comment()

        # Create main preview with revision 1
        preview1 = self.add_preview(comment["id"], revision=1)
        self.assertEqual(preview1["revision"], 1)
        self.assertEqual(preview1["position"], 1)

        # Add extra preview - should work with same revision
        preview2 = self.add_extra_preview(comment["id"], preview1["id"])
        self.assertEqual(preview2["revision"], 1)
        self.assertEqual(preview2["position"], 2)

    def test_update_revision_to_existing_rejected(self):
        """Updating a main preview to an existing revision should fail."""
        # Create two comments with different revisions
        comment1 = self.create_comment()
        preview1 = self.add_preview(comment1["id"], revision=1)

        comment2 = self.create_comment()
        preview2 = self.add_preview(comment2["id"], revision=2)

        # Try to update preview2 to revision 1 - should fail
        path = f"/data/preview-files/{preview2['id']}"
        response = self.put(path, {"revision": 1}, code=400)
        self.assertIn("already exists", response.get("message", ""))

    def test_update_revision_propagates_to_extras(self):
        """Updating main preview revision should propagate to extra previews."""
        comment = self.create_comment()

        # Create main preview with revision 1
        preview1 = self.add_preview(comment["id"], revision=1)

        # Add extra preview
        preview2 = self.add_extra_preview(comment["id"], preview1["id"])

        # Verify both have revision 1
        self.assertEqual(preview1["revision"], 1)
        self.assertEqual(preview2["revision"], 1)

        # Update main preview to revision 5
        path = f"/data/preview-files/{preview1['id']}"
        updated_preview = self.put(path, {"revision": 5})
        self.assertEqual(updated_preview["revision"], 5)

        # Check that extra preview also has revision 5
        extra_preview = PreviewFile.get(preview2["id"])
        self.assertEqual(extra_preview.revision, 5)

    def test_check_revision_is_unique_service(self):
        """Direct test of check_revision_is_unique_for_task service function."""
        # Create a preview with revision 1
        self.generate_fixture_preview_file(revision=1, position=1)

        # Check should raise for existing revision
        with self.assertRaises(RevisionAlreadyExistsException):
            tasks_service.check_revision_is_unique_for_task(
                str(self.task.id), revision=1
            )

        # Check should pass for non-existing revision
        tasks_service.check_revision_is_unique_for_task(
            str(self.task.id), revision=2
        )

    def test_check_revision_exclude_self(self):
        """Check should exclude the preview being updated."""
        preview = self.generate_fixture_preview_file(revision=1, position=1)

        # Should not raise when excluding the preview itself
        tasks_service.check_revision_is_unique_for_task(
            str(self.task.id),
            revision=1,
            exclude_preview_id=str(preview.id),
        )

    def test_check_ignores_extra_previews(self):
        """Check should only consider main previews (position 1)."""
        # Create extra preview (position 2) with revision 1
        self.generate_fixture_preview_file(revision=1, position=2)

        # Should not raise because there's no main preview with revision 1
        tasks_service.check_revision_is_unique_for_task(
            str(self.task.id), revision=1
        )
