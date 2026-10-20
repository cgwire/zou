from tests.base import ApiDBTestCase, rebuild_from_compact
from zou.app.models.entity import Entity
from zou.app.models.task import Task
from zou.app.services import (
    metadata_descriptors_service,
    persons_service,
    projects_service,
    shots_service,
    tasks_service,
)


class ShotTasksTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task()
        self.generate_fixture_metadata_descriptor(entity_type="Shot")
        self.person_id = str(self.person.id)
        self.shot_id = str(self.shot.id)
        self.meta_descriptor_id = self.meta_descriptor.id
        self.department_id = self.department.id

    def test_get_tasks_for_shot(self):
        tasks = self.get(f"data/shots/{self.shot_id}/tasks")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(self.shot_task.id))

    def test_get_shots_and_tasks(self):
        self.generate_fixture_shot_task(name="Secondary")
        shots = self.get("data/shots/with-tasks")
        self.assertEqual(len(shots), 1)
        self.assertEqual(len(shots[0]["tasks"]), 2)
        self.assertEqual(shots[0]["tasks"][0]["assignees"][0], self.person_id)
        self.assertEqual(shots[0]["episode_name"], "E01")
        self.assertEqual(shots[0]["sequence_name"], "S01")

    def test_get_shots_and_tasks_include_task_data(self):
        self.shot_task.update({"data": {"render_layer": "bg"}})
        shots = self.get("data/shots/with-tasks")
        self.assertEqual(shots[0]["tasks"][0]["data"], {"render_layer": "bg"})

    def test_get_shots_and_tasks_compact(self):
        self.generate_fixture_shot_task(name="Secondary")
        reference = self.get("data/shots/with-tasks")
        payload = self.get("data/shots/with-tasks?compact=true")
        self.assertTrue(payload["compact"])
        rebuilt = rebuild_from_compact(
            payload["shot_fields"], payload["task_fields"], payload["rows"]
        )
        self.assertEqual(rebuilt, reference)

    def test_get_shots_and_tasks_stream(self):
        self.generate_fixture_shot_task(name="Secondary")
        reference = self.get("data/shots/with-tasks")

        header, rows = self.get_ndjson("data/shots/with-tasks?stream=true")

        self.assertFalse(header["compact"])
        self.assertEqual(rows, reference)

    def test_get_shots_and_tasks_stream_compact(self):
        self.generate_fixture_shot_task(name="Secondary")
        reference = self.get("data/shots/with-tasks")

        header, rows = self.get_ndjson(
            "data/shots/with-tasks?stream=true&compact=true"
        )

        self.assertTrue(header["compact"])
        rebuilt = rebuild_from_compact(
            header["shot_fields"], header["task_fields"], rows
        )
        self.assertEqual(rebuilt, reference)

    def test_get_shots_and_tasks_vendor(self):
        self.generate_fixture_shot_task(name="Secondary")
        self.generate_fixture_user_vendor()
        task_id = self.shot_task.id
        project_id = self.project.id
        person_id = self.user_vendor["id"]
        self.log_in_vendor()
        shots = self.get(f"data/shots/with-tasks?project_id={project_id}", 403)
        projects_service.add_team_member(project_id, person_id)
        shots = self.get(f"data/shots/with-tasks?project_id={project_id}")
        self.assertEqual(shots, [])
        tasks_service.assign_task(task_id, person_id)
        shots = self.get(f"data/shots/with-tasks?project_id={project_id}")
        self.assertEqual(len(shots), 1)
        self.assertEqual(len(shots[0]["tasks"]), 1)
        self.assertIn(str(person_id), shots[0]["tasks"][0]["assignees"])

        shots_service.update_shot(
            self.shot_id, {"data": {"contractor": "test"}}
        )
        shots = self.get(f"data/shots/with-tasks?project_id={project_id}")
        self.assertEqual(shots[0]["data"]["contractor"], "test")

        metadata_descriptors_service.update_metadata_descriptor(
            self.meta_descriptor_id, {"departments": [self.department_id]}
        )
        persons_service.add_to_department(str(self.department_id), person_id)
        shots = self.get(f"data/shots/with-tasks?project_id={project_id}")
        self.assertEqual(shots[0]["data"]["contractor"], "test")

        persons_service.remove_from_department(
            str(self.department_id), person_id
        )
        shots = self.get(f"data/shots/with-tasks?project_id={project_id}")
        self.assertNotIn("contractor", shots[0]["data"])

        # The listings without the tasks answer the same production, so they
        # hide the same descriptor.
        for path in ["data/shots", "data/shots/all"]:
            with self.subTest(path=path):
                shots = self.get(f"{path}?project_id={project_id}")
                self.assertNotIn("contractor", shots[0]["data"])

    def test_get_task_types_for_shot(self):
        task_types = self.get(f"/data/shots/{self.shot_id}/task-types")
        self.assertEqual(len(task_types), 1)
        self.assertDictEqual(
            task_types[0], self.task_type_animation.serialize()
        )

    def test_get_shots_and_tasks_all_episodes(self):
        project_id = str(self.project.id)
        shots = self.get(
            f"data/shots/with-tasks?project_id={project_id}&episode_id=all"
        )
        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["episode_name"], "E01")

    def test_get_sequences_and_tasks_all_episodes_as_vendor(self):
        project_id = str(self.project.id)
        self.generate_fixture_user_vendor()
        vendor_id = self.user_vendor["id"]
        projects_service.add_team_member(project_id, vendor_id)
        tasks_service.assign_task(str(self.shot_task.id), vendor_id)
        self.log_in_vendor()
        sequences = self.get(
            f"data/sequences/with-tasks?project_id={project_id}&episode_id=all"
        )
        self.assertEqual(len(sequences), 1)
        self.assertEqual(sequences[0]["name"], "S01")


