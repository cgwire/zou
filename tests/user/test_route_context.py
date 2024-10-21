from tests.base import ApiDBTestCase

from zou.app.services import (
    tasks_service,
    notifications_service,
    persons_service,
    projects_service,
    user_service,
)

from zou.app.models.project import Project
from zou.app.models.person import Person


class UserContextRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(UserContextRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project_closed_status()
        self.generate_fixture_project()
        self.generate_fixture_person()
        self.generate_fixture_project_closed()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_to_review()
        self.generate_fixture_assigner()

        self.project_id = self.project.id

        self.task_dict = self.generate_fixture_task().serialize(relations=True)
        self.task_id = self.task.id
        self.sequence_dict = self.sequence.serialize()

        self.shot_task_dict = self.generate_fixture_shot_task().serialize(
            relations=True
        )
        self.task_type_dict = self.task_type_animation.serialize()
        self.shot_task_id = self.task.id

        self.asset_dict = self.asset.serialize(obj_type="Asset")
        self.maxDiff = None

        self.project_closed_id = self.project_closed.id
        self.user_id = self.user["id"]

    def assign_user(self, task_id):
        tasks_service.assign_task(task_id, self.user_id)
        project = Project.get(self.project_id)
        person = Person.get(self.user_id)
        project.team.append(person)
        project.save()

    def test_get_project_sequences(self):
        self.assign_user(self.shot_task.id)
        sequences = self.get(
            "data/user/projects/%s/sequences" % self.project.id
        )
        self.assertEqual(len(sequences), 1)

    def test_get_project_episodes(self):
        self.assign_user(self.shot_task.id)
        episodes = self.get("data/user/projects/%s/episodes" % self.project.id)
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["name"], "E01")
        self.assertEqual(episodes[0]["type"], "Episode")

    def test_get_sequence_shots(self):
        self.assign_user(self.shot_task.id)
        shots = self.get("data/user/sequences/%s/shots" % self.sequence.id)
        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["type"], "Shot")
        self.assertEqual(shots[0]["name"], "P01")

    def test_get_sequence_scenes(self):
        self.generate_fixture_scene()
        self.generate_fixture_scene_task()
        self.assign_user(self.scene_task.id)
        scenes = self.get("data/user/sequences/%s/scenes" % self.sequence.id)
        self.assertEqual(len(scenes), 1)
        self.assertEqual(scenes[0]["type"], "Scene")
        self.assertEqual(scenes[0]["name"], "SC01")

    def test_get_project_asset_types(self):
        task_id = self.task.id
        shot_task_id = self.shot_task.id
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()
        self.generate_fixture_task("main", self.asset_character.id)
        task2_id = self.task.id
        self.generate_fixture_task("second", self.asset_character.id)
        task3_id = self.task.id

        asset_types = self.get(
            "data/user/projects/%s/asset-types" % self.project.id
        )
        self.assertEqual(len(asset_types), 0)

        self.assign_user(task_id)
        self.assign_user(task2_id)
        self.assign_user(task3_id)
        self.assign_user(shot_task_id)
        asset_types = self.get(
            "data/user/projects/%s/asset-types" % self.project.id
        )
        self.assertEqual(len(asset_types), 2)

    def test_get_project_asset_types_assets(self):
        task_id = self.task.id
        assets = self.get(
            "data/user/projects/%s/asset-types/%s/assets"
            % (self.project.id, self.asset_type.id)
        )
        self.assertEqual(len(assets), 0)
        self.assign_user(task_id)

        assets = self.get(
            "data/user/projects/%s/asset-types/%s/assets"
            % (self.project.id, self.asset_type.id)
        )
        self.assertEqual(len(assets), 1)

    def test_get_asset_tasks(self):
        path = "data/user/assets/%s/tasks" % self.asset.id
        task_id = self.task.id

        tasks = self.get(path)
        self.assertEqual(len(tasks), 0)

        self.assign_user(task_id)
        tasks = self.get(path)
        self.assertEqual(len(tasks), 1)

    def test_get_shot_tasks(self):
        path = "data/user/shots/%s/tasks" % self.shot.id
        shot_task_id = self.shot_task.id

        tasks = self.get(path)
        self.assertEqual(len(tasks), 0)

        self.assign_user(shot_task_id)
        tasks = self.get(path)
        self.assertEqual(len(tasks), 1)

    def test_get_scene_tasks(self):
        self.generate_fixture_scene()
        self.generate_fixture_scene_task()
        scene_task_id = self.scene_task.id
        path = "data/user/scenes/%s/tasks" % self.scene.id

        tasks = self.get(path)
        self.assertEqual(len(tasks), 0)

        self.assign_user(scene_task_id)
        tasks = self.get(path)
        self.assertEqual(len(tasks), 1)

    def test_get_asset_task_types(self):
        path = "data/user/assets/%s/task-types" % self.asset.id
        task_id = self.task.id
        task_type_id = self.task_type.id

        task_types = self.get(path)
        self.assertEqual(len(task_types), 0)

        self.assign_user(task_id)
        task_types = self.get(path)
        self.assertEqual(len(task_types), 1)
        self.assertEqual(task_types[0]["id"], str(task_type_id))

    def test_get_shot_task_types(self):
        path = "data/user/shots/%s/task-types" % self.shot.id
        shot_task_id = self.shot_task.id

        task_types = self.get(path)
        self.assertEqual(len(task_types), 0)

        self.assign_user(shot_task_id)
        task_types = self.get(path)
        self.assertEqual(len(task_types), 1)

    def test_get_scene_task_types(self):
        self.generate_fixture_scene()
        self.generate_fixture_scene_task()
        path = "data/user/scenes/%s/task-types" % self.scene.id
        scene_task_id = self.scene_task.id

        task_types = self.get(path)
        self.assertEqual(len(task_types), 0)

        self.assign_user(scene_task_id)
        task_types = self.get(path)
        self.assertEqual(len(task_types), 1)

    def test_get_open_projects(self):
        projects = self.get("data/user/projects/open")
        self.assertEqual(len(projects), 1)

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        projects = self.get("data/user/projects/open")
        self.assertEqual(len(projects), 0)

        project = Project.get(self.project_id)
        person = Person.get(self.user_cg_artist["id"])
        project.team.append(person)
        project.save()

        projects = self.get("data/user/projects/open")
        self.assertEqual(len(projects), 1)

        self.log_in_admin()
        projects = self.get("data/user/projects/open")
        self.assertEqual(len(projects), 1)

        project = Project.get(self.project_id)
        project.team[:] = []
        project.save()

        projects = self.get("data/user/projects/open")
        self.assertEqual(len(projects), 1)

        self.log_in_cg_artist()
        projects = self.get("data/user/projects/open")
        self.assertEqual(len(projects), 0)

    def test_get_todos(self):
        task_id = self.task.id
        shot_task_id = self.shot_task.id

        path = "data/user/tasks/"
        tasks = self.get(path)
        self.assertEqual(len(tasks), 0)

        self.assign_user(task_id)
        self.assign_user(shot_task_id)

        path = "data/user/tasks/"
        tasks = self.get(path)
        self.assertEqual(len(tasks), 2)

        tasks_service.update_task(
            shot_task_id,
            {
                "task_status_id": tasks_service.get_or_create_status(
                    "Done", "done", "#22d160", is_done=True
                )["id"]
            },
        )

        path = "data/user/tasks/"
        tasks = self.get(path)
        self.assertEqual(len(tasks), 1)

    def test_get_done_tasks(self):
        task_id = self.task.id

        path = "data/user/done-tasks/"
        tasks = self.get(path)
        self.assertEqual(len(tasks), 0)

        self.assign_user(task_id)

        path = "data/user/done-tasks/"
        tasks = self.get(path)
        self.assertEqual(len(tasks), 0)

        done_status = tasks_service.get_or_create_status(
            "Done", "done", "#22d160", is_done=True
        )
        tasks_service.update_task(
            task_id, {"task_status_id": done_status["id"]}
        )

        path = "data/user/done-tasks/"
        tasks = self.get(path)
        self.assertEqual(len(tasks), 1)

    def test_get_filter_groups(self):
        project_id = str(self.project.id)
        path = "data/user/filter-groups/"
        filter_group_1 = {
            "list_type": "asset",
            "name": "g1",
            "color": "#000000",
            "project_id": project_id,
        }
        filter_group_2 = {
            "list_type": "shot",
            "name": "g2",
            "color": "#000000",
            "project_id": project_id,
        }
        filter_group_3 = {
            "list_type": "all",
            "name": "g3",
            "color": "#000000",
            "project_id": project_id,
        }
        self.post(path, filter_group_1)
        self.post(path, filter_group_2)
        self.post(path, filter_group_3)

        result = self.get(path)
        self.assertTrue("asset" in result)
        self.assertTrue("shot" in result)
        self.assertTrue("all" in result)
        self.assertEqual(len(result["asset"][project_id]), 1)
        self.assertEqual(len(result["shot"][project_id]), 1)
        self.assertEqual(len(result["all"][project_id]), 1)
        self.assertEqual(result["asset"][project_id][0]["name"], "g1")
        self.assertEqual(result["shot"][project_id][0]["name"], "g2")
        self.assertEqual(result["all"][project_id][0]["name"], "g3")

    def test_update_filter_group(self):
        project_id = str(self.project.id)
        path = "data/user/filter-groups"
        filter_group_1 = {
            "list_type": "asset",
            "name": "g1",
            "color": "#000000",
            "project_id": project_id,
        }
        search_filter_group = self.post(path, filter_group_1)
        result = self.get(path)
        self.assertTrue("asset" in result)
        self.put(
            "%s/%s" % (path, search_filter_group["id"]), {"name": "updated"}
        )
        result = self.get(
            "data/search-filter-groups/%s" % search_filter_group["id"]
        )
        self.assertEqual(result["name"], "updated")

    def test_remove_filter_group(self):
        project_id = str(self.project.id)
        path = "data/user/filter-groups"
        filter_group_1 = {
            "list_type": "asset",
            "name": "g1",
            "color": "#000000",
            "project_id": project_id,
        }
        search_filter_group = self.post(path, filter_group_1)
        result = self.get(path)
        self.assertTrue("asset" in result)

        self.delete("%s/%s" % (path, search_filter_group["id"]))
        result = self.get(path)
        self.assertFalse("asset" in result)

    def test_get_filters(self):
        project_id = str(self.project.id)
        path = "data/user/filters/"
        filter_1 = {
            "list_type": "asset",
            "name": "props",
            "query": "props",
            "project_id": project_id,
        }
        filter_2 = {
            "list_type": "shot",
            "name": "se01",
            "query": "se01",
            "project_id": project_id,
        }
        filter_3 = {
            "list_type": "all",
            "name": "wfa",
            "query": "wfa",
            "project_id": project_id,
        }
        self.post(path, filter_1)
        self.post(path, filter_2)
        self.post(path, filter_3)

        result = self.get(path)
        self.assertTrue("asset" in result)
        self.assertTrue("shot" in result)
        self.assertTrue("all" in result)
        self.assertEqual(len(result["asset"][project_id]), 1)
        self.assertEqual(len(result["shot"][project_id]), 1)
        self.assertEqual(len(result["all"][project_id]), 1)
        self.assertEqual(result["all"][project_id][0]["search_query"], "wfa")
        self.assertEqual(
            result["asset"][project_id][0]["search_query"], "props"
        )
        self.assertEqual(result["shot"][project_id][0]["search_query"], "se01")

    def test_update_filter(self):
        project_id = str(self.project.id)
        path = "data/user/filters"
        filter_1 = {
            "list_type": "asset",
            "name": "props",
            "query": "props",
            "project_id": project_id,
        }
        search_filter = self.post(path, filter_1)
        result = self.get(path)
        self.assertTrue("asset" in result)
        self.put("%s/%s" % (path, search_filter["id"]), {"name": "updated"})
        result = self.get("data/search-filters/%s" % search_filter["id"])
        self.assertEqual(result["name"], "updated")

    def test_remove_filter(self):
        project_id = str(self.project.id)
        path = "data/user/filters"
        filter_1 = {
            "list_type": "asset",
            "name": "props",
            "query": "props",
            "project_id": project_id,
        }
        search_filter = self.post(path, filter_1)
        result = self.get(path)
        self.assertTrue("asset" in result)

        self.delete("%s/%s" % (path, search_filter["id"]))

        result = self.get(path)
        self.assertFalse("asset" in result)

    def test_add_logs(self):
        path = "/data/user/desktop-login-logs"

        date_1 = self.now()
        data = {"date": date_1}
        logs = self.get(path)
        self.assertEqual(len(logs), 0)

        self.post(path, data)
        date_2 = self.now()
        data = {"date": date_2}
        self.post(path, data)

        logs = self.get(path)
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["person_id"], str(self.user_id))
        self.assertEqual(logs[0]["date"], date_2)

    def test_get_notifications(self):
        person_id = str(self.person.id)
        tasks_service.assign_task(self.task.id, self.user_id)
        self.task_dict = self.task.serialize(relations=True)
        self.generate_fixture_comment()
        notifications_service.create_notifications_for_task_and_comment(
            self.task_dict, self.comment
        )
        path = "/data/user/notifications"
        notifications = self.get(path)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["author_id"], person_id)

    def test_get_notification(self):
        tasks_service.assign_task(self.task.id, self.user_id)
        self.generate_fixture_comment()
        self.task_dict = self.task.serialize(relations=True)
        notifications_service.create_notifications_for_task_and_comment(
            self.task_dict, self.comment
        )
        path = "/data/user/notifications"
        notifications = self.get(path)
        notification = notifications[0]
        path = "/data/user/notifications/%s" % notification["id"]
        notification_again = self.get(path)
        self.assertEqual(notification_again["id"], notification["id"])
        self.assertEqual(
            notification_again["full_entity_name"], "Props / Tree"
        )

    def test_subscribe_task(self):
        recipients = notifications_service.get_notification_recipients(
            self.task_dict
        )
        self.assertFalse(self.user_id in recipients)

        self.post(
            "/actions/user/tasks/%s/subscribe" % self.task_dict["id"], {}
        )
        recipients = notifications_service.get_notification_recipients(
            self.task_dict
        )
        self.assertTrue(self.user_id in recipients)

    def test_unsubscribe_task(self):
        self.post(
            "/actions/user/tasks/%s/subscribe" % self.task_dict["id"], {}
        )
        self.delete(
            "/actions/user/tasks/%s/unsubscribe" % self.task_dict["id"]
        )
        recipients = notifications_service.get_notification_recipients(
            self.task_dict
        )
        self.assertFalse(self.user_id in recipients)

    def test_subscribe_sequence(self):
        recipients = notifications_service.get_notification_recipients(
            self.shot_task_dict
        )
        self.assertFalse(self.user_id in recipients)

        path = "/actions/user/sequences/%s/task-types/%s/subscribe" % (
            self.sequence_dict["id"],
            self.task_type_dict["id"],
        )
        self.post(path, {})

        recipients = notifications_service.get_notification_recipients(
            self.shot_task_dict
        )
        self.assertTrue(self.user_id in recipients)

    def test_unsubscribe_sequence(self):
        path = "/actions/user/sequences/%s/task-types/%s/" % (
            self.sequence_dict["id"],
            self.task_type_dict["id"],
        )
        self.post(path + "subscribe", {})
        self.delete(path + "unsubscribe")
        recipients = notifications_service.get_notification_recipients(
            self.shot_task_dict
        )
        self.assertFalse(self.user_id in recipients)

    def test_get_context(self):
        context = self.get("/data/user/context")
        self.assertEqual(len(context["projects"]), 1)
        self.assertEqual(len(context["asset_types"]), 1)
        self.assertEqual(len(context["departments"]), 2)
        self.assertEqual(len(context["task_types"]), 6)
        self.assertEqual(len(context["task_status"]), 3)
        self.assertEqual(len(context["project_status"]), 2)
        self.assertEqual(len(context["persons"]), 3)
        self.assertEqual(context["notification_count"], 0)
        self.assertEqual(len(context["search_filters"]), 0)
        self.assertEqual(len(context["custom_actions"]), 0)

    def test_get_metadata_columns(self):
        projects_service.add_metadata_descriptor(
            self.project_id, "asset", "test client", "string", [], True
        )
        projects_service.add_metadata_descriptor(
            self.project_id, "asset", "test", "string", [], False
        )
        self.generate_fixture_user_client()
        self.log_in_client()
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        context = self.get("/data/user/context")
        self.assertEqual(len(context["projects"]), 1)
        self.assertEqual(len(context["projects"][0]["descriptors"]), 1)
        self.assertEqual(
            context["projects"][0]["descriptors"][0]["name"], "test client"
        )

    def test_shared_filters(self):
        project_id = str(self.project.id)
        self.generate_fixture_user_cg_artist()

        # Create a filter for artist
        self.log_in_cg_artist()
        path = "data/user/filters/"
        filter_1 = {
            "list_type": "asset",
            "name": "my filter",
            "query": "props",
            "project_id": project_id,
            "is_shared": True,
        }
        self.post(path, filter_1)

        # Admin cannot see artist's filter
        self.log_in_admin()
        result = self.get(path)
        self.assertEqual(result, {})

        # Add artist to the project and a department
        self.log_in_admin()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        artist = persons_service.get_person_raw(self.user_cg_artist["id"])
        artist.departments.append(self.department)
        artist.save()

        # Create a shared filter
        filter_2 = {
            "list_type": "asset",
            "name": "team filter",
            "query": "character",
            "project_id": project_id,
            "is_shared": True,
        }
        filter_2 = self.post(path, filter_2)

        # Artist can see their filters and the shared filters
        self.log_in_cg_artist()
        result = self.get(path)
        self.assertEqual(len(result["asset"][project_id]), 2)
        self.assertEqual(result["asset"][project_id][0]["name"], "my filter")
        self.assertEqual(result["asset"][project_id][0]["is_shared"], False)
        self.assertEqual(result["asset"][project_id][1]["name"], "team filter")
        self.assertEqual(result["asset"][project_id][1]["is_shared"], True)

        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()

        # Admin can update filter
        self.log_in_admin()
        self.put(
            "data/user/filters/%s" % filter_2["id"],
            {"name": "team updated"},
        )
        result = self.get(path)
        user_service.clear_filter_cache()
        self.assertEqual(
            result["asset"][project_id][0]["name"], "team updated"
        )
        self.assertEqual(result["asset"][project_id][0]["is_shared"], True)

        # Artist cannot update admin's filter
        self.log_in_cg_artist()
        self.put(
            "data/user/filters/%s" % result["asset"][project_id][0]["id"],
            {"name": "updated", "is_shared": True},
            404,
        )

        # Admin can create a shared filter for a department
        self.log_in_admin()
        filter_3 = {
            "list_type": "asset",
            "name": "department filter",
            "query": "character",
            "project_id": project_id,
            "is_shared": True,
            "department_id": self.department_animation.id,
        }
        filter_3 = self.post(path, filter_3)
        result = self.get(path)
        user_service.clear_filter_cache()
        self.assertEqual(len(result["asset"][project_id]), 2)

        # Artist can't see the department filter
        # because he is not in the department.
        self.log_in_cg_artist()
        result = self.get(path)
        user_service.clear_filter_cache()
        self.assertEqual(len(result["asset"][project_id]), 2)
        self.assertEqual(result["asset"][project_id][0]["name"], "my filter")
        self.assertEqual(
            result["asset"][project_id][1]["name"], "team updated"
        )

        # Filter is shared with the artist's department
        self.log_in_admin()
        self.put(
            "data/user/filters/%s" % filter_3["id"],
            {
                "name": "department updated",
                "is_shared": True,
                "department_id": self.department.id,
            },
        )
        result = self.get(path)
        user_service.clear_filter_cache()
        self.assertEqual(len(result["asset"][project_id]), 2)
        self.assertEqual(
            result["asset"][project_id][0]["name"], "team updated"
        )
        self.assertEqual(
            result["asset"][project_id][1]["name"], "department updated"
        )

        # Now artist can see the department filter
        self.log_in_cg_artist()
        user_service.clear_filter_cache()
        result = self.get(path)
        self.assertEqual(len(result["asset"][project_id]), 3)
        self.assertEqual(
            result["asset"][project_id][2]["name"], "department updated"
        )
        self.assertEqual(
            result["asset"][project_id][1]["name"], "team updated"
        )
        self.assertEqual(result["asset"][project_id][0]["name"], "my filter")

    def test_shared_group_filters(self):
        project_id = str(self.project.id)
        self.generate_fixture_user_cg_artist()

        # Create a filter group for artist
        self.log_in_cg_artist()
        path = "data/user/filter-groups/"
        filter_group_1 = {
            "list_type": "asset",
            "project_id": project_id,
            "is_shared": False,
            "name": "my group",
            "color": "",
        }
        self.post(path, filter_group_1)

        # Admin cannot see artist's filter group
        self.log_in_admin()
        result = self.get(path)
        self.assertEqual(result, {})

        # Artist can see their filter groups
        self.log_in_cg_artist()
        result = self.get(path)
        self.assertEqual(len(result["asset"][project_id]), 1)
        self.assertEqual(result["asset"][project_id][0]["name"], "my group")
        self.assertEqual(result["asset"][project_id][0]["is_shared"], False)

        # Add artist to the project and a department
        self.log_in_admin()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        artist = persons_service.get_person_raw(self.user_cg_artist["id"])
        artist.departments.append(self.department)
        artist.save()

        # Create a shared filter group
        filter_group_2 = {
            "list_type": "asset",
            "project_id": project_id,
            "is_shared": True,
            "name": "team group",
            "color": "",
        }
        self.post(path, filter_group_2)

        # Artist can see their groups and the shared groups
        self.log_in_cg_artist()
        result = self.get(path)
        self.assertEqual(len(result["asset"][project_id]), 2)
        self.assertEqual(result["asset"][project_id][0]["name"], "team group")
        self.assertEqual(result["asset"][project_id][0]["is_shared"], True)
        self.assertEqual(result["asset"][project_id][1]["name"], "my group")
        self.assertEqual(result["asset"][project_id][1]["is_shared"], False)

        # Admin can update filter group
        self.log_in_admin()
        self.put(
            "data/user/filter-groups/%s"
            % result["asset"][project_id][0]["id"],
            {"name": "updated"},
        )
        result = self.get(path)
        user_service.clear_filter_group_cache()
        self.assertEqual(result["asset"][project_id][0]["name"], "updated")
        self.assertEqual(result["asset"][project_id][0]["is_shared"], True)

        # Artist cannot update admin's filter group
        self.log_in_cg_artist()
        self.put(
            "data/user/filter-groups/%s"
            % result["asset"][project_id][0]["id"],
            {"name": "updated", "is_shared": True},
            404,
        )

        # Admin can create a shared filter group for a department
        self.log_in_admin()
        filter_group_3 = {
            "list_type": "asset",
            "project_id": project_id,
            "is_shared": True,
            "name": "department group",
            "color": "",
            "department_id": self.department_animation.id,
        }
        filter_group_3 = self.post(path, filter_group_3)
        result = self.get(path)
        user_service.clear_filter_group_cache()
        self.assertEqual(len(result["asset"][project_id]), 2)

        # Artist can't see the department filter group
        # because he is not in the department.
        self.log_in_cg_artist()
        result = self.get(path)
        user_service.clear_filter_group_cache()
        self.assertEqual(len(result["asset"][project_id]), 2)
        self.assertEqual(result["asset"][project_id][0]["name"], "updated")
        self.assertEqual(result["asset"][project_id][1]["name"], "my group")

        # Filter group is shared with the artist's department
        self.log_in_admin()
        self.put(
            "data/user/filter-groups/%s" % filter_group_3["id"],
            {
                "name": "department updated",
                "is_shared": True,
                "department_id": self.department.id,
            },
        )
        user_service.clear_filter_group_cache()
        result = self.get(path)
        self.assertEqual(len(result["asset"][project_id]), 2)
        self.assertEqual(
            result["asset"][project_id][0]["name"], "department updated"
        )
        self.assertEqual(result["asset"][project_id][1]["name"], "updated")

        # Now artist can see the department filter group
        self.log_in_cg_artist()
        user_service.clear_filter_group_cache()
        result = self.get(path)
        self.assertEqual(len(result["asset"][project_id]), 3)
        self.assertEqual(
            result["asset"][project_id][0]["name"], "department updated"
        )
        self.assertEqual(result["asset"][project_id][1]["name"], "updated")
        self.assertEqual(result["asset"][project_id][2]["name"], "my group")

    def create_test_folder(self):
        return super().create_test_folder()
