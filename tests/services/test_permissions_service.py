# -*- coding: UTF-8 -*-
from contextlib import contextmanager

from flask import g
from flask_jwt_extended import verify_jwt_in_request

from tests.base import ApiDBTestCase

from zou.app import app
from zou.app.services import (
    comments_service,
    permissions_service,
    persons_service,
    projects_service,
    tasks_service,
)

from zou.app.utils import permissions

UNKNOWN = "00000000-0000-0000-0000-000000000000"


class PermissionsTestCase(ApiDBTestCase):
    """
    Base for the access checks. Every one of them reads the role off the
    request, so each case runs inside a request context with a verified
    token, exactly as a route does. Monkey-patching get_current_user would
    let the has_*_permissions calls keep reading the admin the test case
    logs in as.
    """

    def setUp(self):
        super().setUp()

        self.generate_base_context()
        self.project_id = str(self.project.id)

    def a_user(self, role):
        """
        The fixture user of given role, created on demand.
        """
        return {
            "admin": lambda: self.user,
            "manager": self.generate_fixture_user_manager,
            "artist": self.generate_fixture_user_cg_artist,
            "client": self.generate_fixture_user_client,
            "vendor": self.generate_fixture_user_vendor,
            "supervisor": self.generate_fixture_user_supervisor,
        }[role]()

    def join_team(self, user, role=None):
        """
        Add given user to the production, optionally with a role of their
        own on it. Kept out of as_role on purpose: it writes to the
        database and outlives the request context it would be called from.
        """
        projects_service.add_team_member(
            self.project_id, user["id"], role=role
        )
        return user

    @contextmanager
    def as_role(self, role):
        """
        Run the body as the fixture user of given role, inside a request
        carrying their token.

        flask.g lives on the application context, which the test case
        pushed once and test_request_context reuses: the project role
        resolved for an earlier caller has to go, the way it does between
        two real requests. Pushing a fresh application context instead
        would hand out a new database session and detach everything the
        fixtures hold.
        """
        user = self.a_user(role)
        self.log_in(user["email"])
        with app.test_request_context(headers=self.auth_headers):
            g.pop("project_role", None)
            verify_jwt_in_request()
            yield user

    def denied(self):
        return self.assertRaises(permissions.PermissionDenied)


