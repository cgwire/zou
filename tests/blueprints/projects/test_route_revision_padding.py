from tests.base import ApiDBTestCase


class ProjectRevisionPaddingTestCase(ApiDBTestCase):
    """
    Test the revision_padding project setting (display-only padding for
    revision numbers, default 0 = no padding).
    """

    def setUp(self):
        super(ProjectRevisionPaddingTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.project_id = str(self.project.id)

    def test_revision_padding_defaults_to_zero(self):
        project = self.get(f"data/projects/{self.project_id}")
        self.assertEqual(project["revision_padding"], 0)

    def test_revision_padding_is_updatable(self):
        self.put(f"data/projects/{self.project_id}", {"revision_padding": 3})
        project = self.get(f"data/projects/{self.project_id}")
        self.assertEqual(project["revision_padding"], 3)
