from types import SimpleNamespace
from unittest import TestCase, mock

from flask import g

from zou.app import app
from zou.app.utils import permissions


class GlobalRoleFallbackTestCase(TestCase):
    """
    Unit coverage of the permission helpers' global fallback, which reads
    the JWT identity directly since the Flask-Principal removal. Everything
    is mocked: no database fixture is needed, hence the plain TestCase.
    """

    def helpers_for(self, role):
        with app.test_request_context():
            with mock.patch.object(
                permissions,
                "get_current_user",
                return_value=SimpleNamespace(role=role),
            ):
                return {
                    "admin": permissions.has_admin_permissions(),
                    "manager": permissions.has_manager_permissions(),
                    "supervisor": permissions.has_supervisor_permissions(),
                    "at_least_supervisor": (
                        permissions.has_at_least_supervisor_permissions()
                    ),
                    "client": permissions.has_client_permissions(),
                    "vendor": permissions.has_vendor_permissions(),
                    "artist": permissions.has_artist_permissions(),
                }

    def test_admin_implies_manager(self):
        helpers = self.helpers_for("admin")
        self.assertTrue(helpers["admin"])
        self.assertTrue(helpers["manager"])
        self.assertTrue(helpers["at_least_supervisor"])
        self.assertFalse(helpers["supervisor"])

    def test_manager_is_not_admin(self):
        helpers = self.helpers_for("manager")
        self.assertFalse(helpers["admin"])
        self.assertTrue(helpers["manager"])
        self.assertTrue(helpers["at_least_supervisor"])

    def test_single_role_mappings(self):
        self.assertTrue(self.helpers_for("supervisor")["supervisor"])
        self.assertTrue(self.helpers_for("client")["client"])
        self.assertTrue(self.helpers_for("vendor")["vendor"])

    def test_artist_global_fallback_stays_false(self):
        # Flask-Principal never granted a "user" need: the historical
        # always-False global fallback is preserved on purpose.
        helpers = self.helpers_for("user")
        self.assertFalse(helpers["artist"])
        self.assertFalse(helpers["at_least_supervisor"])

    def test_choice_role_objects_are_unwrapped(self):
        # In production Person.role is a sqlalchemy_utils Choice object,
        # not a plain string: the .code unwrapping branch must be covered.
        with app.test_request_context():
            with mock.patch.object(
                permissions,
                "get_current_user",
                return_value=SimpleNamespace(
                    role=SimpleNamespace(code="admin")
                ),
            ):
                self.assertTrue(permissions.has_admin_permissions())
                self.assertTrue(permissions.has_manager_permissions())

    def test_admin_in_project_slot_falls_back_to_global_role(self):
        # Admin is global-only: an "admin" value in the project role slot
        # is invalid data and must not grant admin-tier rights.
        with app.test_request_context():
            g.project_role = "admin"
            with mock.patch.object(
                permissions,
                "get_current_user",
                return_value=SimpleNamespace(role="user"),
            ):
                self.assertFalse(permissions.has_admin_permissions())
                self.assertFalse(permissions.has_manager_permissions())
                self.assertFalse(
                    permissions.has_at_least_supervisor_permissions()
                )

    def test_person_permissions_follow_identity_type(self):
        for identity_type, expected in [
            ("person", True),
            ("person_api", True),
            ("bot", False),
        ]:
            with app.test_request_context():
                with mock.patch.object(
                    permissions,
                    "get_jwt",
                    return_value={"identity_type": identity_type},
                ):
                    self.assertEqual(
                        permissions.has_person_permissions(), expected
                    )

    def test_all_false_outside_app_context(self):
        # Plain TestCase: unlike ApiDBTestCase, no app context is pushed,
        # so this exercises the RuntimeError guards for real.
        self.assertFalse(permissions.has_admin_permissions())
        self.assertFalse(permissions.has_manager_permissions())
        self.assertFalse(permissions.has_person_permissions())
