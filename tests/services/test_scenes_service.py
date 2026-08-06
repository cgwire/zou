from tests.base import ApiDBTestCase

from zou.app.services import scenes_service, shots_service


class SceneUtilsTestCase(ApiDBTestCase):
    """
    A scene is the source of the shots cut out of it. Linking is writing
    that source onto the shot, and the listing reads it back, so a shot of
    another scene or of none at all is not in it.
    """

    def setUp(self):
        super().setUp()

        self.first_scene = self.generate_fixture_scene().serialize()
        self.shot_01 = self.generate_fixture_shot().serialize()
        self.shot_02 = self.generate_fixture_shot("S02").serialize()

    def test_add_shot_to_scene(self):
        shot = scenes_service.add_shot_to_scene(self.first_scene, self.shot_01)

        self.assertEqual(shot["source_id"], self.first_scene["id"])
        self.assertEqual(
            shots_service.get_shot(self.shot_01["id"])["source_id"],
            self.first_scene["id"],
        )

    def test_add_shot_to_scene_announces_the_link(self):
        captured = self.capture_events("shot:add-to-scene")

        scenes_service.add_shot_to_scene(self.first_scene, self.shot_01)

        self.assertEqual(len(captured), 1)
        self.assertEqual(
            (
                captured[0]["scene_id"],
                captured[0]["shot_id"],
                captured[0]["project_id"],
            ),
            (
                self.first_scene["id"],
                self.shot_01["id"],
                self.shot_01["project_id"],
            ),
        )

    def test_remove_shot_from_scene(self):
        scenes_service.add_shot_to_scene(self.first_scene, self.shot_01)

        shot = scenes_service.remove_shot_from_scene(
            self.first_scene, self.shot_01
        )

        self.assertIsNone(shot["source_id"])

    def test_remove_shot_from_scene_announces_the_break(self):
        scenes_service.add_shot_to_scene(self.first_scene, self.shot_01)
        captured = self.capture_events("shot:remove-from-scene")

        scenes_service.remove_shot_from_scene(self.first_scene, self.shot_01)

        self.assertEqual(len(captured), 1)
        self.assertEqual(
            (captured[0]["scene_id"], captured[0]["shot_id"]),
            (self.first_scene["id"], self.shot_01["id"]),
        )

    def test_get_shots_by_scene(self):
        self.generate_fixture_scene("SC02")
        other_scene = self.scene.serialize()
        elsewhere = self.generate_fixture_shot("S03").serialize()
        scenes_service.add_shot_to_scene(self.first_scene, self.shot_01)
        scenes_service.add_shot_to_scene(self.first_scene, self.shot_02)
        scenes_service.add_shot_to_scene(other_scene, elsewhere)

        shots = scenes_service.get_shots_by_scene(self.first_scene["id"])

        # The third shot belongs to the other scene, and nothing here is
        # left unlinked by accident.
        self.assertEqual(
            sorted(shot["id"] for shot in shots),
            sorted([self.shot_01["id"], self.shot_02["id"]]),
        )

    def test_a_shot_taken_out_leaves_the_listing(self):
        scenes_service.add_shot_to_scene(self.first_scene, self.shot_01)
        scenes_service.add_shot_to_scene(self.first_scene, self.shot_02)

        scenes_service.remove_shot_from_scene(self.first_scene, self.shot_01)

        shots = scenes_service.get_shots_by_scene(self.first_scene["id"])
        self.assertEqual([shot["id"] for shot in shots], [self.shot_02["id"]])
