from tests.base import ApiDBTestCase

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.metadata_descriptor import (
    DepartmentMetadataDescriptorLink,
    MetadataDescriptor,
)
from zou.app.models.milestone import Milestone
from zou.app.models.news import News
from zou.app.utils import fields


class CreateFromImportReturnsTestCase(ApiDBTestCase):
    """
    Cover the (instance, is_update) contract on the create_from_import
    classmethod. The Kitsu import routes in zou/app/blueprints/source/kitsu.py
    rely on this tuple shape — every model that may travel through them must
    follow the convention: False on create, True on update.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_asset()
        self.generate_fixture_task()

    def test_basemixin_default_returns_tuple(self):
        # Milestone has no override, so it exercises BaseMixin's default.
        self.generate_fixture_milestone()
        data = self.milestone.serialize()

        # Same ID → update path.
        instance, is_update = Milestone.create_from_import(data)
        self.assertEqual(str(instance.id), str(data["id"]))
        self.assertTrue(is_update)

        # New ID → create path.
        data["id"] = str(fields.gen_uuid())
        data["name"] = "Fresh milestone"
        instance, is_update = Milestone.create_from_import(data)
        self.assertEqual(str(instance.id), data["id"])
        self.assertFalse(is_update)

    def test_news_create_returns_false(self):
        # Regression: News used to return True on create / False on update,
        # the inverse of every other tuple-returning create_from_import.
        news = News.create(
            change=False,
            author_id=self.person.id,
            task_id=self.task.id,
        )
        data = news.serialize()

        instance, is_update = News.create_from_import(data)
        self.assertEqual(str(instance.id), str(data["id"]))
        self.assertTrue(is_update)

        data["id"] = str(fields.gen_uuid())
        instance, is_update = News.create_from_import(data)
        self.assertEqual(str(instance.id), data["id"])
        self.assertFalse(is_update)

    def test_attachment_file_returns_tuple(self):
        attachment = AttachmentFile.create(
            name="bug.png",
            size=42,
            extension="png",
            mimetype="image/png",
        )
        data = attachment.serialize()

        instance, is_update = AttachmentFile.create_from_import(data)
        self.assertEqual(str(instance.id), str(data["id"]))
        self.assertTrue(is_update)

        data["id"] = str(fields.gen_uuid())
        instance, is_update = AttachmentFile.create_from_import(data)
        self.assertEqual(str(instance.id), data["id"])
        self.assertFalse(is_update)

    def test_metadata_descriptor_sets_departments(self):
        self.generate_fixture_metadata_descriptor()
        data = self.meta_descriptor.serialize()
        data["departments"] = [str(self.department.id)]

        instance, is_update = MetadataDescriptor.create_from_import(data)
        self.assertTrue(is_update)
        links = DepartmentMetadataDescriptorLink.query.filter_by(
            metadata_descriptor_id=instance.id
        ).all()
        self.assertEqual(len(links), 1)
        self.assertEqual(str(links[0].department_id), str(self.department.id))

        # Re-import without a "departments" key: existing links stay untouched.
        # create_from_import already popped the key on the first call, so
        # asserting absence is enough.
        self.assertNotIn("departments", data)
        data["name"] = "Renamed"
        instance, is_update = MetadataDescriptor.create_from_import(data)
        self.assertTrue(is_update)
        self.assertEqual(instance.name, "Renamed")
        links = DepartmentMetadataDescriptorLink.query.filter_by(
            metadata_descriptor_id=instance.id
        ).all()
        self.assertEqual(len(links), 1)
