from sqlalchemy.exc import IntegrityError

from tests.base import ApiDBTestCase

from zou.app import db
from zou.app.models.person import Person


class PersonPreviewTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()

    def test_preview_project_id_is_unique(self):
        Person.create(
            first_name="Preview",
            last_name="Project",
            email="preview-0@preview.kitsu.invalid",
            preview_project_id=self.project.id,
        )
        with self.assertRaises(IntegrityError):
            Person.create(
                first_name="Preview",
                last_name="Project",
                email="preview-1@preview.kitsu.invalid",
                preview_project_id=self.project.id,
            )
        db.session.rollback()
