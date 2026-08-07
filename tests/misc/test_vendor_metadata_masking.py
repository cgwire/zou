import json

from tests.base import ApiDBTestCase

from zou.app.services import (
    persons_service,
    projects_service,
    tasks_service,
)


class VendorMetadataMaskingTestCase(ApiDBTestCase):
    """
    A metadata descriptor restricted to a department must not reach a vendor
    who does not belong to it, whichever listing they read the entity from.

    The listings carrying the tasks mask while they build their rows, the
    others hand back whole serialized entities: two ways of answering the
    same production, so they are checked together rather than one by one.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()
        self.generate_fixture_edit()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        self.generate_fixture_episode_task()
        self.generate_fixture_sequence_task()
        self.generate_fixture_scene_task()
        self.generate_fixture_edit_task()

    def restrict_a_descriptor_the_vendor_cannot_read(self):
        """
        Give every entity a "contractor" field reserved to a department the
        vendor is not part of, and put the vendor on a task of each of them
        so that they reach the entities at all.
        """
        project_id = str(self.project.id)
        self.generate_fixture_user_vendor()
        person_id = self.user_vendor["id"]
        projects_service.add_team_member(project_id, person_id)
        for task in [
            self.task,
            self.shot_task,
            self.episode_task,
            self.sequence_task,
            self.scene_task,
            self.edit_task,
        ]:
            tasks_service.assign_task(str(task.id), person_id)

        entities = {
            "Asset": self.asset,
            "Shot": self.shot,
            "Episode": self.episode,
            "Sequence": self.sequence,
            "Scene": self.scene,
            "Edit": self.edit,
        }
        for entity_type, entity in entities.items():
            projects_service.add_metadata_descriptor(
                project_id,
                entity_type,
                "Contractor",
                "list",
                ["value 1"],
                False,
                [str(self.department.id)],
            )
            entity.update({"data": {"contractor": "secret"}})
        projects_service.clear_project_cache(project_id)
        return project_id

    def listing_paths(self, project_id):
        episode_id = str(self.episode.id)
        sequence_id = str(self.sequence.id)
        return [
            "data/assets",
            "data/assets/all",
            "data/assets/with-tasks",
            f"data/projects/{project_id}/assets",
            "data/shots",
            "data/shots/all",
            "data/shots/with-tasks",
            f"data/projects/{project_id}/shots",
            f"data/episodes/{episode_id}/shots",
            f"data/sequences/{sequence_id}/shots",
            "data/edits",
            "data/edits/all",
            "data/edits/with-tasks",
            f"data/projects/{project_id}/edits",
            f"data/episodes/{episode_id}/edits",
            "data/episodes",
            "data/episodes/with-tasks",
            f"data/projects/{project_id}/episodes",
            "data/sequences",
            "data/sequences/with-tasks",
            f"data/projects/{project_id}/sequences",
            f"data/episodes/{episode_id}/sequences",
            "data/scenes/all",
            "data/scenes/with-tasks",
            f"data/projects/{project_id}/scenes",
            f"data/sequences/{sequence_id}/scenes",
        ]

    def test_no_listing_hands_a_restricted_descriptor_to_a_vendor(self):
        project_id = self.restrict_a_descriptor_the_vendor_cannot_read()
        self.log_in_vendor()

        reached = 0
        for path in self.listing_paths(project_id):
            with self.subTest(path=path):
                response = self.app.get(
                    f"/{path}?project_id={project_id}",
                    headers=self.base_headers,
                )
                # A listing a vendor cannot reach at all leaks nothing; only
                # the ones that answer have something to hide.
                if response.status_code != 200:
                    continue
                reached += 1
                for row in json.loads(response.data):
                    self.assertNotIn("contractor", row.get("data") or {})
        self.assertGreater(reached, 0)

    def test_a_descriptor_of_their_own_department_still_reaches_them(self):
        # The masking narrows, it does not blank the metadata out.
        project_id = self.restrict_a_descriptor_the_vendor_cannot_read()
        persons_service.add_to_department(
            str(self.department.id), self.user_vendor["id"]
        )
        self.log_in_vendor()

        shots = self.get(f"data/shots?project_id={project_id}")

        self.assertEqual(shots[0]["data"]["contractor"], "secret")
