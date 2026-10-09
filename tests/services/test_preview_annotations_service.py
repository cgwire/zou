from contextlib import contextmanager
from unittest.mock import patch

from zou.app.services import files_service, preview_annotations_service
from zou.app.exceptions import AnnotationLockTimeoutException
from tests.services.cases import PreviewFileTestCase


class PreviewFileAnnotationsTestCase(PreviewFileTestCase):
    """
    The annotations a preview file carries. Each update is a read, a merge
    and a write, under a lock, addressing drawing objects by id.
    """

    def setUp(self):
        super().setUp()
        self.preview_file_id = str(self.generate_fixture_preview_file().id)
        self.at_zero = [self.annotation("0", "obj1")]
        self.at_two = [self.annotation("2", "obj2")]
        self.also_at_zero = [self.annotation("0", "obj3")]

    def annotation(self, time, object_id, path=None):
        return {
            "time": time,
            "drawing": {
                "objects": [
                    {
                        "id": object_id,
                        "type": "path",
                        "path": path or ["Q", 0, 10],
                    }
                ]
            },
        }

    def annotate(self, **changes):
        """
        Run one annotation update and return what it left on the preview.
        """
        preview_annotations_service.update_preview_file_annotations(
            self.user_id, self.project_id, self.preview_file_id, **changes
        )
        return files_service.get_preview_file(self.preview_file_id)[
            "annotations"
        ]

    def test_an_addition_lands_on_the_preview(self):
        self.assertEqual(self.annotate(additions=self.at_zero), self.at_zero)

    def test_an_addition_at_another_time_is_a_new_entry(self):
        self.annotate(additions=self.at_zero)

        self.assertEqual(
            self.annotate(additions=self.at_two), self.at_zero + self.at_two
        )

    def test_an_addition_at_the_same_time_joins_the_objects(self):
        merged = [
            {
                "time": "0",
                "drawing": {
                    "objects": [
                        self.at_zero[0]["drawing"]["objects"][0],
                        self.also_at_zero[0]["drawing"]["objects"][0],
                    ]
                },
            }
        ]
        self.annotate(additions=self.at_zero)

        self.assertEqual(self.annotate(additions=self.also_at_zero), merged)
        # Replaying the same addition never doubles nor overwrites.
        self.assertEqual(self.annotate(additions=self.also_at_zero), merged)

    def test_a_deletion_names_a_time_and_the_objects_to_drop(self):
        self.annotate(additions=self.at_zero)

        # Neither an unannotated time nor an unknown object drops anything.
        self.assertEqual(
            self.annotate(deletions=[{"time": "2", "objects": ["obj1"]}]),
            self.at_zero,
        )
        self.assertEqual(
            self.annotate(deletions=[{"time": "0", "objects": ["obj4"]}]),
            self.at_zero,
        )
        # A time left without a single object goes away with them.
        self.assertEqual(
            self.annotate(deletions=[{"time": "0", "objects": ["obj1"]}]), []
        )

    def test_an_update_replaces_the_object_it_names(self):
        modified = [self.annotation("0", "obj1", path=["Q", 2, 14])]
        self.annotate(additions=self.at_zero + self.at_two)

        self.assertEqual(
            self.annotate(updates=modified), modified + self.at_two
        )

    def test_an_update_needs_the_lock(self):
        """
        When the Redis lock cannot be acquired (Redis down, or the wait
        timed out), the update is refused rather than raced through the
        read-modify-write without serialization.
        """
        self.annotate(additions=self.at_zero)

        @contextmanager
        def unavailable_lock(*args, **kwargs):
            yield False

        with patch(
            "zou.app.services.preview_annotations_service.with_preview_file_lock",
            side_effect=unavailable_lock,
        ):
            self.assertRaises(
                AnnotationLockTimeoutException,
                preview_annotations_service.update_preview_file_annotations,
                self.user_id,
                self.project_id,
                self.preview_file_id,
                additions=self.at_two,
            )

        self.assertEqual(
            files_service.get_preview_file(self.preview_file_id)[
                "annotations"
            ],
            self.at_zero,
        )

    def test_normalize_preview_file_annotation_times(self):
        preview_file = files_service.get_preview_file_raw(self.preview_file_id)
        preview_file.update(
            {
                "annotations": [
                    {"time": 0.6, "drawing": {"objects": [{"id": "new-1"}]}},
                    {"time": 0.616, "drawing": {"objects": [{"id": "old-1"}]}},
                ]
            }
        )

        self.assertTrue(
            preview_annotations_service.normalize_preview_file_annotation_times(
                preview_file
            )
        )

        persisted = files_service.get_preview_file(self.preview_file_id)
        self.assertEqual(len(persisted["annotations"]), 1)
        self.assertEqual(
            [
                drawing_object["id"]
                for drawing_object in persisted["annotations"][0]["drawing"][
                    "objects"
                ]
            ],
            ["new-1", "old-1"],
        )
        # A second run has nothing left to snap.
        self.assertFalse(
            preview_annotations_service.normalize_preview_file_annotation_times(
                preview_file
            )
        )
