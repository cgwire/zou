from tests.services.cases import TaskTestCase, UserContextTestCase
from zou.app import db
from zou.app.models.entity import EntityLink
from zou.app.models.person import Person
from zou.app.models.studio import Studio
from zou.app.models.task import Task
from zou.app.services import (
    comments_service,
    task_types_service,
    tasks_service,
    todos_service,
)


def ids_of(tasks):
    return {task["id"] for task in tasks}


class TaskReaderTestCase(TaskTestCase):
    def test_get_tasks_for_project_loads_only_assignee_ids(self):
        with self.collect_statements() as statements:
            tasks = todos_service.get_tasks_for_project(self.project.id)

        assignees = [
            assignee for task in tasks for assignee in task["assignees"]
        ]
        self.assertIn(self.person_id, assignees)
        self.assertTrue(
            all(isinstance(assignee, str) for assignee in assignees)
        )

        person_link_statements = [
            statement
            for statement in statements
            if "task_person_link" in statement.lower()
        ]
        self.assertTrue(person_link_statements)
        for statement in person_link_statements:
            self.assertNotIn("person.password", statement)

    def test_get_tasks_for_project_loads_assignees_in_one_query(self):
        # selectinload batches 500 ids per IN, a large project sent
        # one query per batch (KITSU-API-4W3). 501 tasks make two batches.
        tasks = [
            Task(
                name=f"Bulk {index}",
                project_id=self.task.project_id,
                task_type_id=self.task.task_type_id,
                task_status_id=self.task.task_status_id,
                entity_id=self.task.entity_id,
                assigner_id=self.task.assigner_id,
                assignees=[self.person],
            )
            for index in range(501)
        ]
        db.session.add_all(tasks)
        db.session.commit()

        with self.collect_statements() as statements:
            result = todos_service.get_tasks_for_project(self.project.id)

        self.assertEqual(len(result), 503)
        bulk = [task for task in result if task["name"].startswith("Bulk")]
        self.assertTrue(
            all(task["assignees"] == [self.person_id] for task in bulk)
        )
        person_link_statements = [
            statement
            for statement in statements
            if "task_person_link" in statement.lower()
        ]
        self.assertEqual(len(person_link_statements), 1)


