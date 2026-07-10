from tests.base import ApiDBTestCase
from zou.app.models.project import Project, ProjectTaskTypeLink
from zou.app.models.task_type import TaskType

from zou.app.services import (
    comments_service,
    news_service,
    notifications_service,
    persons_service,
    projects_service,
    tasks_service,
)


class TaskRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(TaskRoutesTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_retake()
        self.generate_fixture_task_status_done()
        self.generate_fixture_task_status_wfa()
        self.todo_status = self.generate_fixture_task_status_todo()
        self.asset_id = str(self.asset.id)
        self.shot_id = str(self.shot.id)
        self.task_type_id = str(self.task_type.id)
        self.project_id = str(self.project.id)

        self.wip_status_id = self.task_status_wip.id
        self.retake_status_id = self.task_status_retake.id
        self.done_status_id = self.task_status_done.id
        self.wfa_status_id = self.task_status_wfa.id
        self.person_id = self.person.id

    def test_create_asset_tasks(self):
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()
        path = f"/actions/projects/{self.project.id}/task-types/{self.task_type_id}/assets/create-tasks"
        tasks = self.post(path, {})
        self.assertEqual(len(tasks), 2)

        tasks = self.get("/data/tasks")
        self.assertEqual(len(tasks), 2)
        task = tasks[0]
        self.assertEqual(task["name"], "main")
        self.assertEqual(task["task_type_id"], self.task_type_id)

    def test_create_asset_tasks_from_list(self):
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()
        path = f"/actions/projects/{self.project.id}/task-types/{self.task_type_id}/assets/create-tasks"
        tasks = self.post(path, [self.asset_id])
        self.assertEqual(len(tasks), 1)
        tasks = self.get("/data/tasks")
        self.assertEqual(len(tasks), 1)
        task = tasks[0]
        self.assertEqual(task["name"], "main")
        self.assertEqual(task["task_type_id"], self.task_type_id)
        self.assertEqual(task["entity_id"], self.asset_id)

    def test_create_shot_tasks(self):
        path = f"/actions/projects/{self.project.id}/task-types/{self.task_type_id}/shots/create-tasks"
        tasks = self.post(path, {})
        self.assertEqual(len(tasks), 1)

        tasks = self.get("/data/tasks")
        self.assertEqual(len(tasks), 1)
        task = tasks[0]
        self.assertEqual(task["name"], "main")
        self.assertEqual(task["task_type_id"], self.task_type_id)
        self.assertEqual(task["entity_id"], self.shot_id)

    def test_create_entity_tasks_for_shot(self):
        ProjectTaskTypeLink.create(
            project_id=self.project.id,
            task_type_id=self.task_type_animation.id,
        )
        path = f"/data/entities/{self.shot_id}/tasks"
        tasks = self.post(
            path,
            {"task_type_ids": [str(self.task_type_animation.id)]},
            code=201,
        )
        self.assertEqual(len(tasks), 1)
        self.assertEqual(
            tasks[0]["task_type_id"], str(self.task_type_animation.id)
        )
        self.assertEqual(tasks[0]["entity_id"], self.shot_id)

    def test_create_entity_tasks_rejects_task_type_not_in_project(self):
        # task_type_animation is for_entity=Shot, never linked to project
        path = f"/data/entities/{self.shot_id}/tasks"
        self.post(
            path,
            {"task_type_ids": [str(self.task_type_animation.id)]},
            code=400,
        )

    def test_create_entity_tasks_rejects_wrong_for_entity(self):
        # task_type has for_entity="Asset", shot has wrong kind
        ProjectTaskTypeLink.create(
            project_id=self.project.id,
            task_type_id=self.task_type.id,
        )
        path = f"/data/entities/{self.shot_id}/tasks"
        self.post(
            path,
            {"task_type_ids": [self.task_type_id]},
            code=400,
        )

    def test_create_entity_tasks_rejects_task_type_not_in_asset_workflow(
        self,
    ):
        # task_type is in project, but asset_type workflow is empty
        ProjectTaskTypeLink.create(
            project_id=self.project.id,
            task_type_id=self.task_type.id,
        )
        path = f"/data/entities/{self.asset_id}/tasks"
        self.post(
            path,
            {"task_type_ids": [self.task_type_id]},
            code=400,
        )

    def test_create_entity_tasks_for_asset(self):
        ProjectTaskTypeLink.create(
            project_id=self.project.id,
            task_type_id=self.task_type.id,
        )
        self.asset_type.task_types = [self.task_type]
        self.asset_type.save()

        path = f"/data/entities/{self.asset_id}/tasks"
        tasks = self.post(
            path,
            {"task_type_ids": [self.task_type_id]},
            code=201,
        )
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_type_id"], self.task_type_id)
        self.assertEqual(tasks[0]["entity_id"], self.asset_id)

    def test_create_entity_tasks_defaults_to_project_task_types_on_shot(
        self,
    ):
        # Link two shot task types + one asset task type to the project.
        # An empty body should default to the project's shot task types
        # only (filtered by for_entity).
        for task_type_id in (
            self.task_type_animation.id,
            self.task_type_layout.id,
            self.task_type.id,
        ):
            ProjectTaskTypeLink.create(
                project_id=self.project.id, task_type_id=task_type_id
            )

        path = f"/data/entities/{self.shot_id}/tasks"
        tasks = self.post(path, {}, code=201)

        created_type_ids = {task["task_type_id"] for task in tasks}
        self.assertEqual(
            created_type_ids,
            {
                str(self.task_type_animation.id),
                str(self.task_type_layout.id),
            },
        )

    def test_create_entity_tasks_defaults_to_asset_workflow_on_asset(self):
        # Link two asset task types to the project but only one is in
        # the asset type's workflow. An empty body should create just
        # that one.
        for task_type_id in (
            self.task_type.id,
            self.task_type_modeling.id,
        ):
            ProjectTaskTypeLink.create(
                project_id=self.project.id, task_type_id=task_type_id
            )
        self.asset_type.task_types = [self.task_type]
        self.asset_type.save()

        path = f"/data/entities/{self.asset_id}/tasks"
        tasks = self.post(path, {}, code=201)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_type_id"], self.task_type_id)

    def test_task_assign(self):
        self.generate_fixture_task()
        person_id = str(self.person.id)
        task_id = str(self.task.id)
        data = {"person_id": person_id}
        self.put(f"/actions/tasks/{task_id}/assign", data, 200)
        task = self.get(f"data/tasks/{task_id}")
        self.assertEqual(task["assignees"][0], person_id)
        notifications = notifications_service.get_last_notifications(
            "assignation"
        )
        self.assertEqual(len(notifications), 1)
        self.assertEqual(str(notifications[0]["person_id"]), person_id)

    def test_task_assign_404(self):
        person_id = str(self.person.id)
        data = {"person_id": person_id}
        self.put(f"/actions/tasks/wrong-id/assign", data, 404)

    def test_task_assign_400(self):
        self.generate_fixture_task()
        person_id = "wrong-id"
        data = {"person_id": person_id}
        self.put(f"/actions/tasks/{self.task.id}/assign", data, 400)

    def test_multiple_task_assign(self):
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        task_id = str(self.task.id)
        shot_task_id = str(self.shot_task.id)
        person_id = str(self.person.id)
        data = {"task_ids": [task_id, shot_task_id]}
        self.put(f"/actions/persons/{person_id}/assign", data)

        task = tasks_service.get_task(task_id, relations=True)
        self.assertEqual(len(task["assignees"]), 1)
        task = tasks_service.get_task(shot_task_id, relations=True)
        self.assertEqual(len(task["assignees"]), 1)
        notifications = notifications_service.get_last_notifications()
        self.assertEqual(len(notifications), 2)

    def test_multiple_task_assign_artist(self):
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        self.generate_fixture_user_cg_artist()
        task_id = str(self.task.id)
        shot_task_id = str(self.shot_task.id)
        person_id = str(self.user_cg_artist["id"])
        department_id = str(self.department.id)
        data = {"task_ids": [task_id, shot_task_id]}
        self.put("/actions/tasks/clear-assignation", data)
        self.log_in_cg_artist()
        self.put(f"/actions/persons/{person_id}/assign", data)
        task = tasks_service.get_task(task_id, relations=True)
        self.assertEqual(len(task["assignees"]), 0)
        task = tasks_service.get_task(shot_task_id, relations=True)
        self.assertEqual(len(task["assignees"]), 0)
        persons_service.add_to_department(department_id, person_id)
        self.put(f"/actions/persons/{person_id}/assign", data)
        task = tasks_service.get_task(task_id, relations=True)
        self.assertEqual(len(task["assignees"]), 0)
        task = tasks_service.get_task(shot_task_id, relations=True)
        self.assertEqual(len(task["assignees"]), 0)

    def test_clear_assignation(self):
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        task_id = str(self.task.id)
        shot_task_id = str(self.shot_task.id)
        tasks_service.assign_task(self.task.id, self.person.id)
        tasks_service.assign_task(self.shot_task.id, self.person.id)
        data = {"task_ids": [task_id, shot_task_id]}
        self.put("/actions/tasks/clear-assignation", data)

        task = tasks_service.get_task(task_id, relations=True)
        self.assertEqual(len(task["assignees"]), 0)
        task = tasks_service.get_task(shot_task_id, relations=True)
        self.assertEqual(len(task["assignees"]), 0)

    def test_update_task_assignees(self):
        # The fixture task starts assigned to self.person.
        self.generate_fixture_task()
        task_id = str(self.task.id)
        person_id = str(self.person.id)
        self.put(f"data/tasks/{task_id}", {"assignees": []}, 200)
        task = tasks_service.get_task(task_id, relations=True)
        self.assertEqual(task["assignees"], [])
        self.put(f"data/tasks/{task_id}", {"assignees": [person_id]}, 200)
        task = tasks_service.get_task(task_id, relations=True)
        self.assertEqual(task["assignees"], [person_id])
        # The generic update emits the same task:assign event as the assign
        # route, so the assignation notification is created too.
        notifications = notifications_service.get_last_notifications(
            "assignation"
        )
        self.assertEqual(len(notifications), 1)
        self.assertEqual(str(notifications[0]["person_id"]), person_id)

    def test_set_tasks_priority(self):
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        task_id = str(self.task.id)
        shot_task_id = str(self.shot_task.id)
        data = {"task_ids": [task_id, shot_task_id], "priority": 2}
        result = self.put("/actions/tasks/set-priority", data)

        self.assertEqual(len(result), 2)
        self.assertTrue(all(task["priority"] == 2 for task in result))
        task = tasks_service.get_task(task_id)
        self.assertEqual(task["priority"], 2)
        task = tasks_service.get_task(shot_task_id)
        self.assertEqual(task["priority"], 2)

    def test_set_tasks_priority_skips_forbidden_tasks(self):
        self.generate_fixture_task()
        self.generate_fixture_user_cg_artist()
        task_id = str(self.task.id)
        data = {"task_ids": [task_id], "priority": 1}
        self.log_in_cg_artist()
        result = self.put("/actions/tasks/set-priority", data)

        self.assertEqual(result, [])
        self.log_in_admin()
        task = tasks_service.get_task(task_id)
        self.assertEqual(task["priority"], 0)

    def test_comment_task(self):
        self.project_id = self.project.id
        self.generate_fixture_user_manager()
        self.generate_fixture_user_cg_artist()
        user_cg_artist = persons_service.get_person_raw(
            self.user_cg_artist["id"]
        )
        user_manager = persons_service.get_person_raw(self.user_manager["id"])
        self.project.team = [self.person, user_cg_artist, user_manager]
        self.project.save()
        self.generate_fixture_task()
        path = f"/actions/tasks/{self.task.id}/comment/"
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test",
        }
        comment = self.post(path, data)
        self.assertEqual(comment["text"], data["comment"])
        self.assertEqual(
            comment["person"]["first_name"], self.user["first_name"]
        )
        self.assertEqual(comment["task_status"]["short_name"], "wip")

        tasks = self.get("/data/tasks")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_status_id"], str(self.wip_status_id))
        self.assertIsNotNone(tasks[0]["last_comment_date"])

        comments = self.get("/data/comments/")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["text"], data["comment"])
        self.assertEqual(comments[0]["person_id"], self.user["id"])

        notifications = notifications_service.get_last_notifications("comment")
        self.assertEqual(len(notifications), 1)
        notifications = notifications_service.get_last_notifications("mention")
        self.assertEqual(len(notifications), 0)

        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test @John Did2",
        }
        comment = self.post(path, data)
        notifications = notifications_service.get_last_notifications("comment")
        self.assertEqual(len(notifications), 2)
        notifications = notifications_service.get_last_notifications("mention")
        self.assertEqual(len(notifications), 1)

        news_list = news_service.get_last_news_for_project(
            project_id=self.project_id
        )
        self.assertEqual(len(news_list["data"]), 2)

    def test_edit_comment(self):
        self.generate_fixture_user_manager()
        self.generate_fixture_user_cg_artist()

        user = persons_service.get_person_raw(self.user["id"])
        user_cg_artist = persons_service.get_person_raw(
            self.user_cg_artist["id"]
        )
        user_manager = persons_service.get_person_raw(self.user_manager["id"])

        self.project.team = [self.person, user, user_cg_artist, user_manager]
        self.project.save()
        self.generate_fixture_task()
        path = f"/actions/tasks/{self.task.id}/comment/"
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test @John Doe",
        }
        comment = self.post(path, data)
        notifications = notifications_service.get_last_notifications("mention")
        self.assertEqual(len(notifications), 1)

        path = f"/data/comments/{comment['id']}"
        data = {"text": "comment test @John Did2 @John Did3"}
        comment = self.put(path, data)
        notifications = notifications_service.get_last_notifications("mention")
        self.assertEqual(len(notifications), 2)

    def test_comment_task_with_retake(self):
        self.generate_fixture_task()
        path = f"/actions/tasks/{self.task.id}/comment/"
        data = {
            "task_status_id": self.retake_status_id,
            "comment": "retake test",
        }
        data_wip = {
            "task_status_id": self.wip_status_id,
            "comment": "wip test",
        }
        self.post(path, data)
        tasks = self.get("/data/tasks")
        self.assertEqual(len(tasks), 1)
        tasks = self.get("/data/tasks")
        self.assertEqual(tasks[0]["retake_count"], 1)
        self.post(path, data)
        tasks = self.get("/data/tasks")
        self.assertEqual(tasks[0]["retake_count"], 1)
        self.post(path, data_wip)
        tasks = self.get("/data/tasks")
        self.assertEqual(tasks[0]["retake_count"], 1)
        self.post(path, data)
        tasks = self.get("/data/tasks")
        self.assertEqual(tasks[0]["retake_count"], 2)

    def test_comment_task_with_wip(self):
        self.generate_fixture_task()
        self.task.update({"real_start_date": None})
        path = f"/actions/tasks/{self.task.id}/comment/"
        data = {"task_status_id": self.wip_status_id, "comment": "wip test"}
        self.post(path, data)
        tasks = self.get("/data/tasks")
        self.assertIsNotNone(tasks[0]["real_start_date"])

    def test_comment_task_with_done(self):
        self.generate_fixture_task()
        self.task.update({"end_date": None})
        path = f"/actions/tasks/{self.task.id}/comment/"
        data = {"task_status_id": self.wfa_status_id, "comment": "wip test"}
        self.post(path, data)
        tasks = self.get("/data/tasks")
        self.assertIsNotNone(tasks[0]["end_date"])

    def test_task_comments(self):
        self.generate_fixture_project_standard()
        self.generate_fixture_asset_standard()
        self.generate_fixture_task_standard()
        self.generate_fixture_task()

        self.task_id = str(self.task.id)
        self.task_2_id = str(self.task_standard.id)

        path = f"/actions/tasks/{self.task_id}/comment/"
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test",
        }
        self.post(path, data)
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test 2",
        }
        self.post(path, data)

        path = f"/actions/tasks/{self.task_2_id}/comment/"
        self.post(path, data)

        path = f"/data/tasks/{self.task_id}/comments/"
        comments = self.get(path)
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["text"], data["comment"])
        self.assertEqual(
            comments[0]["person"]["first_name"], self.user["first_name"]
        )
        self.assertEqual(comments[0]["task_status"]["short_name"], "wip")

        path = "/actions/tasks/unknown/comments/"
        comments = self.get(path, 404)

    def test_delete_task_comment(self):
        self.generate_fixture_project_standard()
        self.generate_fixture_asset_standard()
        self.generate_fixture_task_standard()
        self.generate_fixture_task()

        self.task_id = str(self.task.id)

        path = f"/actions/tasks/{self.task_id}/comment/"
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test",
        }
        self.post(path, data)
        comment = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test 2",
        }
        comment = self.post(path, comment)

        path = f"/data/tasks/{self.task_id}/comments/{comment['id']}"
        comments = self.delete(path)
        self.delete(path, 404)
        path = f"/data/tasks/{self.task_id}/comments/"
        comments = self.get(path)
        self.assertEqual(len(comments), 1)

    def test_get_tasks_for_task_type_and_entity(self):
        self.generate_fixture_task()
        task_type_id = self.task_type.id
        task_type_animation_id = self.task_type_animation.id
        entity_id = self.asset.id

        tasks = self.get(
            f"/data/entities/{entity_id}/task-types/{task_type_id}/tasks"
        )
        self.assertEqual(len(tasks), 1)
        self.assertDictEqual(tasks[0], self.task.serialize())

        tasks = self.get(
            f"/data/entities/{entity_id}/task-types/{task_type_animation_id}/tasks"
        )
        self.assertEqual(len(tasks), 0)

    def test_get_tasks_for_person(self):
        self.generate_fixture_task()
        comments_service.new_comment(
            self.task.id, self.task_status.id, self.person.id, "first comment"
        )
        comments_service.new_comment(
            self.task.id, self.task_status.id, self.person.id, "last comment"
        )
        tasks = self.get(f"/data/persons/{self.person.id}/tasks")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["last_comment"]["text"], "last comment")
        self.assertEqual(
            tasks[0]["last_comment"]["person_id"], str(self.person.id)
        )
        self.assertEqual(len(tasks), 1)
        self.assertTrue(str(self.person.id) in tasks[0]["assignees"])

        tasks = self.get(f"/data/persons/{self.user['id']}/tasks")
        self.assertEqual(len(tasks), 0)

    def test_get_done_tasks_for_person(self):
        self.generate_fixture_task()
        self.task_id = self.task.id
        tasks = self.get(f"/data/persons/{self.person.id}/done-tasks")
        self.assertEqual(len(tasks), 0)

        done_status = tasks_service.get_or_create_status(
            "Done", "done", "#22d160", is_done=True
        )
        tasks_service.update_task(
            self.task_id, {"task_status_id": done_status["id"]}
        )

        tasks = self.get(f"/data/persons/{self.person.id}/done-tasks")
        self.assertEqual(len(tasks), 1)

    def test_get_related_tasks_for_person(self):
        task_type_id = str(self.task_type_animation.id)
        self.generate_fixture_task()
        task = self.generate_fixture_task(task_type_id=task_type_id)
        task.assignees = []
        task.save()
        tasks = self.get(
            f"/data/persons/{self.person.id}/related-tasks/{task_type_id}"
        )
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_type_id"], task_type_id)

    def test_delete_all_tasks_for_task_type(self):
        self.generate_fixture_project_standard()
        self.generate_fixture_asset_standard()
        task_1_id = str(self.generate_fixture_task().id)
        task_2_id = str(self.generate_fixture_task(name="second task").id)
        task_3_id = str(self.generate_fixture_shot_task().id)
        task_4_id = str(self.generate_fixture_task_standard().id)
        self.delete(
            f"/actions/projects/{self.project.id}/task-types/{self.task_type.id}/delete-tasks"
        )
        self.get(f"/data/tasks/{task_1_id}", 404)
        self.get(f"/data/tasks/{task_2_id}", 404)
        self.get(f"/data/tasks/{task_3_id}")
        self.get(f"/data/tasks/{task_4_id}")

    def test_delete_tasks(self):
        self.generate_fixture_project_standard()
        self.generate_fixture_asset_standard()
        task_1_id = str(self.generate_fixture_task().id)
        task_2_id = str(self.generate_fixture_task(name="second task").id)
        task_3_id = str(self.generate_fixture_shot_task().id)
        task_4_id = str(self.generate_fixture_task_standard().id)
        self.post(
            f"/actions/projects/{self.project.id}/delete-tasks",
            [task_1_id, task_2_id],
            code=200,
        )
        self.get(f"/data/tasks/{task_1_id}", 404)
        self.get(f"/data/tasks/{task_2_id}", 404)
        self.get(f"/data/tasks/{task_3_id}")
        self.get(f"/data/tasks/{task_4_id}")

    def test_get_tasks_permissions(self):
        self.generate_fixture_user_vendor()
        self.generate_fixture_user_cg_artist()
        task_1_id = str(self.generate_fixture_task().id)
        str(self.generate_fixture_task(name="second task").id)
        str(self.generate_fixture_shot_task().id)

        user_id = self.user_cg_artist["id"]
        tasks = self.get("/data/tasks/")
        self.assertEqual(len(tasks), 3)
        self.log_in_cg_artist()
        tasks = self.get("/data/tasks/")
        self.assertEqual(len(tasks), 0)
        projects_service.add_team_member(self.project_id, user_id)
        tasks = self.get("/data/tasks/")
        self.assertEqual(len(tasks), 3)

        user_id = str(self.user_vendor["id"])
        self.log_in_vendor()
        tasks = self.get("/data/tasks/")
        self.assertEqual(len(tasks), 0)
        projects_service.add_team_member(self.project_id, user_id)
        tasks = self.get("/data/tasks/")
        self.assertEqual(len(tasks), 0)
        tasks_service.assign_task(task_1_id, user_id)
        tasks = self.get("/data/tasks/")
        self.assertEqual(len(tasks), 1)

    def test_get_shot_tasks_for_sequence(self):
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        self.generate_fixture_shot_task("second")
        shot_id = str(self.shot.id)
        tasks = self.get(f"/data/sequences/{self.sequence.id}/shot-tasks")
        self.assertEqual(len(tasks), 2)
        self.assertTrue(shot_id in [task["entity_id"] for task in tasks])

    def test_get_shot_tasks_for_episode(self):
        self.generate_fixture_task()
        self.generate_fixture_episode()
        self.sequence.update({"parent_id": self.episode.id})
        self.generate_fixture_shot_task()
        self.generate_fixture_shot_task("second")
        shot_id = str(self.shot.id)
        tasks = self.get(f"/data/episodes/{self.episode.id}/shot-tasks")
        self.assertEqual(len(tasks), 2)
        self.assertTrue(shot_id in [task["entity_id"] for task in tasks])

    def test_update_task_priority(self):
        self.assertEqual(ProjectTaskTypeLink.query.count(), 0)
        self.post(
            "/data/task-type-links",
            {
                "task_type_id": TaskType.query.first().id,
                "project_id": Project.query.first().id,
                "priority": 2,
            },
        )
        self.assertEqual(ProjectTaskTypeLink.query.first().priority, 2)
        self.post(
            "/data/task-type-links",
            {
                "task_type_id": TaskType.query.first().id,
                "project_id": Project.query.first().id,
                "priority": 3,
            },
        )
        self.assertEqual(ProjectTaskTypeLink.query.count(), 1)
        self.assertEqual(ProjectTaskTypeLink.query.first().priority, 3)

    def test_reorder_task_type_links(self):
        project_id = str(self.project.id)
        tt1 = str(self.task_type.id)
        tt2 = str(self.task_type_concept.id)
        projects_service.create_project_task_type_link(project_id, tt1, 1)
        projects_service.create_project_task_type_link(project_id, tt2, 2)
        result = self.post(
            f"/actions/projects/{project_id}/task-type-links/reorder",
            {"task_type_ids": [tt2, tt1]},
            200,
        )
        by_type = {link["task_type_id"]: link["priority"] for link in result}
        self.assertEqual(by_type[tt2], 1)
        self.assertEqual(by_type[tt1], 2)

    def test_reorder_task_types(self):
        tt1 = str(self.task_type.id)
        tt2 = str(self.task_type_concept.id)
        result = self.post(
            "/actions/task-types/reorder",
            {"task_type_ids": [tt2, tt1]},
            200,
        )
        by_type = {
            task_type["id"]: task_type["priority"] for task_type in result
        }
        self.assertEqual(by_type[tt2], 1)
        self.assertEqual(by_type[tt1], 2)

    def test_reorder_task_status_links_preserves_roles(self):
        from zou.app.models.project import ProjectTaskStatusLink

        project_id = str(self.project.id)
        ts1 = str(self.task_status_wip.id)
        ts2 = str(self.task_status_done.id)
        ProjectTaskStatusLink.create(
            project_id=project_id,
            task_status_id=ts1,
            priority=1,
            roles_for_board=["manager"],
        )
        ProjectTaskStatusLink.create(
            project_id=project_id, task_status_id=ts2, priority=2
        )
        result = self.post(
            f"/actions/projects/{project_id}/task-status-links/reorder",
            {"task_status_ids": [ts2, ts1]},
            200,
        )
        by_status = {link["task_status_id"]: link for link in result}
        self.assertEqual(by_status[ts2]["priority"], 1)
        self.assertEqual(by_status[ts1]["priority"], 2)
        # The reorder only updates priority, board roles are preserved.
        self.assertEqual(by_status[ts1]["roles_for_board"], ["manager"])

    def test_update_entity_main_preview_from_task(self):
        task = self.generate_fixture_task().serialize()
        preview_file = self.generate_fixture_preview_file().serialize()
        self.put(
            f"/actions/tasks/{preview_file['task_id']}/set-main-preview", {}
        )
        entity = self.get(f"/data/entities/{task['entity_id']}")
        self.assertEqual(entity["preview_file_id"], preview_file["id"])

    def test_open_tasks(self):
        self.generate_fixture_task()
        task_id = str(self.task.id)
        self.task.update({"task_status_id": self.wip_status_id})
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()
        self.generate_fixture_task(entity_id=self.asset_character.id)

        animation_id = str(self.task_type_animation.id)
        self.generate_fixture_shot_task()
        self.generate_fixture_shot("SHOT_002")
        self.generate_fixture_shot_task()
        self.generate_fixture_shot("SHOT_003")
        self.generate_fixture_shot_task()

        tasks = self.get("/data/tasks/open-tasks")
        self.assertEqual(len(tasks["data"]), 5)

        self.generate_fixture_project_closed_status()
        self.generate_fixture_project_closed()
        asset = self.generate_fixture_asset(project_id=self.project_closed.id)
        self.generate_fixture_task(
            entity_id=asset.id, project_id=self.project_closed.id
        )
        tasks = self.get("/data/tasks/open-tasks")
        self.assertEqual(len(tasks["data"]), 5)

        self.generate_fixture_project_standard()
        self.generate_fixture_asset_standard()
        self.generate_fixture_task_standard()
        tasks = self.get("/data/tasks/open-tasks")
        self.assertEqual(len(tasks["data"]), 6)

        tasks = self.get(
            f"/data/tasks/open-tasks?project_id={self.project.id}"
        )
        self.assertEqual(len(tasks["data"]), 5)

        tasks = self.get(
            f"/data/tasks/open-tasks?project_id={self.project.id}&limit=3"
        )
        self.assertEqual(len(tasks["data"]), 3)

        tasks = self.get(
            f"/data/tasks/open-tasks?project_id={self.project.id}&limit=3&page=2"
        )
        self.assertEqual(len(tasks["data"]), 2)

        tasks = self.get(f"/data/tasks/open-tasks?task_type_id={animation_id}")
        self.assertEqual(len(tasks["data"]), 3)

        tasks = self.get(
            f"/data/tasks/open-tasks?task_status_id={self.wip_status_id}"
        )
        self.assertEqual(len(tasks["data"]), 1)

        jane = self.generate_fixture_person(
            "Jane", "Doe", "jane.doe", "jane.doe@gmail.com"
        )
        data = {"person_id": jane.id}
        self.put(f"/actions/tasks/{task_id}/assign", data, 200)
        self.put(f"/actions/tasks/{self.shot_task.id}/assign", data, 200)
        tasks = self.get(f"/data/tasks/open-tasks?person_id={jane.id}")
        self.assertEqual(len(tasks["data"]), 2)