class ProjectAccessTestCase(PermissionsTestCase):
    """
    Belonging to a production, and the per-project role that belonging
    resolves. Everything else in this service is built on these two.
    """

    def test_get_project_role_falls_back_to_the_global_role(self):
        artist = self.a_user("artist")
        projects_service.add_team_member(self.project_id, artist["id"])

        self.assertEqual(
            permissions_service.get_project_role(
                artist["id"], self.project_id
            ),
            "user",
        )

    def test_get_project_role_prefers_the_role_set_on_the_team_link(self):
        artist = self.a_user("artist")
        projects_service.add_team_member(
            self.project_id, artist["id"], role="supervisor"
        )

        self.assertEqual(
            permissions_service.get_project_role(
                artist["id"], self.project_id
            ),
            "supervisor",
        )

    def test_get_project_role_of_someone_outside_the_team(self):
        artist = self.a_user("artist")

        self.assertEqual(
            permissions_service.get_project_role(
                artist["id"], self.project_id
            ),
            "user",
        )

    def test_check_belong_to_project(self):
        with self.as_role("artist"):
            self.assertFalse(
                permissions_service.check_belong_to_project(self.project_id)
            )

        self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            self.assertTrue(
                permissions_service.check_belong_to_project(self.project_id)
            )

    def test_check_belong_to_project_without_a_project(self):
        self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            self.assertFalse(permissions_service.check_belong_to_project(None))

    def test_belonging_resolves_the_role_the_next_checks_read(self):
        """
        The documented trap: a role set per project only applies once an
        access check has resolved it into the request. An artist promoted
        to manager on this production is a manager, and only afterwards.
        """
        self.join_team(self.a_user("artist"), role="manager")

        with self.as_role("artist"):
            self.assertFalse(permissions.has_manager_permissions())

            permissions_service.check_belong_to_project(self.project_id)

            self.assertTrue(permissions.has_manager_permissions())

    def test_a_failed_check_clears_the_resolved_role(self):
        """
        A request touching two productions must not carry the role of the
        first into the second.
        """
        self.join_team(self.a_user("artist"), role="manager")
        # generate_fixture_project repoints self.project_id on the way.
        here = self.project_id
        elsewhere = str(self.generate_fixture_project("Another").id)

        with self.as_role("artist"):
            permissions_service.check_belong_to_project(here)
            self.assertTrue(permissions.has_manager_permissions())

            permissions_service.check_belong_to_project(elsewhere)

            self.assertFalse(permissions.has_manager_permissions())

    def test_resolve_project_role_only_resolves(self):
        # Same side effect, no access guarantee: it is for call sites that
        # enforce access later.
        self.join_team(self.a_user("artist"), role="supervisor")

        with self.as_role("artist"):
            self.assertTrue(
                permissions_service.resolve_project_role(self.project_id)
            )
            self.assertTrue(permissions.has_supervisor_permissions())

    def test_an_admin_keeps_the_global_role(self):
        # Admin is global only: a project slot never grants nor removes it.
        self.join_team(self.user, role="user")

        with self.as_role("admin"):
            permissions_service.check_belong_to_project(self.project_id)

            self.assertTrue(permissions.has_admin_permissions())

    def test_check_project_access(self):
        with self.as_role("artist"):
            self.assertFalse(
                permissions_service.has_project_access(self.project_id)
            )
            with self.denied():
                permissions_service.check_project_access(self.project_id)

        self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            self.assertTrue(
                permissions_service.check_project_access(self.project_id)
            )

    def test_an_admin_reaches_a_production_they_are_not_in(self):
        with self.as_role("admin"):
            self.assertTrue(
                permissions_service.check_project_access(self.project_id)
            )

    def test_a_manager_outside_the_team_is_not_a_manager_of_it(self):
        with self.as_role("manager"):
            self.assertFalse(
                permissions_service.has_manager_project_access(self.project_id)
            )
            with self.denied():
                permissions_service.check_manager_project_access(
                    self.project_id
                )

    def test_an_artist_of_the_team_is_not_a_manager_of_it(self):
        self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_manager_project_access(
                    self.project_id
                )

    def test_check_manager_project_access(self):
        self.join_team(self.a_user("manager"))

        with self.as_role("manager"):
            self.assertTrue(
                permissions_service.check_manager_project_access(
                    self.project_id
                )
            )

        with self.as_role("admin"):
            self.assertTrue(
                permissions_service.check_manager_project_access(
                    self.project_id
                )
            )

    def test_check_supervisor_project_access(self):
        self.join_team(self.a_user("supervisor"))

        with self.as_role("supervisor"):
            self.assertTrue(
                permissions_service.check_supervisor_project_access(
                    self.project_id
                )
            )

    def test_a_supervisor_outside_the_team_is_refused(self):
        with self.as_role("supervisor"):
            with self.denied():
                permissions_service.check_supervisor_project_access(
                    self.project_id
                )

    def test_an_artist_of_the_team_is_not_a_supervisor_of_it(self):
        self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_supervisor_project_access(
                    self.project_id
                )

    def test_block_access_to_vendor(self):
        self.join_team(self.a_user("vendor"))
        self.join_team(self.a_user("artist"))

        with self.as_role("vendor"):
            with self.denied():
                permissions_service.block_access_to_vendor()

        with self.as_role("artist"):
            self.assertTrue(permissions_service.block_access_to_vendor())