class ProjectTasksFilterTestCase(TaskTestCase, UserContextTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_episode()
        self.sequence.update({"parent_id": self.episode.id})

    def test_get_tasks_for_project_filters_by_task_type(self):
        tasks = todos_service.get_tasks_for_project(
            self.project.id, task_type_id=self.task_type.id
        )
        self.assertEqual(ids_of(tasks), {self.task_id})

    def test_get_tasks_for_project_filters_by_episode(self):
        with self.as_user():
            tasks = todos_service.get_tasks_for_project(
                self.project.id, episode_id=self.episode.id
            )
        self.assertEqual(ids_of(tasks), {str(self.shot_task.id)})

        first_episode = self.episode
        self.sequence.update(
            {"parent_id": self.generate_fixture_episode("E02").id}
        )
        with self.as_user():
            self.assertEqual(
                todos_service.get_tasks_for_project(
                    self.project.id, episode_id=first_episode.id
                ),
                [],
            )

    def test_an_episode_listing_is_limited_to_the_projects_of_the_user(self):
        artist = self.generate_fixture_user_cg_artist()
        with self.as_user(artist):
            self.assertEqual(
                todos_service.get_tasks_for_project(
                    self.project.id, episode_id=self.episode.id
                ),
                [],
            )

        self.project.team.append(Person.get(artist["id"]))
        self.project.save()
        with self.as_user(artist):
            tasks = todos_service.get_tasks_for_project(
                self.project.id, episode_id=self.episode.id
            )
        self.assertEqual(ids_of(tasks), {str(self.shot_task.id)})


class PersonTaskTestCase(TaskTestCase):
    def test_get_person_tasks(self):
        projects = [self.project.serialize()]
        self.assertEqual(
            todos_service.get_person_tasks(self.user["id"], projects), []
        )

        tasks_service.assign_task(self.task.id, self.user["id"])
        self.assertEqual(
            len(todos_service.get_person_tasks(self.user["id"], projects)), 1
        )

        comments_service.new_comment(
            self.task.id, self.task_status.id, self.person.id, "first comment"
        )
        comments_service.new_comment(
            self.task.id, self.task_status.id, self.person.id, "last comment"
        )

        tasks = todos_service.get_person_tasks(self.person.id, projects)
        tasks = sorted(tasks, key=lambda task: task["task_type_name"])
        self.assertEqual(len(tasks), 2)
        # Animation comes first, so the commented task is the second one.
        self.assertEqual(tasks[1]["last_comment"]["text"], "last comment")
        self.assertEqual(tasks[1]["last_comment"]["person_id"], self.person_id)

    def test_get_person_done_tasks(self):
        projects = [self.project.serialize()]
        self.assertEqual(
            todos_service.get_person_done_tasks(self.user["id"], projects), []
        )

        tasks_service.assign_task(self.task.id, self.user["id"])
        self.assertEqual(
            todos_service.get_person_done_tasks(self.user["id"], projects), []
        )

        done_status = task_types_service.get_or_create_task_status(
            "Done", "done", "#22d160", is_done=True
        )
        tasks_service.update_task(
            self.task.id, {"task_status_id": done_status["id"]}
        )

        self.assertEqual(
            len(
                todos_service.get_person_done_tasks(self.user["id"], projects)
            ),
            1,
        )

    def test_get_person_tasks_lists_the_episodes_an_asset_is_cast_in(self):
        self.generate_fixture_episode()
        EntityLink.create(
            entity_in_id=self.episode.id, entity_out_id=self.asset.id
        )
        projects = [self.project.serialize()]

        tasks = todos_service.get_person_tasks(self.person.id, projects)

        tasks = {task["id"]: task for task in tasks}
        asset_task = tasks[self.task_id]
        self.assertEqual(
            [str(episode_id) for episode_id in asset_task["episode_ids"]],
            [str(self.episode.id)],
        )
        self.assertEqual(asset_task["episode_names"], ["E01"])
        self.assertNotIn("episode_ids", tasks[str(self.shot_task.id)])


class TasksToCheckTestCase(TaskTestCase):
    """
    Both tasks wait for feedback. The asset task is assigned and has dates,
    the shot task has neither.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_task_status_wfa()
        self.wfa_status_id = str(self.task_status_wfa.id)
        for task in [self.task, self.shot_task]:
            task.update({"task_status_id": self.task_status_wfa.id})
        self.shot_task.assignees = []
        self.shot_task.save()
        self.project_ids = [self.project_id]

    def to_check(self, **kwargs):
        return ids_of(
            todos_service.get_person_tasks_to_check(
                project_ids=self.project_ids, **kwargs
            )
        )

    def test_the_tasks_to_check_are_filtered(self):
        both = {self.task_id, str(self.shot_task.id)}
        self.assertEqual(self.to_check(), both)
        for label, kwargs, expected in [
            ("status", {"task_status_id": self.wfa_status_id}, both),
            ("other status", {"task_status_id": self.wip_status_id}, set()),
            ("person", {"person_id": self.person_id}, {self.task_id}),
            ("due date", {"due_date_until": "2017-03-01"}, {self.task_id}),
            ("due date before", {"due_date_until": "2017-02-27"}, set()),
        ]:
            with self.subTest(label=label):
                self.assertEqual(self.to_check(**kwargs), expected)

    def test_the_filter_values_are_scoped(self):
        values = todos_service.get_person_tasks_to_check_filter_values(
            project_ids=self.project_ids, scope=Task.id == self.task.id
        )
        self.assertEqual(values["project_ids"], [self.project_id])
        self.assertEqual(values["task_type_ids"], [str(self.task_type.id)])

        self.generate_fixture_project_standard()
        values = todos_service.get_person_tasks_to_check_filter_values(
            project_ids=[str(self.project_standard.id)]
        )
        self.assertEqual(values["project_ids"], [])


class OpenTasksTestCase(TaskTestCase, UserContextTestCase):
    """
    The asset task is assigned to a person of a studio and a department,
    and has dates. The shot task has no assignee and no date.
    """

    def setUp(self):
        super().setUp()
        self.studio = Studio.create(name="North", color="#FFFFFF")
        self.person.studio_id = self.studio.id
        self.person.departments = [self.department]
        self.person.save()
        self.shot_task.assignees = []
        self.shot_task.save()

    def open_tasks(self, **kwargs):
        with self.as_user():
            result = todos_service.get_open_tasks(
                tasks_service.OpenTasksFilters(**kwargs)
            )
        return ids_of(result["data"])

    def test_the_open_tasks_are_filtered(self):
        shot_task_id = str(self.shot_task.id)
        self.assertEqual(self.open_tasks(), {self.task_id, shot_task_id})
        for label, kwargs, expected in [
            ("unassigned", {"person_id": "unassigned"}, {shot_task_id}),
            ("studio", {"studio_id": str(self.studio.id)}, {self.task_id}),
            (
                "department",
                {"department_id": str(self.department.id)},
                {self.task_id},
            ),
            ("start date", {"start_date": "2017-02-19"}, {self.task_id}),
            ("late start date", {"start_date": "2017-02-21"}, set()),
            ("due date", {"due_date": "2017-03-01"}, {self.task_id}),
            ("early due date", {"due_date": "2017-02-27"}, set()),
        ]:
            with self.subTest(label=label):
                self.assertEqual(self.open_tasks(**kwargs), expected)
