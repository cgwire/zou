# -*- coding: UTF-8 -*-
from flask_jwt_extended import verify_jwt_in_request

from tests.base import ApiDBTestCase

from zou.app import app
from zou.app.models.person import Person
from zou.app.services import (
    permissions_service,
    persons_service,
    projects_service,
    tasks_service,
)

from zou.app.utils import permissions


class PermissionsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_to_review()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        self.generate_fixture_working_file()

        self.task_id = self.task.id
        self.project_id = self.project.id
        self.open_status_id = self.task_status.id
        self.wip_status_id = self.task_status_wip.id
        self.to_review_status_id = self.task_status_to_review.id

        self.old_get_current_user = persons_service.get_current_user
        persons_service.get_current_user = self.get_current_user
        self.old_get_current_user_raw = persons_service.get_current_user_raw
        persons_service.get_current_user_raw = self.get_current_user_raw

    def tearDown(self):
        super().tearDown()
        persons_service.get_current_user = self.old_get_current_user
        persons_service.get_current_user_raw = self.old_get_current_user_raw

    def get_current_user(self):
        return self.user

    def get_current_user_raw(self):
        return Person.get(self.user["id"])

    def test_check_project_access(self):
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        with self.assertRaises(permissions.PermissionDenied):
            permissions_service.check_project_access(str(self.project_id))

        projects_service.add_team_member(
            str(self.project.id), str(self.get_current_user_raw().id)
        )
        projects_service.get_project(self.project_id, relations=True)
        self.assertTrue(
            permissions_service.check_project_access(str(self.project_id))
        )

    def test_check_entity_access(self):
        self.asset_id = str(self.asset.id)
        self.generate_fixture_user_vendor()
        self.log_in_vendor()
        person_id = str(self.get_current_user_raw().id)
        projects_service.add_team_member(self.project_id, person_id)
        # The permission helpers read the JWT identity: run the checks in a
        # verified request context, as production does.
        with app.test_request_context(headers=self.auth_headers):
            verify_jwt_in_request()
            with self.assertRaises(permissions.PermissionDenied):
                permissions_service.check_entity_access(str(self.asset_id))
            tasks_service.assign_task(self.task_id, person_id)
            self.assertTrue(
                permissions_service.check_entity_access(str(self.asset_id))
            )

    def _log_in_cg_artist_as_current_user(self, team_member=True):
        """
        Log in an unassigned CG artist and make get_current_user return it.
        Returns the artist id. The artist is added to the project team unless
        team_member is False.
        """
        self.generate_fixture_user_cg_artist()
        artist_id = self.user_cg_artist["id"]
        if team_member:
            projects_service.add_team_member(self.project_id, artist_id)
        self.log_in_cg_artist()
        persons_service.get_current_user = (
            lambda relations=False: self.user_cg_artist
        )
        return artist_id

    def test_check_task_action_access_granted_for_entity_creator(self):
        artist_id = self._log_in_cg_artist_as_current_user()
        self.asset.update({"created_by": artist_id})
        self.assertTrue(
            permissions_service.check_task_action_access(str(self.task_id))
        )

    def test_check_task_action_access_denied_for_non_creator(self):
        self._log_in_cg_artist_as_current_user()
        # Created by someone else, not assigned -> no access.
        self.asset.update({"created_by": self.user["id"]})
        with self.assertRaises(permissions.PermissionDenied):
            permissions_service.check_task_action_access(str(self.task_id))

    def test_check_task_action_access_denied_without_creator(self):
        self._log_in_cg_artist_as_current_user()
        # Entity has no creator (created_by is None) -> no access.
        with self.assertRaises(permissions.PermissionDenied):
            permissions_service.check_task_action_access(str(self.task_id))

    def test_check_task_action_access_denied_for_creator_not_in_team(self):
        # The creator must still belong to the project team to act on a task.
        artist_id = self._log_in_cg_artist_as_current_user(team_member=False)
        self.asset.update({"created_by": artist_id})
        with self.assertRaises(permissions.PermissionDenied):
            permissions_service.check_task_action_access(str(self.task_id))
