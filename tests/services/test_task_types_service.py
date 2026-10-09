from tests.base import ApiDBTestCase

from zou.app.models.studio import Studio
from zou.app.models.task_type import TaskType
from zou.app.services import departments_service, task_types_service
from zou.app.utils import fields
from zou.app.exceptions import StudioNotFoundException
from tests.services.cases import TaskTestCase


class TaskReaderTestCase(TaskTestCase):
    def test_get_studio(self):
        studio = Studio.create(name="Blue Spirit", color="#000000")

        self.assertEqual(
            task_types_service.get_studio(studio.id)["name"], "Blue Spirit"
        )
        self.assertRaises(
            StudioNotFoundException,
            task_types_service.get_studio,
            fields.gen_uuid(),
        )


class GetOrCreateTaskTypeTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.department = departments_service.get_or_create_department(
            "Concept", "#8D6E63"
        )

    def test_create_when_missing(self):
        task_type = task_types_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1
        )
        self.assertIsNotNone(task_type["id"])
        self.assertEqual(task_type["for_entity"], "Asset")

    def test_return_existing_with_same_name_and_entity(self):
        first = task_types_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1
        )
        second = task_types_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1
        )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(TaskType.get_all_by(name="Concept")), 1)

    def test_return_existing_with_a_name_differing_only_by_case(self):
        """
        The bootstrap follows the same rule as the API: a name differing
        only by case is the same task type, and the existing row keeps
        its name.
        """
        first = task_types_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1
        )
        second = task_types_service.get_or_create_task_type(
            self.department, "CONCEPT", "#8D6E63", 1
        )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["name"], "Concept")
        self.assertEqual(TaskType.get_all_by(name="CONCEPT"), [])

    def test_same_name_different_for_entity_coexist(self):
        asset_type = task_types_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1
        )
        concept_type = task_types_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1, for_entity="Concept"
        )
        self.assertNotEqual(asset_type["id"], concept_type["id"])
        self.assertEqual(asset_type["for_entity"], "Asset")
        self.assertEqual(concept_type["for_entity"], "Concept")
        self.assertEqual(len(TaskType.get_all_by(name="Concept")), 2)

    def test_a_new_task_type_joins_the_listing(self):
        task_types_service.get_task_types()

        task_type = task_types_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1
        )

        self.assertIn(
            task_type["id"],
            [listed["id"] for listed in task_types_service.get_task_types()],
        )


class TaskStatusTestCase(ApiDBTestCase):
    """
    The statuses a studio works with. get_or_create_task_status names them by
    short name, so asking for a second long name of an existing short one
    returns the first.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_task_status()
        # Named WIP with short name wip, which is what makes the second
        # test below get it back under a different long name.
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_to_review()

    def test_get_status(self):
        task_status = task_types_service.get_or_create_task_status(
            "WIP", "wip", is_wip=True
        )
        self.assertEqual(task_status["name"], "WIP")

    def test_get_wip_status(self):
        task_status = task_types_service.get_or_create_task_status(
            "Work In Progress", "wip", "#3273dc", is_wip=True
        )
        self.assertEqual(task_status["name"], "WIP")

    def test_get_done_status(self):
        task_status = task_types_service.get_or_create_task_status(
            "Done", "done", "#22d160", is_done=True
        )
        self.assertEqual(task_status["name"], "Done")

    def test_get_todo_status(self):
        task_status = task_types_service.get_default_task_status()
        self.assertEqual(task_status["is_default"], True)

    def test_get_to_review_status(self):
        task_status = task_types_service.get_to_review_status()
        self.assertEqual(task_status["name"], "To review")

    def test_a_new_status_joins_the_listing(self):
        # The listing is memoized and feeds the status dropdowns of every
        # client, so a status created outside the CRUD route has to drop it
        # too.
        task_types_service.get_task_statuses()

        task_status = task_types_service.get_or_create_task_status(
            "Omitted", "omt", "#22d160"
        )

        self.assertIn(
            task_status["id"],
            [
                listed["id"]
                for listed in task_types_service.get_task_statuses()
            ],
        )
