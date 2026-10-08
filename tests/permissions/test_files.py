from tests.permissions.cases import DemotedRoleTestCase


class PreviewThumbnailRoleTestCase(DemotedRoleTestCase):
    """
    Coverage audit fix: previews/resources.py
    BasePreviewFileThumbnailResource.is_allowed resolves the project role
    before checking has_vendor_permissions, so a demoted vendor does not
    get the shared-preview shortcut.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_preview_file()
        self.asset.update(
            {
                "preview_file_id": str(self.preview_file.id),
                "is_shared": True,
            }
        )

    def test_demoted_vendor_must_be_assigned_for_shared_thumbnail(self):
        self.demote_manager("vendor")
        self.get(
            f"/pictures/thumbnails/preview-files/{self.preview_file.id}.png",
            403,
        )


class PreviewFileReadRoleTestCase(DemotedRoleTestCase):
    """
    Coverage audit fix: crud/preview_file.py
    PreviewFileResource.check_read_permissions resolves the project role
    before checking has_vendor_permissions, so a demoted vendor must be
    working on the task.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_preview_file()

    def test_demoted_vendor_not_working_on_task_cannot_read(self):
        self.demote_manager("vendor")
        self.get(f"data/preview-files/{self.preview_file.id}", 403)


class OutputFileUpdateRoleTestCase(DemotedRoleTestCase):
    """
    Coverage audit fix: crud/output_file.py
    OutputFileResource.check_update_permissions checks
    has_manager_project_access instead of the global
    has_manager_permissions, so a demoted manager must be working on the
    entity.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_asset()
        self.generate_fixture_output_type()
        self.generate_fixture_output_file()

    def test_demoted_manager_must_be_working_on_entity(self):
        self.demote_manager("user")
        self.put(
            f"data/output-files/{self.output_file.id}",
            {"comment": "Updated"},
            403,
        )
