# -*- coding: UTF-8 -*-
from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.task import Task
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

        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_task_status_to_review()
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
        self.assertEqual(projects, [])

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
        self.assertEqual(notifications, [])
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
        self.assertEqual(notifications[0]["comment_text"], "")
        self.assertGreater(len(notifications[1]["comment_text"]), 0)


class UserVisibleEntitiesTestCase(ApiDBTestCase):
    """
    What the four listings behind the user context answer: the assets,
    asset types, sequences and episodes of one production the caller has a
    task on. Each is scoped three ways, by the production, by the caller's
    assignments, and by the production being open.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset_types()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_assigner()

        self.old_get_current_user = persons_service.get_current_user
        self.old_get_current_user_raw = persons_service.get_current_user_raw
        persons_service.get_current_user = lambda **kwargs: self.user
        persons_service.get_current_user_raw = lambda: Person.get(
            self.user["id"]
        )
        self.addCleanup(self.restore_current_user)

        # Each production owns an asset of its own type plus one of the
        # shared Props type, so both asset listings have a row of the other
        # production to leave out.
        self.project = self.build_production(
            "Watched", self.asset_type_character
        )
        self.other = self.build_production(
            "Unwatched", self.asset_type_environment
        )

    def restore_current_user(self):
        persons_service.get_current_user = self.old_get_current_user
        persons_service.get_current_user_raw = self.old_get_current_user_raw

    def build_production(self, name, asset_type):
        """
        A production with one asset and one shot under a sequence and an
        episode, each carrying a task assigned to the caller.
        """
        project = Project.create(
            name=name, project_status_id=self.open_status.id
        )
        me = Person.get(self.user["id"])
        rows = {}
        for entity_name, entity_type_id, parent in [
            ("asset", asset_type.id, None),
            # Both productions also own a props asset, so the asset listing
            # has a row of the same type to leave out.
            ("props", self.asset_type.id, None),
            ("episode", self.episode_type.id, None),
            ("sequence", self.sequence_type.id, "episode"),
            ("shot", self.shot_type.id, "sequence"),
        ]:
            rows[entity_name] = Entity.create(
                name=f"{name} {entity_name}",
                project_id=project.id,
                entity_type_id=entity_type_id,
                parent_id=rows[parent].id if parent else None,
            )
        for entity_name in ["asset", "props", "shot"]:
            Task.create(
                name=f"{name} {entity_name} task",
                project_id=project.id,
                task_type_id=self.task_type.id,
                task_status_id=self.task_status.id,
                entity_id=rows[entity_name].id,
                assignees=[me],
                assigner_id=self.assigner.id,
            )
        project.team.append(me)
        project.save()
        self.__dict__.setdefault("rows", {})[name] = rows
        return project

    def test_the_listings_answer_for_one_production_only(self):
        project_id = str(self.project.id)
        watched = self.rows["Watched"]

        self.assertEqual(
            [
                asset["id"]
                for asset in user_service.get_assets_for_asset_type(
                    project_id, str(self.asset_type.id)
                )
            ],
            [str(watched["props"].id)],
        )
        self.assertEqual(
            sorted(
                asset_type["id"]
                for asset_type in user_service.get_asset_types_for_project(
                    project_id
                )
            ),
            sorted(
                [
                    str(self.asset_type.id),
                    str(self.asset_type_character.id),
                ]
            ),
        )
        self.assertEqual(
            [
                sequence["id"]
                for sequence in user_service.get_sequences_for_project(
                    project_id
                )
            ],
            [str(watched["sequence"].id)],
        )
        self.assertEqual(
            [
                episode["id"]
                for episode in user_service.get_project_episodes(project_id)
            ],
            [str(watched["episode"].id)],
        )
