from unittest.mock import patch

from tests.base import ApiDBTestCase

from zou.app import config
from zou.app.utils import fields
from zou.app.models.project import Project
from zou.app.services import (
    projects_service,
    shots_service,
    metadata_descriptors_service,
)


class ProjectTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_project("Agent 327")
        self.generate_fixture_project("Big Buck Bunny")
        self.open_status_id = str(self.open_status.id)

    def test_get_projects(self):
        projects = self.get("data/projects")
        self.assertEqual(len(projects), 3)

    def test_get_project(self):
        project = self.get_first("data/projects/open")
        project_again = self.get(f"data/projects/{project['id']}")
        project["project_status_name"] = "Open"
        self.assertEqual(project, project_again)
        self.get_404(f"data/projects/{fields.gen_uuid()}")

    def test_get_project_without_relations(self):
        project = self.get_first("data/projects")
        project_again = self.get(
            f"data/projects/{project['id']}?relations=false"
        )
        project["project_status_name"] = "Open"
        self.assertEqual(project, project_again)

    def test_get_closed_project_with_the_listing_extra_data(self):
        """
        A closed project is out of the open projects listing, so a read by
        its id is the only one: it carries what the listing attaches.
        """
        self.generate_fixture_project_closed()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        project_id = str(self.project_closed.id)
        self.project_closed.update({"production_type": "tvshow"})
        episode = shots_service.create_episode(project_id, "E01")
        descriptor = metadata_descriptors_service.add_metadata_descriptor(
            project_id, "Asset", "Contractor", "list", ["in", "out"], False
        )
        projects_service.create_project_task_type_link(
            project_id, str(self.task_type.id), 3
        )
        projects_service.create_project_task_status_link(
            project_id, str(self.task_status.id), 2, ["supervisor"]
        )

        project = self.get(f"data/projects/{project_id}")

        self.assertEqual(project["project_status_name"], "closed")
        self.assertEqual(
            [entry["id"] for entry in project["descriptors"]],
            [descriptor["id"]],
        )
        self.assertEqual(
            project["task_types_priority"], {str(self.task_type.id): 3}
        )
        self.assertEqual(
            project["task_statuses_link"],
            {
                str(self.task_status.id): {
                    "priority": 2,
                    "roles_for_board": ["supervisor"],
                }
            },
        )
        self.assertEqual(project["first_episode_id"], episode["id"])

    def test_get_project_as_client_with_the_published_descriptors(self):
        """
        A client reads a project with the descriptors published to clients
        only, as the open projects listing serves them.
        """
        project_id = str(self.project.id)
        self.generate_fixture_user_client()
        projects_service.add_team_member(project_id, self.user_client["id"])
        metadata_descriptors_service.add_metadata_descriptor(
            project_id, "Asset", "Contractor", "list", ["in", "out"], False
        )
        published = metadata_descriptors_service.add_metadata_descriptor(
            project_id, "Asset", "Delivery", "list", ["in", "out"], True
        )
        self.log_in_client()

        project = self.get(f"data/projects/{project_id}")

        self.assertEqual(
            [entry["id"] for entry in project["descriptors"]],
            [published["id"]],
        )

    def test_create_project(self):
        data = {
            "name": "Cosmos Landromat 2",
            "description": "Video game trailer.",
        }
        self.project = self.post("data/projects", data)
        self.assertIsNotNone(self.project["id"])
        self.assertEqual(
            self.project["project_status_id"], str(self.open_status_id)
        )

        projects = self.get("data/projects")
        self.assertEqual(len(projects), 4)

    def test_create_project_with_a_default_preview_background(self):
        background = self.generate_fixture_preview_background_file()
        background_id = str(background.id)
        data = {
            "name": "Cosmos Landromat 2",
            "preview_background_files": [background_id],
            "default_preview_background_file_id": background_id,
        }
        project = self.post("data/projects", data)
        self.assertEqual(
            project["default_preview_background_file_id"], background_id
        )
        project_again = self.get(
            f"data/projects/{project['id']}?relations=true"
        )
        self.assertEqual(
            project_again["preview_background_files"], [background_id]
        )

        # The default must be one of the files attached to the project. The
        # payloads get a new name: a taken one would refuse them on its own.
        data["name"] = "Cosmos Landromat 3"
        data["preview_background_files"] = []
        self.post("data/projects", data, 400)
        del data["preview_background_files"]
        self.post("data/projects", data, 400)

    def test_update_project(self):
        project = self.get_first("data/projects")
        data = {"name": "Cosmos Landromat 3"}
        self.put(f"data/projects/{project['id']}", data)
        project_again = self.get(f"data/projects/{project['id']}")
        self.assertEqual(data["name"], project_again["name"])
        self.put_404(f"data/projects/{fields.gen_uuid()}", data)

    def test_update_project_bitrates(self):
        project = self.get_first("data/projects")
        path = f"data/projects/{project['id']}"
        self.put(
            path,
            {"hd_bitrate_compression": 20, "ld_bitrate_compression": None},
        )
        project_again = self.get(path)
        self.assertEqual(project_again["hd_bitrate_compression"], 20)
        self.assertIsNone(project_again["ld_bitrate_compression"])
        self.put(path, {"hd_bitrate_compression": "fast"}, 400)
        self.put(path, {"ld_bitrate_compression": 0}, 400)
        self.put(path, {"hd_bitrate_compression": 29}, 400)
        # The low def bitrate is checked against the stored high def one.
        self.put(path, {"ld_bitrate_compression": 21}, 400)
        self.put(path, {"ld_bitrate_compression": 20})
        self.put(
            path,
            {"hd_bitrate_compression": 19, "ld_bitrate_compression": 21},
            400,
        )
        # The encoder caps a stored low def left above the high def.
        self.put(path, {"hd_bitrate_compression": 19})
        # Bitrates stored above a ceiling lowered since do not lock the
        # project, even sent back with the rest of it.
        with patch.object(config, "MOVIE_HIGHDEF_BITRATE", 10):
            self.put(path, {"description": "Still editable."})
            self.put(
                path,
                {
                    "description": "Sent back whole.",
                    "hd_bitrate_compression": 19,
                    "ld_bitrate_compression": 20,
                },
            )

    def test_create_project_leaves_the_bitrates_to_the_instance(self):
        project = self.post("data/projects", {"name": "Cosmos Landromat 2"})
        self.assertIsNone(project["hd_bitrate_compression"])
        self.assertIsNone(project["ld_bitrate_compression"])
        project = self.post(
            "data/projects",
            {"name": "Cosmos Landromat 3", "hd_bitrate_compression": None},
        )
        self.assertIsNone(project["hd_bitrate_compression"])

    def test_delete_project(self):
        projects = self.get("data/projects")
        self.assertEqual(len(projects), 3)
        project = projects[0]
        self.delete(f"data/projects/{project['id']}", 400)
        self.generate_fixture_project_closed_status()
        self.generate_fixture_project_closed()
        self.delete(f"data/projects/{self.project_closed.id}")
        self.assertIsNone(Project.get(self.project_closed.id))

    def test_project_status(self):
        data = {"name": "stalled", "color": "#FFFFFF"}
        self.open_status = self.post("data/project-status", data)
        data = {"name": "close", "color": "#000000"}
        self.close_status = self.post("data/project-status", data)
        data = {
            "name": "Cosmos Landromat 2",
            "description": "Video game trailer.",
            "project_status_id": self.open_status["id"],
        }
        self.project = self.post("data/projects", data)
        self.assertIsNotNone(self.project["id"])
        project_again = self.get(f"data/projects/{self.project['id']}")
        self.assertEqual(
            project_again["project_status_id"], self.open_status["id"]
        )

    def test_get_project_by_name(self):
        project_before = self.get("data/projects")[1]
        project = self.get_first(
            f"data/projects?name={project_before['name'].lower()}"
        )
        self.assertEqual(project["id"], project_before["id"])