class PersonAccessTestCase(PermissionsTestCase):
    """
    The checks that name a person rather than a production.
    """

    def test_check_person_access(self):
        # Admin or self, and nothing else: not a manager, not a teammate.
        with self.as_role("admin"):
            self.assertTrue(
                permissions_service.check_person_access(
                    self.a_user("artist")["id"]
                )
            )

        self.join_team(self.a_user("manager"))

        with self.as_role("manager") as manager:
            self.assertTrue(
                permissions_service.check_person_access(manager["id"])
            )
            with self.denied():
                permissions_service.check_person_access(
                    self.a_user("artist")["id"]
                )

    def test_check_day_off_access(self):
        with self.as_role("artist") as artist:
            day_off = {"person_id": artist["id"]}
            self.assertTrue(permissions_service.check_day_off_access(day_off))

            with self.denied():
                permissions_service.check_day_off_access(
                    {"person_id": self.user["id"]}
                )

        with self.as_role("admin"):
            self.assertTrue(
                permissions_service.check_day_off_access(
                    {"person_id": self.a_user("artist")["id"]}
                )
            )

    def test_check_person_is_not_bot(self):
        self.generate_fixture_person()
        person_id = str(self.person.id)
        self.assertTrue(permissions_service.check_person_is_not_bot(person_id))

        self.person.update({"is_bot": True})
        persons_service.clear_person_cache()

        with self.denied():
            permissions_service.check_person_is_not_bot(person_id)

    def test_a_bot_is_allowed_on_a_production_that_wants_one(self):
        self.generate_fixture_person()
        person_id = str(self.person.id)
        self.person.update({"is_bot": True})
        persons_service.clear_person_cache()

        with self.denied():
            permissions_service.check_person_is_not_bot(
                person_id, self.project_id
            )

        self.project.update({"is_bot_collaboration_enabled": True})

        self.assertTrue(
            permissions_service.check_person_is_not_bot(
                person_id, self.project_id
            )
        )


