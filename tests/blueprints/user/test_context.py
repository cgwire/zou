import orjson as json

from tests.base import ApiDBTestCase

from zou.app.services import (
    tasks_service,
    notifications_service,
    persons_service,
    projects_service,
)

from zou.app.models.project import Project
from zou.app.models.person import Person


class UserContextRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
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
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_to_review()

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
        sequences = self.get(f"data/user/projects/{self.project.id}/sequences")
        self.assertEqual(len(sequences), 1)

    def test_get_project_episodes(self):
        self.assign_user(self.shot_task.id)
        episodes = self.get(f"data/user/projects/{self.project.id}/episodes")
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["name"], "E01")
        self.assertEqual(episodes[0]["type"], "Episode")

    def test_get_sequence_shots(self):
        self.assign_user(self.shot_task.id)
        shots = self.get(f"data/user/sequences/{self.sequence.id}/shots")
        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["type"], "Shot")
        self.assertEqual(shots[0]["name"], "P01")

    def test_get_sequence_scenes(self):
        self.generate_fixture_scene()
        self.generate_fixture_scene_task()
        self.assign_user(self.scene_task.id)
        scenes = self.get(f"data/user/sequences/{self.sequence.id}/scenes")
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
            f"data/user/projects/{self.project.id}/asset-types"
        )
        self.assertEqual(len(asset_types), 0)

        self.assign_user(task_id)
        self.assign_user(task2_id)
        self.assign_user(task3_id)
        self.assign_user(shot_task_id)
        asset_types = self.get(
            f"data/user/projects/{self.project.id}/asset-types"
        )
        self.assertEqual(len(asset_types), 2)

    def test_get_project_asset_types_assets(self):
        task_id = self.task.id
        assets = self.get(
            f"data/user/projects/{self.project.id}/asset-types/{self.asset_type.id}/assets"
        )
        self.assertEqual(len(assets), 0)
        self.assign_user(task_id)

        assets = self.get(
            f"data/user/projects/{self.project.id}/asset-types/{self.asset_type.id}/assets"
        )
        self.assertEqual(len(assets), 1)

    def test_get_asset_tasks(self):
        path = f"data/user/assets/{self.asset.id}/tasks"
        task_id = self.task.id

        tasks = self.get(path)
        self.assertEqual(len(tasks), 0)

        self.assign_user(task_id)
        tasks = self.get(path)
        self.assertEqual(len(tasks), 1)

    def test_get_shot_tasks(self):
        path = f"data/user/shots/{self.shot.id}/tasks"
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
        path = f"data/user/scenes/{self.scene.id}/tasks"

        tasks = self.get(path)
        self.assertEqual(len(tasks), 0)

        self.assign_user(scene_task_id)
        tasks = self.get(path)
        self.assertEqual(len(tasks), 1)

    def test_get_sequence_tasks(self):
        sequence_task = self.generate_fixture_task(
            "sequence task", self.sequence.id
        )
        path = f"data/user/sequences/{self.sequence.id}/tasks"

        self.assertEqual(len(self.get(path)), 0)

        self.assign_user(sequence_task.id)
        tasks = self.get(path)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(sequence_task.id))

    def test_get_sequence_task_types(self):
        sequence_task = self.generate_fixture_task(
            "sequence task", self.sequence.id
        )
        path = f"data/user/sequences/{self.sequence.id}/task-types"

        self.assertEqual(len(self.get(path)), 0)

        self.assign_user(sequence_task.id)
        task_types = self.get(path)
        self.assertEqual(len(task_types), 1)
        self.assertEqual(task_types[0]["id"], str(sequence_task.task_type_id))

    def test_get_asset_task_types(self):
        path = f"data/user/assets/{self.asset.id}/task-types"
        task_id = self.task.id
        task_type_id = self.task_type.id

        task_types = self.get(path)
        self.assertEqual(len(task_types), 0)

        self.assign_user(task_id)
        task_types = self.get(path)
        self.assertEqual(len(task_types), 1)
        self.assertEqual(task_types[0]["id"], str(task_type_id))

    def test_get_shot_task_types(self):
        path = f"data/user/shots/{self.shot.id}/task-types"
        shot_task_id = self.shot_task.id

        task_types = self.get(path)
        self.assertEqual(len(task_types), 0)

        self.assign_user(shot_task_id)
        task_types = self.get(path)
        self.assertEqual(len(task_types), 1)

    def test_get_scene_task_types(self):
        self.generate_fixture_scene()
        self.generate_fixture_scene_task()
        path = f"data/user/scenes/{self.scene.id}/task-types"
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

    def test_get_todos_bearer_only(self):
        # Regression for issue #1059: /data/user/tasks must work with a
        # bare JWT Bearer header, without any Flask-Principal session
        # cookie. Reproduces a script-style call (curl / gazu) where the
        # decorator ordering used to make permissions.require_person
        # raise 403 before jwt_required() had loaded the identity.
        self.assign_user(self.task.id)

        bearer_client = self.flask_app.test_client()
        headers = dict(self.base_headers)
        response = bearer_client.get("data/user/tasks", headers=headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(json.loads(response.data.decode("utf-8"))), 1)

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
        self.put(f"{path}/{search_filter_group['id']}", {"name": "updated"})
        result = self.get(
            f"data/search-filter-groups/{search_filter_group['id']}"
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

        self.delete(f"{path}/{search_filter_group['id']}")
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
        self.put(f"{path}/{search_filter['id']}", {"name": "updated"})
        result = self.get(f"data/search-filters/{search_filter['id']}")
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

        self.delete(f"{path}/{search_filter['id']}")

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
        path = f"/data/user/notifications/{notification['id']}"
        notification_again = self.get(path)
        self.assertEqual(notification_again["id"], notification["id"])
        self.assertEqual(
            notification_again["full_entity_name"], "Props / Tree"
        )

    def test_mark_all_notifications_as_read(self):
        tasks_service.assign_task(self.task.id, self.user_id)
        self.generate_fixture_comment()
        notifications_service.create_notifications_for_task_and_comment(
            self.task.serialize(relations=True), self.comment
        )
        self.assertFalse(self.get("/data/user/notifications")[0]["read"])

        self.post("/actions/user/notifications/mark-all-as-read", {}, 200)

        self.assertTrue(self.get("/data/user/notifications")[0]["read"])

    def test_clear_avatar(self):
        persons_service.update_person(self.user_id, {"has_avatar": True})
        self.assertTrue(persons_service.get_person(self.user_id)["has_avatar"])

        self.delete("/actions/user/clear-avatar")

        self.assertFalse(
            persons_service.get_person(self.user_id)["has_avatar"]
        )

    def test_subscribe_task(self):
        recipients = notifications_service.get_notification_recipients(
            self.task_dict
        )
        self.assertFalse(self.user_id in recipients)

        self.post(f"/actions/user/tasks/{self.task_dict['id']}/subscribe", {})
        recipients = notifications_service.get_notification_recipients(
            self.task_dict
        )
        self.assertTrue(self.user_id in recipients)

    def test_unsubscribe_task(self):
        self.post(f"/actions/user/tasks/{self.task_dict['id']}/subscribe", {})
        self.delete(f"/actions/user/tasks/{self.task_dict['id']}/unsubscribe")
        recipients = notifications_service.get_notification_recipients(
            self.task_dict
        )
        self.assertFalse(self.user_id in recipients)

    def test_subscribe_sequence(self):
        recipients = notifications_service.get_notification_recipients(
            self.shot_task_dict
        )
        self.assertFalse(self.user_id in recipients)

        path = f'/actions/user/sequences/{self.sequence_dict["id"]}/task-types/{self.task_type_dict["id"]}/subscribe'
        self.post(path, {})

        recipients = notifications_service.get_notification_recipients(
            self.shot_task_dict
        )
        self.assertTrue(self.user_id in recipients)

        subscribed_path = (
            f'/data/user/sequences/{self.sequence_dict["id"]}'
            f'/task-types/{self.task_type_dict["id"]}/subscribed'
        )
        self.assertTrue(self.get(subscribed_path))
        deprecated_path = (
            f'/data/user/entities/{self.sequence_dict["id"]}'
            f'/task-types/{self.task_type_dict["id"]}/subscribed'
        )
        self.assertTrue(self.get(deprecated_path))

        listing_path = (
            f"/data/user/projects/{self.project_id}"
            f'/task-types/{self.task_type_dict["id"]}/sequence-subscriptions'
        )
        self.assertEqual(self.get(listing_path), [self.sequence_dict["id"]])

    def test_unsubscribe_sequence(self):
        path = f'/actions/user/sequences/{self.sequence_dict["id"]}/task-types/{self.task_type_dict["id"]}/'
        self.post(path + "subscribe", {})
        self.delete(path + "unsubscribe")
        recipients = notifications_service.get_notification_recipients(
            self.shot_task_dict
        )
        self.assertFalse(self.user_id in recipients)

    def test_get_tasks_to_check(self):
        tasks = self.get("data/user/tasks-to-check")
        self.assertEqual(len(tasks), 0)

        feedback_status = tasks_service.get_or_create_status(
            "Waiting For Approval", "wfa", is_feedback_request=True
        )
        tasks_service.update_task(
            self.task_id, {"task_status_id": feedback_status["id"]}
        )

        tasks = self.get("data/user/tasks-to-check")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(self.task_id))

    def test_get_day_off(self):
        path = "data/user/day-offs/2026-08-05"
        self.assertEqual(self.get(path), {})

        self.generate_fixture_day_off("2026-08-05", person_id=self.user_id)

        day_off = self.get(path)
        self.assertEqual(day_off["person_id"], self.user_id)
        # A date the driver cannot cast is a 400, not a 500.
        self.get("data/user/day-offs/not-a-date", 400)

    def test_get_time_spents_for_date(self):
        path = "data/user/time-spents/2026-08-05"
        self.assertEqual(len(self.get(path)), 0)

        tasks_service.create_or_update_time_spent(
            self.task_id, self.user_id, "2026-08-05", 3600
        )

        time_spents = self.get(path)
        self.assertEqual(len(time_spents), 1)
        self.assertEqual(time_spents[0]["duration"], 3600)
        # Another day sees nothing.
        self.assertEqual(len(self.get("data/user/time-spents/2026-08-06")), 0)
        self.get("data/user/time-spents/not-a-date", 400)

    def test_get_task_time_spent_for_date(self):
        path = f"data/user/tasks/{self.task_id}/time-spents/2026-08-05"
        tasks_service.create_or_update_time_spent(
            self.task_id, self.user_id, "2026-08-05", 3600
        )

        time_spent = self.get(path)
        self.assertEqual(time_spent["duration"], 3600)
        self.assertEqual(time_spent["task_id"], str(self.task_id))
        self.get(f"data/user/tasks/{self.task_id}/time-spents/nope", 400)

    def test_get_time_spents_range(self):
        tasks_service.create_or_update_time_spent(
            self.task_id, self.user_id, "2026-08-05", 3600
        )
        time_spents = self.get(
            "data/user/time-spents?start_date=2026-08-01&end_date=2026-08-31"
        )
        self.assertEqual(len(time_spents), 1)
        # Both bounds are required, one alone is a 400.
        self.get("data/user/time-spents?start_date=2026-08-01", 400)

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

    def test_context_excludes_guests(self):
        """
        Guests created by the shared playlist flow must not show up
        in /data/user/context — they are not part of the studio team.
        """
        Person.create(
            first_name="Reviewer",
            last_name="One",
            email="guest-1@guest.kitsu",
            role="client",
            is_guest=True,
        )
        regular_count_before = len(persons_service.get_persons())

        context = self.get("/data/user/context")
        person_ids = [p["id"] for p in context["persons"]]
        self.assertEqual(len(person_ids), regular_count_before)
        self.assertFalse(
            any(
                p.get("is_guest")
                for p in context["persons"]
                if "is_guest" in p
            ),
            "context.persons leaked an is_guest=True person",
        )

    def create_test_folder(self):
        return super().create_test_folder()


class UserContextProjectRolesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.user_id = self.user["id"]
        projects_service.add_team_member(str(self.project.id), self.user_id)

    def test_context_exposes_explicit_project_roles(self):
        projects_service.update_team_member_role(
            str(self.project.id), self.user_id, "supervisor"
        )
        context = self.get("data/user/context")
        self.assertEqual(
            context["project_roles"],
            {str(self.project.id): "supervisor"},
        )

    def test_context_project_roles_empty_when_inherited(self):
        context = self.get("data/user/context")
        self.assertEqual(context["project_roles"], {})
