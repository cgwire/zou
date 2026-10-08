from zou.app.services import tasks_service
from tests.permissions.cases import DemotedRoleTestCase


class AllShotsRoleTestCase(DemotedRoleTestCase):
    """
    Coverage audit fix: shots/resources.py AllShotsResource.get moves
    check_project_access above the vendor filter so a project-scoped
    vendor demotion is honored.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()

    def test_demoted_vendor_scoped_to_assigned_shots(self):
        manager_id = self.demote_manager("vendor")
        shots = self.get(f"data/shots?project_id={self.project.id}")
        self.assertEqual(shots, [])
        tasks_service.assign_task(str(self.shot_task.id), manager_id)
        shots = self.get(f"data/shots?project_id={self.project.id}")
        self.assertEqual(len(shots), 1)


class AllEditsRoleTestCase(DemotedRoleTestCase):
    """
    Coverage audit fix: edits/resources.py AllEditsResource.get moves
    check_project_access above the vendor filter so a project-scoped
    vendor demotion is honored.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_edit()
        self.generate_fixture_edit_task()

    def test_demoted_vendor_scoped_to_assigned_edits(self):
        manager_id = self.demote_manager("vendor")
        edits = self.get(f"data/edits?project_id={self.project.id}")
        self.assertEqual(edits, [])
        tasks_service.assign_task(str(self.edit_task.id), manager_id)
        edits = self.get(f"data/edits?project_id={self.project.id}")
        self.assertEqual(len(edits), 1)


class ProjectPersonQuotasRoleTestCase(DemotedRoleTestCase):
    """
    Coverage audit fix: shots/resources.py ProjectPersonQuotasResource.get
    resolves the project role before branching, so a demoted manager falls
    to the person-access branch instead of the project-wide one.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_person()

    def test_demoted_manager_cannot_view_other_person_quotas(self):
        self.demote_manager("user")
        self.get(
            f"data/projects/{self.project.id}/quotas/persons/"
            f"{self.person.id}",
            403,
        )
