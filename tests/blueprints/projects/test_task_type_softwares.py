from tests.base import ApiDBTestCase
from zou.app.models.department import Department
from zou.app.models.project import ProjectTaskTypeSoftwareLink
from zou.app.services import (
    cascade_deletion_service,
    persons_service,
    projects_service,
)
from zou.app.utils import events


class TaskTypeSoftwaresTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_task_type()
        self.generate_fixture_software()
        self.project_id = str(self.project.id)
        self.task_type_id = str(self.task_type.id)
        self.software_id = str(self.software.id)
        projects_service.add_task_type_setting(
            self.project_id, self.task_type_id
        )
        self.list_path = f"data/projects/{self.project_id}/task-type-softwares"
        self.path = (
            f"data/projects/{self.project_id}"
            f"/task-types/{self.task_type_id}/softwares"
        )
        self.link = {
            "project_id": self.project_id,
            "task_type_id": self.task_type_id,
            "software_id": self.software_id,
        }
        self.events = []
        events.register("project:update", "handle_event", self)

    def handle_event(self, data={}):
        self.events.append(data)

    def add_link(self, code=201):
        return self.post(self.path, {"software_id": self.software_id}, code)

    def join_team(self, person):
        projects_service.add_team_member(self.project_id, person["id"])

    def test_add_software_to_task_type(self):
        self.assertEqual(self.add_link(), self.link)
        self.assertEqual(self.get(self.list_path), [self.link])
        self.assertEqual(len(self.events), 1)

    def test_add_software_twice_returns_the_existing_link(self):
        self.add_link()
        self.assertEqual(self.add_link(), self.link)
        self.assertEqual(len(self.get(self.list_path)), 1)

    def test_add_software_refuses_a_task_type_outside_the_project(self):
        path = (
            f"data/projects/{self.project_id}"
            f"/task-types/{self.task_type_modeling.id}/softwares"
        )
        self.post(path, {"software_id": self.software_id}, 400)

    def test_add_software_refuses_an_archived_software(self):
        self.software.update({"archived": True})
        self.add_link(400)

    def test_add_software_refuses_an_unknown_software(self):
        self.post(
            self.path,
            {"software_id": "5b0b9f5b-ff5d-4b4f-9a2e-0f0d0e2c1a11"},
            404,
        )
        self.post(self.path, {}, 400)

    def test_remove_software_from_task_type(self):
        self.add_link()
        self.delete(f"{self.path}/{self.software_id}")
        self.assertEqual(self.get(self.list_path), [])
        self.assertEqual(len(self.events), 2)

    def test_remove_returns_the_deleted_link(self):
        self.add_link()
        args = (self.project_id, self.task_type_id, self.software_id)
        removed = projects_service.remove_task_type_software(*args)
        self.assertEqual(removed, self.link)
        self.assertIsNone(projects_service.remove_task_type_software(*args))

    def test_the_list_is_scoped_to_the_project(self):
        self.add_link()
        self.generate_fixture_project_standard()
        path = f"data/projects/{self.project_standard.id}/task-type-softwares"
        self.assertEqual(self.get(path), [])

    def test_an_artist_of_the_team_reads_but_cannot_write(self):
        self.add_link()
        artist = self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.get(self.list_path, 403)
        self.join_team(artist)
        self.assertEqual(self.get(self.list_path), [self.link])
        self.post(self.path, {"software_id": self.software_id}, 403)
        self.delete(f"{self.path}/{self.software_id}", 403)

    def test_a_manager_of_the_team_writes(self):
        manager = self.generate_fixture_user_manager()
        self.log_in_manager()
        self.add_link(403)
        self.join_team(manager)
        self.add_link()
        self.delete(f"{self.path}/{self.software_id}")

    def test_a_supervisor_writes_for_the_task_types_of_the_department(self):
        supervisor = self.generate_fixture_user_supervisor()
        self.join_team(supervisor)
        self.log_in_supervisor()
        # No department: every task type of the project.
        self.add_link()
        lighting = Department.create(name="Lighting", color="#000000")
        persons_service.add_to_department(str(lighting.id), supervisor["id"])
        self.delete(f"{self.path}/{self.software_id}", 403)
        persons_service.add_to_department(
            str(self.department.id), supervisor["id"]
        )
        self.delete(f"{self.path}/{self.software_id}")

    def test_the_links_go_with_the_software(self):
        self.add_link()
        self.delete(f"data/softwares/{self.software_id}")
        self.assertEqual(self.get(self.list_path), [])

    def test_the_links_go_with_the_task_type(self):
        self.add_link()
        self.delete(f"data/task-types/{self.task_type_id}?force=true")
        self.assertEqual(self.get(self.list_path), [])

    def test_the_links_go_with_the_project(self):
        self.add_link()
        cascade_deletion_service.remove_project(self.project_id)
        self.assertEqual(ProjectTaskTypeSoftwareLink.query.count(), 0)