class WithTasksPaginationTestCase(ApiDBTestCase):
    """
    Opt-in pagination of the shot, sequence, episode and scene boards:
    walking the pages yields the very entity dicts of the full list,
    nested tasks included, for a studio member as for a vendor.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.project_id = str(self.project.id)
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_user_vendor()
        self.vendor_id = self.user_vendor["id"]
        projects_service.add_team_member(self.project_id, self.vendor_id)
        shots = []
        sequences = []
        sequence_tasks = []
        for index in range(1, 4):
            episode = self.generate_fixture_episode(f"E0{index}")
            self.add_tasks(episode)
            sequence = self.generate_fixture_sequence(
                f"S0{index}", episode_id=episode.id
            )
            sequences.append(sequence)
            sequence_tasks.append(self.add_tasks(sequence))
            self.add_tasks(self.generate_fixture_scene(f"SC0{index}"))
            shots.append(self.generate_fixture_shot(f"P0{index}"))
        shots.append(
            self.generate_fixture_shot("P04", sequence_id=sequences[0].id)
        )
        self.shot_tasks = [self.add_tasks(shot) for shot in shots]
        for shot_tasks in [self.shot_tasks[0], self.shot_tasks[2]]:
            tasks_service.assign_task(str(shot_tasks[0].id), self.vendor_id)
        tasks_service.assign_task(str(sequence_tasks[0][0].id), self.vendor_id)

    def add_tasks(self, entity):
        return [
            Task.create(
                name=name,
                project_id=self.project.id,
                task_type_id=self.task_type_animation.id,
                task_status_id=self.task_status.id,
                entity_id=entity.id,
                assignees=[self.person],
                assigner_id=self.assigner.id,
            )
            for name in [f"{entity.name} main", f"{entity.name} extra"]
        ]

    def board_paths(self, entity_types):
        return [
            f"data/{entity_type}/with-tasks?project_id={self.project_id}"
            for entity_type in entity_types
        ]

    def test_boards_page_like_their_full_list(self):
        for path in self.board_paths(
            ["shots", "sequences", "episodes", "scenes"]
        ):
            with self.subTest(path=path):
                self.assert_opt_in_pagination(path)
                full = self.assert_pages_match_full_list(path, ordered=False)
                self.assertGreaterEqual(len(full), 3)
                self.assertTrue(all(row["tasks"] for row in full))
                self.assert_pages_match_full_list(path, limit=2, ordered=False)

    def test_boards_page_like_their_full_list_for_a_vendor(self):
        self.log_in_vendor()
        for path in self.board_paths(["shots", "sequences", "episodes"]):
            with self.subTest(path=path):
                self.assert_opt_in_pagination(path)
                full = self.assert_pages_match_full_list(path, ordered=False)
                self.assertEqual(len(full), 2)

    def test_a_vendor_board_page_is_masked(self):
        """
        The metadata of departments a vendor does not belong to stays
        hidden in a page of the sequence and episode boards too.
        """
        self.generate_fixture_department()
        field_names = {}
        for entity_type, entity_type_path in [
            ("Sequence", "sequences"),
            ("Episode", "episodes"),
        ]:
            descriptor = metadata_descriptors_service.add_metadata_descriptor(
                self.project_id,
                entity_type,
                "Rig",
                "string",
                [],
                False,
                [str(self.department_animation.id)],
            )
            field_name = descriptor["field_name"]
            field_names[entity_type_path] = field_name
            for entity in Entity.get_all_by(
                project_id=self.project.id,
                entity_type_id=getattr(self, f"{entity_type.lower()}_type").id,
            ):
                entity.update({"data": {field_name: "secret"}})
        self.assertEqual(
            self.get_first(f"{self.board_paths(['sequences'])[0]}")["data"],
            {field_names["sequences"]: "secret"},
        )
        self.log_in_vendor()
        for path in self.board_paths(["sequences", "episodes"]):
            entity_type_path = path.split("/")[1]
            with self.subTest(path=path):
                page = self.get(f"{path}&page=1&limit=10")
                self.assertGreaterEqual(page["total"], 1)
                for row in page["data"]:
                    self.assertNotIn(
                        field_names[entity_type_path], row["data"] or {}
                    )

    def test_paginated_board_honors_compact_and_ignores_stream(self):
        path = f"{self.board_paths(['shots'])[0]}&page=1&limit=2"
        page = self.get(path)
        self.assertNotIn("compact", page)
        self.assertEqual(len(page["data"]), 2)
        self.assertEqual(page["total"], 4)
        self.assertEqual(self.get(f"{path}&stream=true"), page)
        compact = self.get(f"{path}&compact=true")
        self.assertEqual(self.get(f"{path}&compact=true&stream=true"), compact)
        self.assertTrue(compact["compact"])
        self.assertEqual(
            compact["shot_fields"], shots_service.SHOTS_AND_TASKS_SHOT_FIELDS
        )
        self.assertEqual(
            {key: value for key, value in compact.items() if key != "data"},
            {
                **{key: value for key, value in page.items() if key != "data"},
                "compact": True,
                "shot_fields": shots_service.SHOTS_AND_TASKS_SHOT_FIELDS,
                "task_fields": shots_service.SHOTS_AND_TASKS_TASK_FIELDS,
            },
        )
        rebuilt = rebuild_from_compact(
            compact["shot_fields"], compact["task_fields"], compact["data"]
        )
        self.assertEqual(rebuilt, page["data"])


class EntityTaskListsPaginationTestCase(ApiDBTestCase):
    """
    Opt-in pagination of the task lists of a shot, a sequence, an episode
    and a scene, and of the shot and asset tasks of a sequence or an
    episode: walking the pages yields the very task dicts of the full list.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_user_vendor()
        self.vendor_id = self.user_vendor["id"]
        projects_service.add_team_member(str(self.project.id), self.vendor_id)
        self.episode = self.generate_fixture_episode()
        self.sequence = self.generate_fixture_sequence(
            episode_id=self.episode.id
        )
        # Each fixture call replaces the attribute it sets: keep the
        # entities aside.
        other_shot = self.generate_fixture_shot(
            "P02", sequence_id=self.sequence.id
        )
        shot = self.generate_fixture_shot(sequence_id=self.sequence.id)
        self.scene = self.generate_fixture_scene(sequence_id=self.sequence.id)
        assets = [
            self.generate_fixture_asset(name, description=name)
            for name in ["Rock", "Tree"]
        ]
        for asset in assets:
            asset.update({"source_id": self.episode.id})
        for entity in [
            self.episode,
            self.sequence,
            shot,
            other_shot,
            self.scene,
            *assets,
        ]:
            self.add_tasks(entity)
        for task in self.add_tasks(self.sequence, prefix="vendor"):
            tasks_service.assign_task(str(task.id), self.vendor_id)
        for task in self.add_tasks(self.episode, prefix="vendor"):
            tasks_service.assign_task(str(task.id), self.vendor_id)

    def add_tasks(self, entity, prefix="task"):
        return [
            Task.create(
                name=f"{prefix} {index}",
                project_id=self.project.id,
                task_type_id=self.task_type_animation.id,
                task_status_id=self.task_status.id,
                entity_id=entity.id,
                assignees=[self.person],
                assigner_id=self.assigner.id,
            )
            for index in [3, 1, 2]
        ]

    def test_entity_task_lists_page_like_their_full_list(self):
        for path in [
            f"data/shots/{self.shot.id}/tasks",
            f"data/shots/{self.shot.id}/tasks?relations=true",
            f"data/sequences/{self.sequence.id}/tasks",
            f"data/episodes/{self.episode.id}/tasks",
            f"data/scenes/{self.scene.id}/tasks",
            f"data/sequences/{self.sequence.id}/shot-tasks",
            f"data/episodes/{self.episode.id}/shot-tasks",
            f"data/episodes/{self.episode.id}/asset-tasks",
            f"data/episodes/{self.episode.id}/asset-tasks?relations=true",
        ]:
            with self.subTest(path=path):
                self.assert_opt_in_pagination(path)
                full = self.assert_pages_match_full_list(
                    path, limit=2, ordered=False
                )
                self.assertGreaterEqual(len(full), 3)

    def test_entity_task_lists_page_for_a_vendor(self):
        self.log_in_vendor()
        for path in [
            f"data/sequences/{self.sequence.id}/tasks",
            f"data/episodes/{self.episode.id}/tasks",
        ]:
            with self.subTest(path=path):
                self.assert_opt_in_pagination(path)
                full = self.assert_pages_match_full_list(
                    path, limit=2, ordered=False
                )
                self.assertEqual(len(full), 3)
