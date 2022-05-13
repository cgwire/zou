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
        path = "/actions/projects/%s/task-types/%s/assets/create-tasks" % (
            self.project.id,
            self.task_type_id,
        )
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
        path = "/actions/projects/%s/task-types/%s/assets/create-tasks" % (
            self.project.id,
            self.task_type_id,
        )
        tasks = self.post(path, [self.asset_id])
        self.assertEqual(len(tasks), 1)
        tasks = self.get("/data/tasks")
        self.assertEqual(len(tasks), 1)
        task = tasks[0]
        self.assertEqual(task["name"], "main")
        self.assertEqual(task["task_type_id"], self.task_type_id)
        self.assertEqual(task["entity_id"], self.asset_id)

    def test_create_shot_tasks(self):
        path = "/actions/projects/%s/task-types/%s/shots/create-tasks" % (
            self.project.id,
            self.task_type_id,
        )
        tasks = self.post(path, {})
        self.assertEqual(len(tasks), 1)

        tasks = self.get("/data/tasks")
        self.assertEqual(len(tasks), 1)
        task = tasks[0]
        self.assertEqual(task["name"], "main")
        self.assertEqual(task["task_type_id"], self.task_type_id)
        self.assertEqual(task["entity_id"], self.shot_id)

    def test_task_assign(self):
        self.generate_fixture_task()
        person_id = str(self.person.id)
        task_id = str(self.task.id)
        data = {"person_id": person_id}
        self.put("/actions/tasks/%s/assign" % task_id, data, 200)
        task = self.get("data/tasks/%s" % task_id)
        self.assertEqual(task["assignees"][0], person_id)
        notifications = notifications_service.get_last_notifications(
            "assignation"
        )
        self.assertEqual(len(notifications), 1)
        self.assertEqual(str(notifications[0]["person_id"]), person_id)

    def test_task_assign_404(self):
        person_id = str(self.person.id)
        data = {"person_id": person_id}
        self.put("/actions/tasks/%s/assign" % "wrong-id", data, 404)

    def test_task_assign_400(self):
        self.generate_fixture_task()
        person_id = "wrong-id"
        data = {"person_id": person_id}
        self.put("/actions/tasks/%s/assign" % self.task.id, data, 400)

    def test_multiple_task_assign(self):
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        task_id = str(self.task.id)
        shot_task_id = str(self.shot_task.id)
        person_id = str(self.person.id)
        data = {"task_ids": [task_id, shot_task_id]}
        self.put("/actions/persons/%s/assign" % person_id, data)

        task = tasks_service.get_task_with_relations(task_id)
        self.assertEqual(len(task["assignees"]), 1)
        task = tasks_service.get_task_with_relations(shot_task_id)
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
        self.put("/actions/persons/%s/assign" % person_id, data)
        task = tasks_service.get_task_with_relations(task_id)
        self.assertEqual(len(task["assignees"]), 0)
        task = tasks_service.get_task_with_relations(shot_task_id)
        self.assertEqual(len(task["assignees"]), 0)
        persons_service.add_to_department(department_id, person_id)
        self.put("/actions/persons/%s/assign" % person_id, data)
        task = tasks_service.get_task_with_relations(task_id)
        self.assertEqual(len(task["assignees"]), 0)
        task = tasks_service.get_task_with_relations(shot_task_id)
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

        task = tasks_service.get_task_with_relations(task_id)
        self.assertEqual(len(task["assignees"]), 0)
        task = tasks_service.get_task_with_relations(shot_task_id)
        self.assertEqual(len(task["assignees"]), 0)

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
        path = "/actions/tasks/%s/comment/" % self.task.id
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

        news_list = news_service.get_last_news_for_project(self.project_id)
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
        path = "/actions/tasks/%s/comment/" % self.task.id
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test @John Doe",
        }
        comment = self.post(path, data)
        notifications = notifications_service.get_last_notifications("mention")
        self.assertEqual(len(notifications), 1)

        path = "/data/comments/%s" % comment["id"]
        data = {"text": "comment test @John Did2 @John Did3"}
        comment = self.put(path, data)
        notifications = notifications_service.get_last_notifications("mention")
        self.assertEqual(len(notifications), 2)

    def test_comment_task_with_retake(self):
        self.generate_fixture_task()
        path = "/actions/tasks/%s/comment/" % self.task.id
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
        path = "/actions/tasks/%s/comment/" % self.task.id
        data = {"task_status_id": self.wip_status_id, "comment": "wip test"}
        self.post(path, data)
        tasks = self.get("/data/tasks")
        self.assertIsNotNone(tasks[0]["real_start_date"])

    def test_comment_task_with_done(self):
        self.generate_fixture_task()
        self.task.update({"end_date": None})
        path = "/actions/tasks/%s/comment/" % self.task.id
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

        path = "/actions/tasks/%s/comment/" % self.task_id
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

        path = "/actions/tasks/%s/comment/" % self.task_2_id
        self.post(path, data)

        path = "/data/tasks/%s/comments/" % self.task_id
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

        path = "/actions/tasks/%s/comment/" % self.task_id
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

        path = "/data/tasks/%s/comments/%s" % (self.task_id, comment["id"])
        comments = self.delete(path)
        self.delete(path, 404)
        path = "/data/tasks/%s/comments/" % self.task_id
        comments = self.get(path)
        self.assertEqual(len(comments), 1)

    def test_get_tasks_for_task_type_and_entity(self):
        self.generate_fixture_task()
        task_type_id = self.task_type.id
        task_type_animation_id = self.task_type_animation.id
        entity_id = self.asset.id

        tasks = self.get(
            "/data/entities/%s/task-types/%s/tasks" % (entity_id, task_type_id)
        )
        self.assertEqual(len(tasks), 1)
        self.assertDictEqual(tasks[0], self.task.serialize())

        tasks = self.get(
            "/data/entities/%s/task-types/%s/tasks"
            % (entity_id, task_type_animation_id)
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
        tasks = self.get("/data/persons/%s/tasks" % self.person.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["last_comment"]["text"], "last comment")
        self.assertEqual(
            tasks[0]["last_comment"]["person_id"], str(self.person.id)
        )
        self.assertEqual(len(tasks), 1)
        self.assertTrue(str(self.person.id) in tasks[0]["assignees"])

        tasks = self.get("/data/persons/%s/tasks" % self.user["id"])
        self.assertEqual(len(tasks), 0)

    def test_get_done_tasks_for_person(self):
        self.generate_fixture_task()
        self.task_id = self.task.id
        tasks = self.get("/data/persons/%s/done-tasks" % self.person.id)
        self.assertEqual(len(tasks), 0)

        done_status = tasks_service.get_or_create_status(
            "Done", "done", "#22d160", is_done=True
        )
        tasks_service.update_task(
            self.task_id, {"task_status_id": done_status["id"]}
        )

        tasks = self.get("/data/persons/%s/done-tasks" % self.person.id)
        self.assertEqual(len(tasks), 1)

    def test_get_related_tasks_for_person(self):
        task_type_id = str(self.task_type_animation.id)
        self.generate_fixture_task()
        task = self.generate_fixture_task(task_type_id=task_type_id)
        task.assignees = []
        task.save()
        tasks = self.get(
            "/data/persons/%s/related-tasks/%s"
            % (self.person.id, task_type_id)
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
            "/actions/projects/%s/task-types/%s/delete-tasks"
            % (self.project.id, self.task_type.id)
        )
        self.get("/data/tasks/%s" % task_1_id, 404)
        self.get("/data/tasks/%s" % task_2_id, 404)
        self.get("/data/tasks/%s" % task_3_id)
        self.get("/data/tasks/%s" % task_4_id)

    def test_delete_tasks(self):
        self.generate_fixture_project_standard()
        self.generate_fixture_asset_standard()
        task_1_id = str(self.generate_fixture_task().id)
        task_2_id = str(self.generate_fixture_task(name="second task").id)
        task_3_id = str(self.generate_fixture_shot_task().id)
        task_4_id = str(self.generate_fixture_task_standard().id)
        self.post(
            "/actions/projects/%s/delete-tasks" % self.project.id,
            [task_1_id, task_2_id],
            code=200,
        )
        self.get("/data/tasks/%s" % task_1_id, 404)
        self.get("/data/tasks/%s" % task_2_id, 404)
        self.get("/data/tasks/%s" % task_3_id)
        self.get("/data/tasks/%s" % task_4_id)

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
        tasks = self.get("/data/sequences/%s/shot-tasks" % self.sequence.id)
        self.assertEqual(len(tasks), 2)
        self.assertTrue(shot_id in [task["entity_id"] for task in tasks])

    def test_get_shot_tasks_for_episode(self):
        self.generate_fixture_task()
        self.generate_fixture_episode()
        self.sequence.update({"parent_id": self.episode.id})
        self.generate_fixture_shot_task()
        self.generate_fixture_shot_task("second")
        shot_id = str(self.shot.id)
        tasks = self.get("/data/episodes/%s/shot-tasks" % self.episode.id)
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
