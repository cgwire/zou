from tests.blueprints.source.shotgun.base import ShotgunTestCase
from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.services import entity_types_service


class ImportShotgunSequence(ShotgunTestCase):
    def setUp(self):
        super().setUp()

    def test_import_sequences(self):
        self.load_fixture("projects")
        self.sequences = self.load_fixture("sequences")
        self.assertEqual(len(self.sequences), 3)

        self.sequences = self.get("data/sequences")
        self.assertEqual(len(self.sequences), 3)

    def test_import_sequences_twice(self):
        self.load_fixture("projects")
        self.sequences = self.load_fixture("sequences")
        self.sequences = self.load_fixture("sequences")
        self.assertEqual(len(self.sequences), 3)

        self.sequences = self.get("data/sequences")
        self.assertEqual(len(self.sequences), 3)

    def test_import_sequence(self):
        self.load_fixture("projects")
        self.load_fixture("episodes")
        sg_sequence = {
            "project": {"type": "Project", "id": 1, "name": "Agent327"},
            "episode": {"type": "Episode", "id": 1, "name": "E01"},
            "code": "S04",
            "type": "Sequence",
            "id": 4,
            "description": "test description",
        }
        api_path = "/import/shotgun/sequences"
        self.sequences = self.post(api_path, [sg_sequence], 200)
        self.assertEqual(len(self.sequences), 1)

        self.sequences = self.get("data/sequences")
        self.assertEqual(len(self.sequences), 1)

        sequence = self.sequences[0]
        project = Project.get_by(name="Agent327")
        episode = Entity.get_by(name="E01")
        self.assertEqual(sequence["name"], sg_sequence["code"])
        self.assertEqual(sequence["description"], sg_sequence["description"])
        self.assertEqual(sequence["shotgun_id"], sg_sequence["id"])
        self.assertEqual(sequence["project_id"], str(project.id))
        self.assertEqual(sequence["parent_id"], str(episode.id))

    def test_import_sequence_without_episode(self):
        self.load_fixture("projects")
        project = Project.get_by(name="Agent327")
        Entity.create(
            name="E01",
            project_id=project.id,
            entity_type_id=entity_types_service.get_episode_type()["id"],
        )
        sg_sequence = {
            "project": {"type": "Project", "id": 1, "name": "Agent327"},
            "code": "S04",
            "type": "Sequence",
            "id": 4,
            "description": "test description",
        }
        api_path = "/import/shotgun/sequences"
        self.post(api_path, [sg_sequence], 200)

        sequence = self.get("data/sequences")[0]
        self.assertIsNone(sequence["parent_id"])

    def test_remove_sequence_with_shots(self):
        self.load_fixture("projects")
        self.load_fixture("sequences")
        self.load_fixture("shots")
        sequence = Entity.get_by(
            shotgun_id=1,
            entity_type_id=entity_types_service.get_sequence_type()["id"],
        )

        sequence_id = sequence.id
        self.spare_fixtures_from_rollbacks()

        api_path = "/import/shotgun/remove/sequence"
        result = self.post(api_path, {"id": 1}, 200)
        self.assertFalse(result["success"])
        self.assertIsNotNone(Entity.get(sequence_id))