class TaskAccessTestCase(PermissionsTestCase):
    """
    Reaching a task, the entity behind it and the statuses it may be moved
    to.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        # A second asset carrying its own task, so that a check naming one
        # of them has the other to reject. Both generators repoint the
        # attribute they name, hence the locals.
        task, asset = self.task, self.asset
        elsewhere = self.generate_fixture_asset("Rock")
        other_task = self.generate_fixture_task(
            "Second", entity_id=elsewhere.id
        )
        self.task_id = str(task.id)
        self.asset_id = str(asset.id)
        self.other_task_id = str(other_task.id)
        self.other_asset_id = str(elsewhere.id)

    def test_check_working_on_task(self):
        artist = self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_working_on_task(self.task_id)

        tasks_service.assign_task(self.task_id, artist["id"])

        with self.as_role("artist"):
            self.assertTrue(
                permissions_service.check_working_on_task(self.task_id)
            )
            # Assigned to one task is not assigned to every task.
            with self.denied():
                permissions_service.check_working_on_task(self.other_task_id)

    def test_check_working_on_entity(self):
        artist = self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_working_on_entity(self.asset_id)

        tasks_service.assign_task(self.task_id, artist["id"])

        with self.as_role("artist"):
            self.assertTrue(
                permissions_service.check_working_on_entity(self.asset_id)
            )
            with self.denied():
                permissions_service.check_working_on_entity(
                    self.other_asset_id
                )

    def test_check_entity_access_lets_everyone_but_a_vendor_through(self):
        """
        Only a vendor filter: it says nothing about the production, and
        never replaces check_project_access.
        """
        for role in ["artist", "client", "supervisor", "manager"]:
            with self.subTest(role=role):
                with self.as_role(role):
                    self.assertTrue(
                        permissions_service.check_entity_access(self.asset_id)
                    )

    def test_check_entity_access_holds_a_vendor_to_their_own_tasks(self):
        vendor = self.join_team(self.a_user("vendor"))

        with self.as_role("vendor"):
            with self.denied():
                permissions_service.check_entity_access(self.asset_id)

        tasks_service.assign_task(self.task_id, vendor["id"])

        with self.as_role("vendor"):
            self.assertTrue(
                permissions_service.check_entity_access(self.asset_id)
            )
            # The task they hold is on one entity, not on the next one.
            with self.denied():
                permissions_service.check_entity_access(self.other_asset_id)

    def test_a_vendor_reaches_only_the_tasks_they_hold(self):
        # check_task_access is the pair of checks together: the production
        # first, then the entity.
        vendor = self.join_team(self.a_user("vendor"))
        tasks_service.assign_task(self.task_id, vendor["id"])

        with self.as_role("vendor"):
            self.assertTrue(
                permissions_service.check_task_access(self.task_id)
            )
            with self.denied():
                permissions_service.check_task_access(self.other_task_id)

    def test_check_task_access(self):
        self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            self.assertTrue(
                permissions_service.check_task_access(self.task_id)
            )

        with self.as_role("manager"):
            # In no team, so the project check refuses before the entity
            # check is ever reached.
            with self.denied():
                permissions_service.check_task_access(self.task_id)

    def a_closed_status(self):
        """
        A status open to neither artists nor clients.
        """
        status = self.generate_fixture_task_status_wip()
        status.update({"is_artist_allowed": False, "is_client_allowed": False})
        tasks_service.clear_task_status_cache(str(status.id))
        return str(status.id)

    def test_a_client_may_not_use_a_status_closed_to_clients(self):
        closed = self.a_closed_status()
        self.join_team(self.a_user("client"))

        with self.as_role("client"):
            self.assertTrue(
                permissions_service.check_task_status_access(
                    str(self.task_status.id)
                )
            )
            with self.denied():
                permissions_service.check_task_status_access(closed)

    def test_an_artist_may_not_use_a_status_closed_to_artists(self):
        """
        has_artist_permissions answers on the resolved project role alone,
        so this check only bites once the project has been resolved. Every
        real call site resolves it first.
        """
        closed = self.a_closed_status()
        self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            # Nothing resolved yet: the artist branch does not apply.
            self.assertTrue(
                permissions_service.check_task_status_access(closed)
            )

            permissions_service.check_project_access(self.project_id)

            with self.denied():
                permissions_service.check_task_status_access(closed)
            self.assertTrue(
                permissions_service.check_task_status_access(
                    str(self.task_status.id)
                )
            )

    def test_a_manager_may_use_a_status_closed_to_artists(self):
        closed = self.generate_fixture_task_status_wip()
        closed.update({"is_artist_allowed": False, "is_client_allowed": False})
        tasks_service.clear_task_status_cache(str(closed.id))
        self.join_team(self.a_user("manager"))

        with self.as_role("manager"):
            self.assertTrue(
                permissions_service.check_task_status_access(str(closed.id))
            )

    def test_check_time_spent_access(self):
        artist = self.join_team(self.a_user("artist"))
        tasks_service.assign_task(self.task_id, artist["id"])

        with self.as_role("artist"):
            self.assertTrue(
                permissions_service.check_time_spent_access(
                    self.task_id, artist["id"]
                )
            )

    def test_time_spent_of_someone_else_is_refused(self):
        artist = self.join_team(self.a_user("artist"))
        other = self.join_team(self.a_user("supervisor"))
        tasks_service.assign_task(self.task_id, artist["id"])
        tasks_service.assign_task(self.task_id, other["id"])

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_time_spent_access(
                    self.task_id, other["id"]
                )

    def test_time_spent_of_someone_not_assigned_is_refused(self):
        # Even an admin cannot log time on a task for someone who is not on
        # it.
        artist = self.join_team(self.a_user("artist"))

        with self.as_role("admin"):
            with self.denied():
                permissions_service.check_time_spent_access(
                    self.task_id, artist["id"]
                )

    def test_a_manager_of_the_team_logs_time_for_an_assignee(self):
        artist = self.join_team(self.a_user("artist"))
        self.join_team(self.a_user("manager"))
        tasks_service.assign_task(self.task_id, artist["id"])

        with self.as_role("manager"):
            self.assertTrue(
                permissions_service.check_time_spent_access(
                    self.task_id, artist["id"]
                )
            )


class TaskActionAccessTestCase(PermissionsTestCase):
    """
    Who may act on a task: an admin, a manager or client of the team, an
    assignee, a supervisor of the right department, and the creator of the
    entity the task hangs on.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.task_id = str(self.task.id)

    def test_an_admin_acts_on_any_task(self):
        with self.as_role("admin"):
            self.assertTrue(
                permissions_service.check_task_action_access(self.task_id)
            )

    def test_a_manager_of_the_team_acts_on_its_tasks(self):
        self.join_team(self.a_user("manager"))

        with self.as_role("manager"):
            self.assertTrue(
                permissions_service.check_task_action_access(self.task_id)
            )

    def test_an_assignee_acts_on_their_task(self):
        artist = self.join_team(self.a_user("artist"))
        tasks_service.assign_task(self.task_id, artist["id"])

        with self.as_role("artist"):
            self.assertTrue(
                permissions_service.check_task_action_access(self.task_id)
            )

    def test_the_creator_of_the_entity_acts_on_its_tasks(self):
        # An artist's own concept stays theirs to work on.
        artist = self.join_team(self.a_user("artist"))
        self.asset.update({"created_by": artist["id"]})

        with self.as_role("artist"):
            self.assertTrue(
                permissions_service.check_task_action_access(self.task_id)
            )

    def test_someone_else_s_entity_is_refused(self):
        self.join_team(self.a_user("artist"))
        self.asset.update({"created_by": self.user["id"]})

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_task_action_access(self.task_id)

    def test_an_entity_with_no_creator_is_refused(self):
        self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_task_action_access(self.task_id)

    def test_the_creator_still_has_to_belong_to_the_team(self):
        artist = self.a_user("artist")
        self.asset.update({"created_by": artist["id"]})

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_task_action_access(self.task_id)


