from tests.base import ApiDBTestCase

from zou.app.services import concepts_service, projects_service


class ConceptFolderRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        # generate_fixture_project() moves self.project and self.project_id
        # to the project it creates: keep the first one under its own name.
        self.main_project_id = str(self.project.id)
        self.folders_path = (
            f"/data/projects/{self.main_project_id}/concept-folders"
        )
        self.move_path = (
            f"/actions/projects/{self.main_project_id}/move-concepts"
        )

    def create_folder(self, name="Characters"):
        return concepts_service.create_concept_folder(
            self.main_project_id, name
        )

    def create_concept(self, name="Concept", parent_id=None):
        return concepts_service.create_concept(
            self.main_project_id, name, parent_id=parent_id
        )

    def get_parent_id(self, concept):
        return self.get(f"/data/concepts/{concept['id']}")["parent_id"]

    def log_in_team_member(self, person, log_in):
        projects_service.add_team_member(self.main_project_id, person["id"])
        log_in()

    def test_get_concept_folders(self):
        self.create_folder("Sets")
        self.create_folder("Characters")
        folders = self.get(self.folders_path)
        self.assertEqual(
            [folder["name"] for folder in folders], ["Characters", "Sets"]
        )
        self.assertEqual(folders[0]["type"], "ConceptFolder")

    def test_get_concept_folders_only_of_the_project(self):
        self.create_folder()
        other_project = self.generate_fixture_project("Other project")
        self.assertEqual(
            self.get(f"/data/projects/{other_project.id}/concept-folders"), []
        )

    def test_create_concept_folder(self):
        folder = self.post(self.folders_path, {"name": "Characters"})
        self.assertEqual(folder["name"], "Characters")
        self.assertEqual(folder["project_id"], self.main_project_id)
        self.assertEqual(folder["created_by"], self.user["id"])
        self.assertEqual(len(self.get(self.folders_path)), 1)

    def test_create_concept_folder_twice(self):
        folder = self.post(self.folders_path, {"name": "Characters"})
        same_folder = self.post(self.folders_path, {"name": "Characters"})
        self.assertEqual(folder["id"], same_folder["id"])
        self.assertEqual(len(self.get(self.folders_path)), 1)

    def test_create_concept_folder_without_name(self):
        self.post(self.folders_path, {"name": ""}, 400)

    def test_rename_concept_folder(self):
        folder = self.create_folder()
        renamed = self.put(
            f"/data/concept-folders/{folder['id']}", {"name": "Creatures"}
        )
        self.assertEqual(renamed["name"], "Creatures")
        self.assertEqual(self.get(self.folders_path)[0]["name"], "Creatures")

    def test_rename_concept_folder_to_a_taken_name(self):
        folder = self.create_folder("Characters")
        self.create_folder("Sets")
        self.put(
            f"/data/concept-folders/{folder['id']}", {"name": "Sets"}, 400
        )

    def test_rename_concept_folder_not_found(self):
        concept = self.create_concept()
        self.put_404(
            f"/data/concept-folders/{concept['id']}", {"name": "Sets"}
        )

    def test_delete_concept_folder_keeps_its_concepts(self):
        folder = self.create_folder()
        concept = self.create_concept(parent_id=folder["id"])
        self.delete(f"/data/concept-folders/{folder['id']}")
        self.assertEqual(self.get(self.folders_path), [])
        self.assertIsNone(self.get_parent_id(concept))

    def test_delete_concept_folder_not_found(self):
        concept = self.create_concept()
        self.delete_404(f"/data/concept-folders/{concept['id']}")
        self.get(f"/data/concepts/{concept['id']}")

    def test_create_concept_in_a_folder(self):
        folder = self.create_folder()
        concept = self.post(
            f"/data/projects/{self.main_project_id}/concepts",
            {"name": "Hero", "parent_id": folder["id"]},
        )
        self.assertEqual(concept["parent_id"], folder["id"])
        concepts = self.get(
            f"/data/concepts/with-tasks?project_id={self.main_project_id}"
        )
        self.assertEqual(concepts[0]["parent_id"], folder["id"])

    def test_create_concept_in_a_folder_of_another_project(self):
        other_project = self.generate_fixture_project("Other project")
        folder = concepts_service.create_concept_folder(
            str(other_project.id), "Characters"
        )
        self.post(
            f"/data/projects/{self.main_project_id}/concepts",
            {"name": "Hero", "parent_id": folder["id"]},
            404,
        )

    def test_move_concepts(self):
        folder = self.create_folder()
        concepts = [self.create_concept("A"), self.create_concept("B")]
        concept_ids = [concept["id"] for concept in concepts]
        moved_ids = self.post(
            self.move_path,
            {"concept_ids": concept_ids, "concept_folder_id": folder["id"]},
            200,
        )
        self.assertEqual(sorted(moved_ids), sorted(concept_ids))
        for concept in concepts:
            self.assertEqual(self.get_parent_id(concept), folder["id"])

    def test_move_concepts_back_to_the_root(self):
        folder = self.create_folder()
        concept = self.create_concept(parent_id=folder["id"])
        self.post(self.move_path, {"concept_ids": [concept["id"]]}, 200)
        self.assertIsNone(self.get_parent_id(concept))

    def test_move_concepts_skips_what_is_not_a_concept_of_the_project(self):
        folder = self.create_folder()
        other_folder = self.create_folder("Sets")
        other_project = self.generate_fixture_project("Other project")
        foreign_concept = concepts_service.create_concept(
            str(other_project.id), "Foreign"
        )
        moved_ids = self.post(
            self.move_path,
            {
                "concept_ids": [foreign_concept["id"], other_folder["id"]],
                "concept_folder_id": folder["id"],
            },
            200,
        )
        self.assertEqual(moved_ids, [])
        self.assertIsNone(self.get_parent_id(foreign_concept))

    def test_move_concepts_to_a_folder_of_another_project(self):
        other_project = self.generate_fixture_project("Other project")
        folder = concepts_service.create_concept_folder(
            str(other_project.id), "Characters"
        )
        concept = self.create_concept()
        self.post(
            self.move_path,
            {
                "concept_ids": [concept["id"]],
                "concept_folder_id": folder["id"],
            },
            404,
        )

    def test_move_concepts_with_a_wrong_id(self):
        self.post(self.move_path, {"concept_ids": ["wrong-id"]}, 400)

    def test_concept_folder_is_neither_an_asset_nor_a_concept(self):
        folder = self.create_folder()
        asset_type_ids = [
            asset_type["id"] for asset_type in self.get("/data/asset-types")
        ]
        self.assertNotIn(folder["entity_type_id"], asset_type_ids)
        self.assertEqual(self.get("/data/assets"), [])
        self.assertEqual(self.get("/data/concepts"), [])
        self.get_404(f"/data/concepts/{folder['id']}")
        entity = self.get(f"/data/entities/{folder['id']}")
        self.assertEqual(entity["type"], "ConceptFolder")

    def test_supervisor_manages_the_folders_of_its_project(self):
        concept = self.create_concept()
        self.log_in_team_member(
            self.generate_fixture_user_supervisor(), self.log_in_supervisor
        )
        folder = self.post(self.folders_path, {"name": "Characters"})
        self.put(f"/data/concept-folders/{folder['id']}", {"name": "Sets"})
        self.post(
            self.move_path,
            {
                "concept_ids": [concept["id"]],
                "concept_folder_id": folder["id"],
            },
            200,
        )
        self.delete(f"/data/concept-folders/{folder['id']}")

    def test_manager_manages_the_folders_of_its_project(self):
        self.log_in_team_member(
            self.generate_fixture_user_manager(), self.log_in_manager
        )
        folder = self.post(self.folders_path, {"name": "Characters"})
        self.delete(f"/data/concept-folders/{folder['id']}")

    def test_supervisor_of_another_project_is_denied(self):
        folder = self.create_folder()
        self.generate_fixture_user_supervisor()
        self.log_in_supervisor()
        self.get(self.folders_path, 403)
        self.post(self.folders_path, {"name": "Sets"}, 403)
        self.put(f"/data/concept-folders/{folder['id']}", {"name": "S"}, 403)
        self.post(self.move_path, {"concept_ids": []}, 403)
        self.delete(f"/data/concept-folders/{folder['id']}", 403)

    def test_artist_only_reads_the_folders(self):
        folder = self.create_folder()
        concept = self.create_concept()
        self.log_in_team_member(
            self.generate_fixture_user_cg_artist(), self.log_in_cg_artist
        )
        self.assertEqual(len(self.get(self.folders_path)), 1)
        self.post(self.folders_path, {"name": "Sets"}, 403)
        self.put(f"/data/concept-folders/{folder['id']}", {"name": "S"}, 403)
        self.post(
            self.move_path,
            {
                "concept_ids": [concept["id"]],
                "concept_folder_id": folder["id"],
            },
            403,
        )
        self.delete(f"/data/concept-folders/{folder['id']}", 403)

    def test_artist_publishes_a_concept_in_a_folder(self):
        folder = self.create_folder()
        self.log_in_team_member(
            self.generate_fixture_user_cg_artist(), self.log_in_cg_artist
        )
        concept = self.post(
            f"/data/projects/{self.main_project_id}/concepts",
            {"name": "Hero", "parent_id": folder["id"]},
        )
        self.assertEqual(concept["parent_id"], folder["id"])

    def test_client_does_not_read_the_folders(self):
        self.create_folder()
        self.log_in_team_member(
            self.generate_fixture_user_client(), self.log_in_client
        )
        self.get(self.folders_path, 403)
