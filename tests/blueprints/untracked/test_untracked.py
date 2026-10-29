from tests.base import ApiDBTestCase
from zou.app.models.entity import Entity
from zou.app.models.department import Department
from zou.app.models.task_type import TaskType
from zou.app.services import projects_service, untracked_service


class UntrackedRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_shot_suite()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.project_id = str(self.project.id)
        self.path = f"/data/projects/{self.project_id}/untracked"
        self.sound_design = TaskType.create(
            name="Sound Design",
            short_name="snd",
            color="#FFFFFF",
            for_entity="Untracked",
            department_id=self.department.id,
        )
        self.sound_design_id = str(self.sound_design.id)
        projects_service.add_task_type_setting(
            self.project_id, self.sound_design_id
        )

    def create_untracked(self, name="Sound design", parent_id=None):
        return untracked_service.create_untracked(
            self.project_id, name, parent_id=parent_id
        )

    def test_create_untracked(self):
        untracked = self.post(self.path, {"name": "Sound design"})
        self.assertEqual(untracked["name"], "Sound design")
        self.assertEqual(untracked["project_id"], self.project_id)
        self.assertEqual(untracked["type"], "Untracked")
        self.assertIsNone(untracked["parent_id"])
        self.assertEqual(untracked["created_by"], self.user["id"])

    def test_create_untracked_twice(self):
        untracked = self.post(self.path, {"name": "Sound design"})
        same = self.post(self.path, {"name": "Sound design"})
        self.assertEqual(untracked["id"], same["id"])
        self.assertEqual(len(self.get(self.path)), 1)

    def test_create_untracked_without_name(self):
        self.post(self.path, {"name": ""}, 400)

    def test_create_untracked_linked(self):
        for parent in (self.episode, self.sequence, self.shot):
            untracked = self.post(
                self.path, {"name": "Layout plan", "parent_id": str(parent.id)}
            )
            self.assertEqual(untracked["parent_id"], str(parent.id))

    def test_create_untracked_linked_to_an_asset(self):
        self.post(
            self.path,
            {"name": "Sound design", "parent_id": str(self.asset.id)},
            400,
        )

    def test_create_untracked_linked_to_another_project(self):
        other_project = self.generate_fixture_project("Other project")
        other_sequence = Entity.create(
            name="S99",
            project_id=other_project.id,
            entity_type_id=self.sequence_type.id,
        )
        self.post(
            self.path,
            {"name": "Sound design", "parent_id": str(other_sequence.id)},
            400,
        )

    def test_get_untracked_with_episode(self):
        self.create_untracked("Unlinked")
        self.create_untracked("On shot", parent_id=str(self.shot.id))
        items = {item["name"]: item for item in self.get(self.path)}
        self.assertIsNone(items["Unlinked"]["episode_id"])
        self.assertIsNone(items["Unlinked"]["link_name"])
        self.assertEqual(items["On shot"]["episode_id"], str(self.episode.id))
        self.assertEqual(
            items["On shot"]["link_name"],
            f"{self.episode.name} / {self.sequence.name} / {self.shot.name}",
        )

    def test_update_untracked_link(self):
        untracked = self.create_untracked()
        path = f"/data/untracked/{untracked['id']}"
        updated = self.put(path, {"parent_id": str(self.sequence.id)})
        self.assertEqual(updated["parent_id"], str(self.sequence.id))
        updated = self.put(path, {"name": "Foley"})
        self.assertEqual(updated["name"], "Foley")
        self.assertEqual(updated["parent_id"], str(self.sequence.id))
        updated = self.put(path, {"parent_id": None})
        self.assertIsNone(updated["parent_id"])
        self.put(path, {"parent_id": str(self.asset.id)}, 400)

    def test_untracked_stays_out_of_the_assets(self):
        untracked = self.create_untracked()
        asset_ids = {asset["id"] for asset in self.get("data/assets/all")}
        self.assertNotIn(untracked["id"], asset_ids)
        self.assertIn(str(self.asset.id), asset_ids)
        asset_type_names = {
            asset_type["name"] for asset_type in self.get("data/asset-types")
        }
        self.assertNotIn("Untracked", asset_type_names)
        self.assertEqual(
            self.get(f"data/entities/{untracked['id']}")["id"],
            untracked["id"],
        )

    def test_create_untracked_tasks(self):
        untracked = self.create_untracked()
        tasks = self.post(
            f"data/entities/{untracked['id']}/tasks",
            {"task_type_ids": [self.sound_design_id]},
        )
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_type_id"], self.sound_design_id)
        self.assertEqual(tasks[0]["entity_id"], untracked["id"])

    def test_untracked_task_type_refused_for_a_shot(self):
        self.post(
            f"data/entities/{self.shot.id}/tasks",
            {"task_type_ids": [self.sound_design_id]},
            400,
        )

    def test_untracked_in_schedule(self):
        # generate_fixture_episode() moves self.episode to the new one.
        episode_id = str(self.episode.id)
        unlinked = self.create_untracked("Unlinked")
        linked = self.create_untracked("On shot", parent_id=str(self.shot.id))
        other_episode = self.generate_fixture_episode(name="E02")
        elsewhere = self.create_untracked(
            "Elsewhere", parent_id=str(other_episode.id)
        )
        for untracked in (unlinked, linked, elsewhere):
            self.post(
                f"data/entities/{untracked['id']}/tasks",
                {"task_type_ids": [self.sound_design_id]},
            )

        task_type_items = self.get(
            f"/data/projects/{self.project_id}/schedule-items/task-types"
        )
        self.assertIn(
            self.sound_design_id,
            [item["task_type_id"] for item in task_type_items],
        )

        base_path = (
            f"/data/projects/{self.project_id}/schedule-items/"
            f"{self.sound_design_id}/untracked"
        )
        items = self.get(base_path)
        self.assertEqual(
            [item["name"] for item in items],
            ["Elsewhere", "On shot", "Unlinked"],
        )
        items = self.get(f"{base_path}?episode_id={episode_id}")
        self.assertEqual(
            {item["object_id"] for item in items},
            {unlinked["id"], linked["id"]},
        )

    def test_untracked_in_schedule_under_its_task_type_only(self):
        sound = self.create_untracked("Sound design")
        music = self.create_untracked("Music")
        self.post(
            f"data/entities/{sound['id']}/tasks",
            {"task_type_ids": [self.sound_design_id]},
        )
        self.post(
            f"/data/projects/{self.project_id}/untracked",
            {"name": "Music", "create_task": True},
        )
        items = self.get(
            f"/data/projects/{self.project_id}/schedule-items/"
            f"{self.sound_design_id}/untracked"
        )
        self.assertEqual([item["object_id"] for item in items], [sound["id"]])
        self.assertNotIn(music["id"], [item["object_id"] for item in items])

    def task_type_of(self, untracked):
        return self.get(
            f"data/task-types/{untracked['tasks'][0]['task_type_id']}"
        )

    def test_create_untracked_with_its_task(self):
        sound = Department.create(name="Sound", color="#123456")
        untracked = self.post(
            self.path,
            {
                "name": "Sounddesign",
                "create_task": True,
                "department_id": str(sound.id),
            },
        )
        self.assertEqual(len(untracked["tasks"]), 1)
        # the row of the schedule carries the name of the item
        task_type = self.task_type_of(untracked)
        self.assertEqual(task_type["name"], "Sounddesign")
        self.assertEqual(task_type["for_entity"], "Untracked")
        self.assertEqual(task_type["department_id"], str(sound.id))
        self.assertEqual(task_type["color"], "#123456")
        project = self.get(f"data/projects/{self.project_id}")
        self.assertIn(task_type["id"], project["task_types"])

    def test_create_untracked_task_without_department(self):
        untracked = self.post(self.path, {"name": "Mix", "create_task": True})
        task_type = self.task_type_of(untracked)
        self.assertEqual(task_type["name"], "Mix")
        self.assertIsNone(task_type["department_id"])
        self.assertIn(task_type["color"], untracked_service.COLORS)

    def test_create_untracked_task_with_a_colour(self):
        sound = Department.create(name="Sound", color="#123456")
        untracked = self.post(
            self.path,
            {
                "name": "Foley",
                "create_task": True,
                "department_id": str(sound.id),
                "color": "#F06292",
            },
        )
        # the chosen colour wins over the one of the department
        self.assertEqual(self.task_type_of(untracked)["color"], "#F06292")
        # a reused task type keeps its colour: the rows of the other
        # productions use it too
        other_project = self.generate_fixture_project("Other project")
        other = self.post(
            f"/data/projects/{other_project.id}/untracked",
            {
                "name": "Foley",
                "create_task": True,
                "department_id": str(sound.id),
                "color": "#1976D2",
            },
        )
        self.assertEqual(self.task_type_of(other)["color"], "#F06292")

    def test_create_untracked_with_its_task_twice(self):
        untracked = self.post(self.path, {"name": "Mix", "create_task": True})
        same = self.post(self.path, {"name": "Mix", "create_task": True})
        self.assertEqual(same["id"], untracked["id"])
        self.assertEqual(len(same["tasks"]), 1)
        self.assertEqual(same["tasks"][0]["id"], untracked["tasks"][0]["id"])

    def test_rename_untracked_moves_its_task(self):
        sound = Department.create(name="Sound", color="#123456")
        untracked = self.post(
            self.path,
            {
                "name": "Foley",
                "create_task": True,
                "department_id": str(sound.id),
                "color": "#F06292",
            },
        )
        former_type = self.task_type_of(untracked)
        self.put(f"data/untracked/{untracked['id']}", {"name": "Ambience"})
        task = self.get(f"data/tasks/{untracked['tasks'][0]['id']}")
        task_type = self.get(f"data/task-types/{task['task_type_id']}")
        self.assertEqual(task_type["name"], "Ambience")
        self.assertEqual(task_type["department_id"], str(sound.id))
        self.assertEqual(task_type["color"], "#F06292")
        project = self.get(f"data/projects/{self.project_id}")
        self.assertIn(task_type["id"], project["task_types"])
        # the former task type stays, for the other productions
        self.get(f"data/task-types/{former_type['id']}")

    def test_delete_linked_shot_and_sequence(self):
        on_shot = self.create_untracked("Foley", parent_id=str(self.shot.id))
        on_sequence = self.create_untracked(
            "Music", parent_id=str(self.sequence.id)
        )
        self.delete(f"data/shots/{self.shot.id}?force=true")
        self.delete(f"data/sequences/{self.sequence.id}?force=true")
        self.assertIsNone(
            self.get(f"data/untracked/{on_shot['id']}")["parent_id"]
        )
        self.assertIsNone(
            self.get(f"data/untracked/{on_sequence['id']}")["parent_id"]
        )

    def test_create_untracked_task_with_a_wrong_colour(self):
        self.post(
            self.path,
            {"name": "Foley", "create_task": True, "color": "red"},
            400,
        )

    def test_untracked_items_of_the_same_name_share_their_task_type(self):
        other_project = self.generate_fixture_project("Other project")
        mix = self.post(self.path, {"name": "Mix", "create_task": True})
        other_mix = self.post(
            f"/data/projects/{other_project.id}/untracked",
            {"name": "mix", "create_task": True},
        )
        self.assertEqual(
            self.task_type_of(other_mix)["id"], self.task_type_of(mix)["id"]
        )
        music = self.post(self.path, {"name": "Music", "create_task": True})
        self.assertNotEqual(
            self.task_type_of(music)["id"], self.task_type_of(mix)["id"]
        )

    def test_create_untracked_task_with_a_taken_name(self):
        TaskType.create(name="Modeling", for_entity="Asset")
        modeling = self.post(
            self.path, {"name": "Modeling", "create_task": True}
        )
        self.assertEqual(
            self.task_type_of(modeling)["name"], "Modeling (untracked)"
        )
        TaskType.create(name="Layout", for_entity="Shot")
        layout = self.post(
            self.path,
            {
                "name": "Layout",
                "create_task": True,
                "department_id": str(self.department_animation.id),
            },
        )
        self.assertEqual(
            self.task_type_of(layout)["name"], "Layout (Animation)"
        )

    def test_create_untracked_without_task(self):
        untracked = self.post(self.path, {"name": "Mix"})
        self.assertNotIn("tasks", untracked)

    def test_untracked_permissions(self):
        untracked = self.create_untracked()
        self.generate_fixture_user_cg_artist()
        self.generate_fixture_user_vendor()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        projects_service.add_team_member(
            self.project_id, self.user_vendor["id"]
        )

        self.log_in_cg_artist()
        self.assertEqual(len(self.get(self.path)), 1)
        self.post(self.path, {"name": "Music"}, 403)
        self.put(f"/data/untracked/{untracked['id']}", {"name": "Music"}, 403)

        self.log_in_vendor()
        self.get(self.path, 403)
        self.get(f"/data/untracked/{untracked['id']}", 403)
