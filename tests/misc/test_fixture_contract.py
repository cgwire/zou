from tests.base import ApiDBTestCase


class FixtureRepointingTestCase(ApiDBTestCase):
    """
    The fixture generators repoint the attribute they name. It is what lets
    a test build a second shot and keep using self.shot, and it is also the
    trap that turns "two shots" into the same shot twice.

    Pinned here because it is the assumption every test file makes without
    saying so, and because the docstring of ApiDBTestCase promises it.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

    def test_the_default_call_returns_what_is_already_there(self):
        first = self.shot
        self.assertEqual(self.generate_fixture_shot().id, first.id)
        self.assertEqual(self.shot.id, first.id)

    def test_a_named_call_builds_a_row_and_takes_over_the_attribute(self):
        first = self.shot

        second = self.generate_fixture_shot("Z01")

        self.assertNotEqual(second.id, first.id)
        self.assertEqual(self.shot.id, second.id)

    def test_the_fixtures_that_follow_land_on_the_new_row(self):
        """
        The consequence that costs the time: a task asked for after a second
        shot hangs from that second shot, not from the one the test still
        calls self.shot in its head.
        """
        first = self.shot
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()

        self.generate_fixture_shot("Z01")
        task = self.generate_fixture_shot_task(name="after")

        self.assertNotEqual(str(task.entity_id), str(first.id))
        self.assertEqual(str(task.entity_id), str(self.shot.id))
