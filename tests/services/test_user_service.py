# -*- coding: UTF-8 -*-
from tests.base import ApiDBTestCase

from zou.app.models.person import Person
from zou.app.services import (
    comments_service,
    persons_service,
    projects_service,
    tasks_service,
    user_service,
)


class UserServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_to_review()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.generate_fixture_user_client()

        self.task_id = self.task.id
        self.project_id = self.project.id
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

    def get_current_user_artist(self):
        return self.user_cg_artist

    def get_current_user_raw(self):
        return Person.get(self.user["id"])

    def test_related_projects(self):
        projects = user_service.related_projects()
        self.assertEqual(len(projects), 0)

        self.project.team.append(self.get_current_user_raw())

        self.project.save()
        projects = user_service.related_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["id"], str(self.project_id))

    def test_get_last_notifications(self):
        persons_service.get_current_user = self.get_current_user_artist
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        person_id = self.user_cg_artist["id"]
        projects_service.add_team_member(self.project_id, person_id)
        tasks_service.assign_task(self.task_id, person_id)
        notifications = user_service.get_last_notifications()
        self.assertEqual(len(notifications), 0)
        comments_service.create_comment(
            self.user["id"],
            self.task_id,
            self.to_review_status_id,
            "Lets go",
            [],
            {},
            None,
        )
        notifications = user_service.get_last_notifications()
        self.assertEqual(len(notifications), 1)

        comments_service.create_comment(
            self.user_client["id"],
            self.task_id,
            self.to_review_status_id,
            "Wrong picture",
            [],
            {},
            None,
        )
        notifications = user_service.get_last_notifications()
        self.assertEqual(len(notifications), 2)
        self.assertEqual(len(notifications[0]["comment_text"]), 0)
        self.assertGreater(len(notifications[1]["comment_text"]), 0)
