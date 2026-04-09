from tests.base import ApiDBTestCase

from zou.app.utils import fields
from zou.app.models.project_template import ProjectTemplate


class ProjectTemplateTestCase(ApiDBTestCase):
    def setUp(self):
        super(ProjectTemplateTestCase, self).setUp()
        ProjectTemplate.create(
            name="Short Film", description="Default short-film setup"
        )
        ProjectTemplate.create(
            name="TV Show", description="Episodic show setup"
        )
        ProjectTemplate.create(
            name="VFX Bid", description="Bidding template"
        )

    def test_get_project_templates(self):
        templates = self.get("data/project-templates")
        self.assertEqual(len(templates), 3)

    def test_get_project_template(self):
        template = self.get_first("data/project-templates")
        again = self.get(
            "data/project-templates/%s" % template["id"]
        )
        self.assertEqual(template["id"], again["id"])
        self.get_404("data/project-templates/%s" % fields.gen_uuid())

    def test_create_project_template(self):
        data = {
            "name": "Animated Series",
            "description": "Reusable animated series setup",
            "fps": "24",
            "ratio": "2.39:1",
            "resolution": "2048x858",
            "production_type": "tvshow",
            "production_style": "3d",
        }
        template = self.post("data/project-templates", data)
        self.assertIsNotNone(template["id"])
        self.assertEqual(template["name"], "Animated Series")
        self.assertEqual(template["fps"], "24")

        templates = self.get("data/project-templates")
        self.assertEqual(len(templates), 4)

    def test_create_project_template_duplicate_name_fails(self):
        self.post(
            "data/project-templates",
            {"name": "Short Film"},
            code=400,
        )

    def test_update_project_template(self):
        template = self.get_first("data/project-templates")
        self.put(
            "data/project-templates/%s" % template["id"],
            {"description": "Updated description"},
        )
        again = self.get(
            "data/project-templates/%s" % template["id"]
        )
        self.assertEqual(again["description"], "Updated description")

    def test_delete_project_template(self):
        template = self.get_first("data/project-templates")
        self.delete("data/project-templates/%s" % template["id"])
        self.assertIsNone(ProjectTemplate.get(template["id"]))
        templates = self.get("data/project-templates")
        self.assertEqual(len(templates), 2)
