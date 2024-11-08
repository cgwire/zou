from tests.base import ApiDBTestCase

from zou.app.services import projects_service, tasks_service


class SequenceTestCase(ApiDBTestCase):
    def setUp(self):
        super(SequenceTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_assigner()
        self.generate_fixture_person()

        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.serialized_sequence = self.sequence.serialize(obj_type="Sequence")
        self.sequence_id = self.serialized_sequence["id"]
        sequence_02 = self.generate_fixture_sequence("SE02")
        self.sequence_02_id = str(sequence_02.id)
        self.generate_fixture_sequence("SE03")

    def test_get_sequences(self):
        sequences = self.get("data/sequences")
        self.assertEqual(len(sequences), 3)
        self.assertDictEqual(sequences[0], self.serialized_sequence)

    def test_get_sequence(self):
        sequence = self.get("data/sequences/%s" % self.sequence.id)
        self.assertEqual(sequence["id"], str(self.sequence.id))
        self.assertEqual(sequence["name"], self.sequence.name)
        self.assertEqual(sequence["episode_name"], self.episode.name)
        self.assertEqual(sequence["episode_id"], str(self.episode.id))
        self.assertEqual(sequence["project_name"], self.project.name)

    def test_get_sequence_by_name(self):
        sequences = self.get(
            "data/sequences?name=%s" % self.sequence.name.lower()
        )
        self.assertEqual(sequences[0]["id"], str(self.sequence.id))

    def test_get_sequence_tasks(self):
        self.generate_fixture_sequence_task()
        tasks = self.get("data/sequences/%s/tasks" % self.sequence.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(self.sequence_task.id))

    def test_create_sequence(self):
        self.generate_fixture_episode()
        sequence_name = "NSE01"
        project_id = str(self.project.id)
        episode_id = str(self.episode.id)
        data = {"name": sequence_name, "episode_id": episode_id}
        sequence = self.post("data/projects/%s/sequences" % project_id, data)
        sequence = self.get("data/sequences/%s" % sequence["id"])
        self.assertEqual(sequence["name"], sequence_name)
        self.assertEqual(sequence["parent_id"], episode_id)

    def test_get_sequences_for_project(self):
        sequences = self.get("data/projects/%s/sequences" % self.project.id)
        self.assertEqual(len(sequences), 3)
        self.assertDictEqual(sequences[0], self.serialized_sequence)

    def test_get_sequences_for_project_with_vendor(self):
        self.generate_fixture_shot_task(name="Secondary")
        self.generate_fixture_user_vendor()
        task_id = self.shot_task.id
        project_id = self.project_id
        person_id = self.user_vendor["id"]
        projects_service.clear_project_cache(str(project_id))
        self.log_in_vendor()
        projects_service.add_team_member(project_id, person_id)
        episodes = self.get("data/projects/%s/sequences" % project_id)
        self.assertEqual(len(episodes), 0)
        tasks_service.assign_task(task_id, person_id)
        episodes = self.get("data/projects/%s/sequences" % project_id)
        self.assertEqual(len(episodes), 1)

    def test_get_sequences_for_project_404(self):
        self.get("data/projects/unknown/sequences", 404)

    def test_get_shots_for_sequence(self):
        self.generate_fixture_shot()
        shot = self.shot.serialize(obj_type="Shot")
        shots = self.get("data/sequences/%s/shots" % self.sequence.id)
        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["id"], shot["id"])

    def test_get_sequences_by_project_and_name(self):
        self.get("data/sequences?project_id=undefined&name=S01", 400)
        sequences = self.get(
            "data/sequences?project_id=%s&name=SE02" % self.project_id
        )
        self.assertEqual(sequences[0]["id"], str(self.sequence_02_id))

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        sequences = self.get(
            "data/sequences?project_id=%s&name=SE01" % self.project_id, 403
        )

    def test_force_delete_sequence(self):
        self.get("data/sequences/%s" % self.sequence_id)
        self.delete("data/sequences/%s?force=true" % self.sequence_id)
        self.get("data/sequences/%s" % self.sequence_id, 404)

    def test_cant_delete_sequence(self):
        self.get("data/sequences/%s" % self.sequence_id)
        self.delete("data/sequences/%s" % self.sequence_id, 400)
