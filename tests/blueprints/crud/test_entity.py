from unittest.mock import patch

from tests.base import ApiDBTestCase
from zou.app.models.entity import Entity, EntityConceptLink
from zou.app.services import (
    concepts_service,
    projects_service,
    subscriptions_service,
    tasks_service,
)
from zou.app.utils import fields


class EntityTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.asset_1_id = str(self.generate_fixture_asset("Asset 1").id)
        self.asset_2_id = str(self.generate_fixture_asset("Asset 2").id)
        self.asset_3_id = str(self.generate_fixture_asset("Asset 3").id)

    def test_get_entities(self):
        entities = self.get("data/entities")
        self.assertEqual(len(entities), 3)
        self.assertEqual(entities[0]["type"], "Asset")

    def test_get_entities_as_a_vendor_of_this_project_only(self):
        task = self.generate_fixture_task(entity_id=self.asset_1_id)
        artist_id = self.generate_fixture_user_cg_artist()["id"]
        projects_service.add_team_member(self.project.id, artist_id, "vendor")
        tasks_service.assign_task(task.id, artist_id)
        self.log_in_cg_artist()
        entities = self.get("data/entities")
        self.assertEqual(
            [entity["id"] for entity in entities], [self.asset_1_id]
        )

    def test_get_entities_vendor_with_two_tasks_on_an_entity(self):
        first_task = self.generate_fixture_task(entity_id=self.asset_1_id)
        second_task = self.generate_fixture_task(
            name="Second", entity_id=self.asset_1_id
        )
        vendor_id = self.generate_fixture_user_vendor()["id"]
        projects_service.add_team_member(self.project.id, vendor_id)
        tasks_service.assign_task(first_task.id, vendor_id)
        tasks_service.assign_task(second_task.id, vendor_id)
        self.log_in_vendor()
        entities = self.get("data/entities")
        self.assertEqual(
            [entity["id"] for entity in entities], [self.asset_1_id]
        )

    def test_get_entity(self):
        entity = self.get_first("data/entities?relations=true")
        entity_again = self.get(f"data/entities/{entity['id']}")
        self.assertEqual(entity, entity_again)
        self.get_404(f"data/entities/{fields.gen_uuid()}")

    def test_create_entity(self):
        data = {
            "name": "Cosmos Landromat",
            "description": "Video game trailer.",
            "project_id": self.project.id,
            "entity_type_id": self.asset_type.id,
        }
        self.asset = self.post("data/entities", data)
        self.assertIsNotNone(self.asset["id"])

        entities = self.get("data/entities")
        self.assertEqual(len(entities), 4)

    def test_update_entity(self):
        entity = self.get_first("data/entities")
        data = {"name": "Cosmos Landromat 2", "data": {"extra_work": True}}
        self.put(f"data/entities/{entity['id']}", data)
        entity_again = self.get(f"data/entities/{entity['id']}")
        self.assertEqual(entity_again["name"], data["name"])
        self.assertEqual(entity_again["data"], data["data"])

        data = {"data": {"extra_field": True}}
        self.put(f"data/entities/{entity['id']}", data)
        entity_again = self.get(f"data/entities/{entity['id']}")
        self.assertEqual(
            entity_again["data"], {"extra_work": True, "extra_field": True}
        )

        self.put_404(f"data/entities/{fields.gen_uuid()}", data)

    def test_update_entity_refreshes_casting_stats_on_ready_for_only(self):
        """
        The casting stats of every shot an asset is cast in were recomputed
        on each asset update, because a payload without ready_for compared
        as a change of it.
        """
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        target = (
            "zou.app.blueprints.crud.entity.breakdown_service"
            ".refresh_casting_stats"
        )
        with patch(target) as refresh_casting_stats:
            self.put(f"data/entities/{self.asset_1_id}", {"name": "Renamed"})
            refresh_casting_stats.assert_not_called()

            self.put(
                f"data/entities/{self.asset_1_id}",
                {"ready_for": str(self.task_type.id)},
            )
            refresh_casting_stats.assert_called_once()

            refresh_casting_stats.reset_mock()
            self.put(
                f"data/entities/{self.asset_1_id}",
                {"ready_for": str(self.task_type.id)},
            )
            refresh_casting_stats.assert_not_called()

            self.put(f"data/entities/{self.asset_1_id}", {"ready_for": None})
            refresh_casting_stats.assert_called_once()

    def test_update_entity_refusal_is_a_403(self):
        """
        A refusal used to fall into a catch-all and come back as a 400
        carrying the exception text, which hid it from clients and tests
        filtering on the status.
        """
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.put(f"data/entities/{self.asset_1_id}", {"name": "Nope"}, 403)

    def test_delete_entity(self):
        entities = self.get("data/entities")
        self.assertEqual(len(entities), 3)
        entity = entities[0]
        self.delete(f"data/entities/{entity['id']}")
        entities = self.get("data/entities")
        self.assertEqual(len(entities), 2)
        self.delete_404(f"data/entities/{fields.gen_uuid()}")

    def test_a_creator_out_of_the_team_deletes_no_entity(self):
        artist_id = self.generate_fixture_user_cg_artist()["id"]
        Entity.get(self.asset_1_id).update({"created_by": artist_id})
        self.log_in_cg_artist()
        self.delete(f"data/entities/{self.asset_1_id}", 403)
        projects_service.add_team_member(self.project.id, artist_id)
        self.delete(f"data/entities/{self.asset_1_id}", 204)

    def test_delete_entity_removes_its_links(self):
        """
        A deletion removes the links of the entity along with it: its
        casting in a shot and the concept tagging it.
        """
        self.generate_fixture_shot()
        shot_id = str(self.shot.id)
        self.post(
            "data/entity-links",
            {"entity_in_id": shot_id, "entity_out_id": self.asset_1_id},
        )
        concept = concepts_service.create_concept(
            self.project_id, "Concept", entity_concept_links=[self.asset_1_id]
        )
        self.delete(f"data/entities/{self.asset_1_id}")
        self.get_404(f"data/entities/{self.asset_1_id}")
        self.assertEqual(self.get("data/entity-links"), [])
        self.assertEqual(
            EntityConceptLink.get_all_by(entity_out_id=self.asset_1_id), []
        )
        self.get(f"data/entities/{shot_id}")
        self.get(f"data/entities/{concept['id']}")

    def test_delete_sequence_removes_its_subscriptions(self):
        """
        A deletion removes the subscriptions of a sequence along with it.
        """
        self.generate_fixture_sequence()
        self.generate_fixture_task_type()
        sequence_id = str(self.sequence.id)
        task_type_id = str(self.task_type_animation.id)
        subscriptions_service.subscribe_to_sequence(
            self.user["id"], sequence_id, task_type_id
        )
        self.delete(f"data/entities/{sequence_id}")
        self.get_404(f"data/entities/{sequence_id}")
        self.assertFalse(
            subscriptions_service.has_sequence_subscription(
                self.user["id"], sequence_id, task_type_id
            )
        )

    def test_refused_entity_deletion_keeps_its_links(self):
        """
        The links of an entity were removed and committed before the
        database refused to delete the entity itself: a shot with a task
        stayed, without its casting and its concept links.
        """
        self.generate_fixture_shot_task()
        shot_id = str(self.shot.id)
        self.post(
            "data/entity-links",
            {"entity_in_id": shot_id, "entity_out_id": self.asset_1_id},
        )
        concepts_service.create_concept(
            self.project_id, "Concept", entity_concept_links=[shot_id]
        )
        self.spare_fixtures_from_rollbacks()
        self.delete(f"data/entities/{shot_id}", 400)
        self.get(f"data/entities/{shot_id}")
        self.assertEqual(len(self.get("data/entity-links")), 1)
        self.assertEqual(
            len(EntityConceptLink.get_all_by(entity_out_id=shot_id)), 1
        )

    def test_refused_sequence_deletion_keeps_its_subscriptions(self):
        """
        The subscriptions of a sequence were removed and committed before
        the database refused to delete the sequence, here for its shots.
        """
        self.generate_fixture_shot()
        self.generate_fixture_task_type()
        sequence_id = str(self.sequence.id)
        task_type_id = str(self.task_type_animation.id)
        subscriptions_service.subscribe_to_sequence(
            self.user["id"], sequence_id, task_type_id
        )
        self.spare_fixtures_from_rollbacks()
        self.delete(f"data/entities/{sequence_id}", 400)
        self.assertTrue(
            subscriptions_service.has_sequence_subscription(
                self.user["id"], sequence_id, task_type_id
            )
        )

    def test_delete_entity_link(self):
        entity_link = {
            "entity_in_id": self.asset_1_id,
            "entity_out_id": self.asset_2_id,
        }
        entity_link = self.post("data/entity-links", entity_link)
        entity_links = self.get("data/entity-links")
        self.assertEqual(len(entity_links), 1)
        self.delete(f"data/entity-links/{entity_link['id']}")
        entity_links = self.get("data/entity-links")
        self.assertEqual(entity_links, [])