class DepartmentAccessTestCase(PermissionsTestCase):
    """
    What a supervisor may touch. A supervisor with no department at all is
    a supervisor of everything; one with departments is held to them.

    check_all_departments_access and check_metadata_department_access are
    driven through their routes in tests/services/test_project_roles.py.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.task_id = str(self.task.id)
        self.task_dict = self.task.serialize()
        # The task type of the fixture task belongs to Modeling.
        self.own_department = str(self.department.id)
        self.other_department = str(self.department_animation.id)

    def a_supervisor(self, department=None):
        supervisor = self.join_team(self.a_user("supervisor"))
        if department is not None:
            persons_service.add_to_department(department, supervisor["id"])
        return supervisor

    def test_a_supervisor_of_no_department_supervises_everything(self):
        self.a_supervisor()

        with self.as_role("supervisor"):
            self.assertTrue(
                permissions_service.check_supervisor_task_access(
                    self.task_dict, {"priority": 2}
                )
            )

    def test_a_supervisor_is_held_to_their_departments(self):
        self.a_supervisor(department=self.other_department)

        with self.as_role("supervisor"):
            with self.denied():
                permissions_service.check_supervisor_task_access(
                    self.task_dict, {"priority": 2}
                )

        persons_service.add_to_department(
            self.own_department, self.a_user("supervisor")["id"]
        )

        with self.as_role("supervisor"):
            self.assertTrue(
                permissions_service.check_supervisor_task_access(
                    self.task_dict, {"priority": 2}
                )
            )

    def test_a_supervisor_only_writes_the_columns_they_may(self):
        self.a_supervisor(department=self.own_department)

        with self.as_role("supervisor"):
            for column in [
                "priority",
                "start_date",
                "due_date",
                "estimation",
                "difficulty",
                "data",
            ]:
                with self.subTest(column=column):
                    self.assertTrue(
                        permissions_service.check_supervisor_task_access(
                            self.task_dict, {column: 1}
                        )
                    )
            with self.denied():
                permissions_service.check_supervisor_task_access(
                    self.task_dict, {"task_status_id": UNKNOWN}
                )

    def test_a_manager_of_the_team_writes_any_column(self):
        self.join_team(self.a_user("manager"))

        with self.as_role("manager"):
            self.assertTrue(
                permissions_service.check_supervisor_task_access(
                    self.task_dict, {"task_status_id": UNKNOWN}
                )
            )

    def test_check_supervisor_project_task_type_access(self):
        self.a_supervisor(department=self.own_department)
        own_type = str(self.task_type.id)
        other_type = str(self.task_type_animation.id)

        with self.as_role("supervisor"):
            self.assertTrue(
                permissions_service.check_supervisor_project_task_type_access(
                    self.project_id, own_type
                )
            )
            with self.denied():
                permissions_service.check_supervisor_project_task_type_access(
                    self.project_id, other_type
                )

    def test_a_task_type_of_a_production_one_does_not_belong_to(self):
        self.a_user("supervisor")

        with self.as_role("supervisor"):
            with self.denied():
                permissions_service.check_supervisor_project_task_type_access(
                    self.project_id, str(self.task_type.id)
                )

    def test_an_artist_assigns_themselves_within_their_department(self):
        artist = self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_task_department_access(
                    self.task_id, artist["id"]
                )

        persons_service.add_to_department(self.own_department, artist["id"])

        with self.as_role("artist"):
            self.assertTrue(
                permissions_service.check_task_department_access(
                    self.task_id, artist["id"]
                )
            )

    def test_an_artist_does_not_assign_somebody_else(self):
        artist = self.join_team(self.a_user("artist"))
        persons_service.add_to_department(self.own_department, artist["id"])
        other = self.join_team(self.a_user("supervisor"))

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_task_department_access(
                    self.task_id, other["id"]
                )

    def test_a_supervisor_assigns_within_their_department(self):
        supervisor = self.a_supervisor(department=self.own_department)
        artist = self.join_team(self.a_user("artist"))

        with self.as_role("supervisor"):
            # The person being assigned has to share the department too.
            with self.denied():
                permissions_service.check_task_department_access(
                    self.task_id, artist["id"]
                )

        persons_service.add_to_department(self.own_department, artist["id"])

        with self.as_role("supervisor"):
            self.assertTrue(
                permissions_service.check_task_department_access(
                    self.task_id, artist["id"]
                )
            )

    def test_unassigning_takes_the_assignees_into_account(self):
        """
        The unassign variant differs from the assign one: an artist may
        take themselves off a task they are on, whatever their department.
        """
        artist = self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_task_department_access_for_unassign(
                    self.task_id, artist["id"]
                )

        tasks_service.assign_task(self.task_id, artist["id"])

        with self.as_role("artist"):
            self.assertTrue(
                permissions_service.check_task_department_access_for_unassign(
                    self.task_id, artist["id"]
                )
            )

    def test_a_supervisor_unassigns_within_their_department(self):
        self.a_supervisor(department=self.other_department)
        artist = self.join_team(self.a_user("artist"))

        with self.as_role("supervisor"):
            with self.denied():
                permissions_service.check_task_department_access_for_unassign(
                    self.task_id, artist["id"]
                )

        persons_service.add_to_department(
            self.own_department, self.a_user("supervisor")["id"]
        )

        with self.as_role("supervisor"):
            self.assertTrue(
                permissions_service.check_task_department_access_for_unassign(
                    self.task_id, artist["id"]
                )
            )


class PlaylistAccessTestCase(PermissionsTestCase):
    """
    Who sees and who edits a playlist. Both checks take the playlist as a
    dict rather than an id, so they are driven directly here.
    """

    def a_playlist(self, for_client=False, created_by=None):
        return {
            "project_id": self.project_id,
            "for_client": for_client,
            "created_by": created_by,
        }

    def test_a_manager_of_the_team_sees_every_playlist(self):
        self.join_team(self.a_user("manager"))

        with self.as_role("manager"):
            self.assertTrue(
                permissions_service.check_playlist_access(self.a_playlist())
            )

    def test_an_artist_of_the_team_sees_none(self):
        self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_playlist_access(self.a_playlist())

    def test_a_client_sees_only_the_playlists_meant_for_them(self):
        self.join_team(self.a_user("client"))

        with self.as_role("client"):
            with self.denied():
                permissions_service.check_playlist_access(self.a_playlist())
            self.assertTrue(
                permissions_service.check_playlist_access(
                    self.a_playlist(for_client=True)
                )
            )

    def test_a_supervisor_sees_them_when_the_caller_opts_in(self):
        self.join_team(self.a_user("supervisor"))

        with self.as_role("supervisor"):
            with self.denied():
                permissions_service.check_playlist_access(self.a_playlist())
            self.assertTrue(
                permissions_service.check_playlist_access(
                    self.a_playlist(), supervisor_access=True
                )
            )

    def test_a_playlist_of_another_production_is_out_of_reach(self):
        self.a_user("manager")

        with self.as_role("manager"):
            with self.denied():
                permissions_service.check_playlist_access(self.a_playlist())

    def test_a_manager_of_the_team_updates_any_playlist(self):
        self.join_team(self.a_user("manager"))

        with self.as_role("manager"):
            self.assertTrue(
                permissions_service.check_playlist_update_access(
                    self.a_playlist(created_by=self.user["id"])
                )
            )

    def test_a_supervisor_updates_the_playlists_they_created(self):
        supervisor = self.join_team(self.a_user("supervisor"))

        with self.as_role("supervisor"):
            self.assertTrue(
                permissions_service.check_playlist_update_access(
                    self.a_playlist(created_by=supervisor["id"])
                )
            )
            # No creator recorded: an old playlist stays editable.
            self.assertTrue(
                permissions_service.check_playlist_update_access(
                    self.a_playlist()
                )
            )
            with self.denied():
                permissions_service.check_playlist_update_access(
                    self.a_playlist(created_by=self.user["id"])
                )

    def test_a_supervisor_of_another_production_updates_nothing(self):
        """
        The supervisor branch checks the team on its own: a failed manager
        check clears the resolved role, and the global supervisor role
        would otherwise carry them into a production they are not in.
        """
        supervisor = self.a_user("supervisor")

        with self.as_role("supervisor"):
            with self.denied():
                permissions_service.check_playlist_update_access(
                    self.a_playlist(created_by=supervisor["id"])
                )


class CommentAccessTestCase(PermissionsTestCase):
    """
    Who may read a comment. The interesting side is the client one: a
    client's comment is internal to the clients, and a production can be
    set to isolate its clients from each other.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.task_id = str(self.task.id)

    def a_comment(self, author, for_client=False):
        return comments_service.new_comment(
            self.task_id,
            str(self.task_status.id),
            author["id"],
            "comment",
            for_client=for_client,
        )["id"]

    def test_an_admin_reads_any_comment(self):
        comment_id = self.a_comment(self.join_team(self.a_user("client")))

        with self.as_role("admin"):
            self.assertTrue(
                permissions_service.check_comment_access(comment_id)
            )

    def test_a_manager_of_the_team_reads_any_comment(self):
        comment_id = self.a_comment(self.join_team(self.a_user("client")))
        self.join_team(self.a_user("manager"))

        with self.as_role("manager"):
            self.assertTrue(
                permissions_service.check_comment_access(comment_id)
            )

    def test_an_artist_reads_a_comment_of_the_studio(self):
        artist = self.join_team(self.a_user("artist"))
        comment_id = self.a_comment(artist)

        with self.as_role("artist"):
            self.assertTrue(
                permissions_service.check_comment_access(comment_id)
            )

    def test_an_artist_does_not_read_a_client_comment(self):
        comment_id = self.a_comment(self.join_team(self.a_user("client")))
        self.join_team(self.a_user("artist"))

        with self.as_role("artist"):
            with self.denied():
                permissions_service.check_comment_access(comment_id)

    def test_a_client_reads_their_own_comment(self):
        client = self.join_team(self.a_user("client"))
        comment_id = self.a_comment(client)

        with self.as_role("client"):
            self.assertTrue(
                permissions_service.check_comment_access(comment_id)
            )

    def test_a_client_reads_a_comment_meant_for_them(self):
        self.join_team(self.a_user("client"))
        comment_id = self.a_comment(
            self.join_team(self.a_user("manager")), for_client=True
        )

        with self.as_role("client"):
            self.assertTrue(
                permissions_service.check_comment_access(comment_id)
            )

    def test_a_client_does_not_read_an_internal_comment(self):
        self.join_team(self.a_user("client"))
        comment_id = self.a_comment(self.join_team(self.a_user("manager")))

        with self.as_role("client"):
            with self.denied():
                permissions_service.check_comment_access(comment_id)

    def test_isolated_clients_do_not_read_each_other(self):
        """
        A production can hold its clients apart: each one then sees only
        their own comments and the ones written for the clients.
        """
        author = self.join_team(self.a_user("artist"), role="client")
        comment_id = self.a_comment(author)
        self.join_team(self.a_user("client"))

        with self.as_role("client"):
            self.assertTrue(
                permissions_service.check_comment_access(comment_id)
            )

        projects_service.update_project(
            self.project_id, {"is_clients_isolated": True}
        )

        with self.as_role("client"):
            with self.denied():
                permissions_service.check_comment_access(comment_id)
