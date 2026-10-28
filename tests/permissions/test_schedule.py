from tests.permissions.cases import DemotedRoleTestCase
from zou.app.services import projects_service


class ProductionScheduleVersionRoleTestCase(DemotedRoleTestCase):
    """
    Coverage audit fix: crud/production_schedule_version.py
    check_read_permissions methods run check_project_access before the
    has_vendor/has_client deny, so a demoted client is caught by the deny
    instead of slipping through on a stale global role.
    """

    def setUp(self):
        super().setUp()
        self.version = self.post(
            "data/production-schedule-versions",
            {"name": "Version 1", "project_id": str(self.project.id)},
        )

    def test_demoted_client_cannot_read_production_schedule_version(self):
        self.demote_manager("client")
        self.get(
            f"data/production-schedule-versions/{self.version['id']}", 403
        )

    def test_global_vendor_gets_403_not_500_with_no_query_args(self):
        self.generate_fixture_user_vendor()
        self.log_in_vendor()
        self.get("data/production-schedule-versions", 403)


class PersonsTaskDatesRoleTestCase(DemotedRoleTestCase):
    """
    The persons task dates of a named production follow the role held on
    it: the supervisor check runs once the membership resolved that role.
    """

    def test_demoted_client_is_refused_the_task_dates(self):
        self.demote_manager("client")
        self.get(f"data/persons/task-dates?project_id={self.project.id}", 403)

    def test_supervisor_on_the_project_reads_the_task_dates(self):
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            str(self.project.id), self.user_cg_artist["id"], role="supervisor"
        )
        self.log_in_cg_artist()
        self.get(f"data/persons/task-dates?project_id={self.project.id}")
