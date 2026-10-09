from tests.base import ApiDBTestCase

from zou.app.services import projects_service


class DemotedRoleTestCase(ApiDBTestCase):
    """
    The shape every check below shares: someone globally privileged holds a
    weaker role on one production, and is refused there what that weaker role
    forbids. It is the ordering trap of permissions._effective_role, which
    only sees the project role once the project has been resolved, so each
    subclass drives the one route whose ordering was wrong.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_user_manager()

    def demote_manager(self, role):
        """
        Give the manager fixture a weaker role on the production, log them
        in, and return their id.
        """
        manager_id = str(self.user_manager["id"])
        projects_service.add_team_member(
            str(self.project.id), manager_id, role=role
        )
        self.log_in_manager()
        return manager_id
