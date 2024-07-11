from tests.base import ApiDBTestCase

from zou.app.services import projects_service, shots_service, tasks_service


class ShotTestCase(ApiDBTestCase):
    def setUp(self):
        super(ShotTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.project_id = str(self.project.id)
        self.generate_fixture_asset_type()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot("SH01")
        self.shot_dict = self.shot.serialize(obj_type="Shot")
        self.shot_dict["project_name"] = self.project.name
        self.shot_dict["sequence_name"] = self.sequence.name
        self.serialized_shot = self.shot.serialize(obj_type="Shot")
        self.shot_id = str(self.shot.id)
        self.shot_01 = self.shot
        self.serialized_sequence = self.sequence.serialize(obj_type="Sequence")
        self.serialized_episode = self.episode.serialize(obj_type="Episode")
        self.serialized_project = self.project.serialize()

        shot_02 = self.generate_fixture_shot("SH02")
        self.shot_02 = shot_02
        self.shot_02_id = str(shot_02.id)
        self.shot_03 = self.generate_fixture_shot("SH03")
        self.generate_fixture_asset()

        self.generate_fixture_project_standard()

    def test_get_shots(self):
        shots = self.get("data/shots/all")
        self.assertEqual(len(shots), 3)
        self.assertDictEqual(shots[0], self.shot_dict)

    def test_remove_shot(self):
        self.generate_fixture_asset()
        path = "data/shots/%s" % self.shot.id
        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 3)
        self.delete(path)
        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 2)

    def test_get_shot(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task()

        shot = self.get("data/shots/%s" % self.shot.id)
        self.assertEqual(shot["id"], str(self.shot.id))
        self.assertEqual(shot["name"], self.shot.name)
        self.assertEqual(
            shot["sequence_name"], self.serialized_sequence["name"]
        )
        self.assertEqual(shot["sequence_id"], self.serialized_sequence["id"])
        self.assertEqual(shot["episode_name"], self.serialized_episode["name"])
        self.assertEqual(shot["episode_id"], self.serialized_episode["id"])
        self.assertEqual(shot["project_name"], self.serialized_project["name"])
        self.assertEqual(len(shot["tasks"]), 1)

    def test_get_shot_by_name(self):
        shots = self.get("data/shots/all?name=%s" % self.shot.name.lower())
        self.assertEqual(shots[0]["id"], str(self.shot.id))

    def test_get_shot_by_name_with_vendor(self):
        shot_name = self.shot.name.lower()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task()
        self.generate_fixture_user_vendor()
        sequence_id = str(self.sequence.id)
        project_id = str(self.shot_task.project_id)
        task_id = str(self.shot_task.id)
        shot_id = str(self.shot.id)
        vendor_id = str(self.user_vendor["id"])
        self.log_in_vendor()
        self.get(
            "data/shots?sequence_id=%s&name=%s" % (sequence_id, shot_name), 403
        )
        projects_service.add_team_member(project_id, vendor_id)
        shots = self.get(
            "data/shots?sequence_id=%s&name=%s" % (sequence_id, shot_name)
        )
        self.assertEqual(len(shots), 0)
        tasks_service.assign_task(task_id, vendor_id)
        shots = self.get(
            "data/shots?sequence_id=%s&name=%s" % (sequence_id, shot_name)
        )
        self.assertEqual(shots[0]["id"], shot_id)

    def test_remove_shot_with_tasks(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task()

        path = "data/shots/%s" % self.shot.id
        self.delete(path)
        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 3)
        self.assertEqual(shots[2]["canceled"], True)

    def test_create_shot(self):
        shot_name = "NSH01"
        project_id = str(self.project.id)
        sequence_id = str(self.sequence.id)
        data = {
            "name": shot_name,
            "sequence_id": sequence_id,
            "data": {"frame_in": 10, "frame_out": 20},
        }
        shot = self.post("data/projects/%s/shots" % project_id, data)
        shot = self.get("data/shots/%s" % shot["id"])
        self.assertEqual(shot["name"], shot_name)
        self.assertEqual(shot["sequence_id"], sequence_id)
        self.assertDictEqual(shot["data"], data["data"])

    def test_get_shots_for_project(self):
        self.generate_fixture_sequence_standard()
        self.generate_fixture_shot_standard("SH01")
        self.generate_fixture_shot_standard("SH02")
        shots = self.get("data/projects/%s/shots" % self.project.id)
        self.assertEqual(len(shots), 3)
        self.assertDictEqual(shots[0], self.serialized_shot)

    def test_get_shots_for_project_404(self):
        self.get("data/projects/unknown/shots", 404)

    def test_get_shots_by_project_and_name(self):
        self.get("data/shots/all?project_id=undefined&name=SH01", 400)
        shots = self.get(
            "data/shots/all?project_id=%s&name=SH02" % self.project_id
        )
        self.assertEqual(shots[0]["id"], str(self.shot_02_id))

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        shots = self.get(
            "data/shots/all?project_id=%s&name=SH01" % self.project_id, 403
        )

    def test_set_frames_from_task_type_previews(self):
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        project_id = str(self.project.id)
        task_type = self.task_type_animation
        task_type_id = str(task_type.id)
        self.shot = self.shot_01
        self.shot_02.delete()
        self.shot_03.delete()

        (
            episode_01,
            episode_02,
            sequence_01,
            sequence_02,
            shot_01,
            shot_02,
            shot_03,
            shot_e201,
            task_shot_01,
            task_shot_02,
            task_shot_03,
            task_shot_e201,
            preview_01,
            preview_02,
            preview_03,
            preview_e201,
        ) = self.generate_fixture_shot_tasks_and_previews(task_type_id)

        self.post(
            "actions/projects/%s/task-types/%s/set-shot-nb-frames?episode_id=%s"
            % ("wrong-id", task_type_id, str(episode_01.id)),
            {},
            400,
        )
        self.post(
            "actions/projects/%s/task-types/%s/set-shot-nb-frames?episode_id=%s"
            % (project_id, "wrong-id", str(episode_01.id)),
            {},
            400,
        )

        self.post(
            "actions/projects/%s/task-types/%s/set-shot-nb-frames?episode_id=%s"
            % (project_id, task_type_id, "wrong-id"),
            {},
            400,
        )
        self.post(
            "actions/projects/%s/task-types/%s/set-shot-nb-frames?episode_id=%s"
            % (project_id, task_type_id, str(episode_01.id)),
            {},
            200,
        )
        shot_01 = shots_service.get_shot(shot_01.id)
        shot_02 = shots_service.get_shot(shot_02.id)
        shot_03 = shots_service.get_shot(shot_03.id)
        shot_e201 = shots_service.get_shot(shot_e201.id)
        self.assertEqual(shot_01["nb_frames"], 750)
        self.assertEqual(shot_02["nb_frames"], 500)
        self.assertEqual(shot_03["nb_frames"], 250)
        self.assertEqual(shot_e201["nb_frames"], 0)

        self.post(
            "actions/projects/%s/task-types/%s/set-shot-nb-frames?episode_id="
            % (
                project_id,
                task_type_id,
            ),
            {},
            200,
        )
        shot_e201 = shots_service.get_shot(shot_e201["id"])
        self.assertEqual(shot_e201["nb_frames"], 1000)
