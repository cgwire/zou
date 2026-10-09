import pytest
from tests.services.cases import (
    AssetsTestCase,
    ShotsTestCase,
    DeletionTestCase,
)
from tests.base import ApiDBTestCase
from sqlalchemy import text
from unittest.mock import patch

from zou.app.models.entity import Entity, EntityLink
from zou.app.services import (
    assets_service,
    breakdown_service,
    cascade_deletion_service,
    concepts_service,
    deletion_service,
    edits_service,
    shots_service,
)
from zou.app.exceptions import (
    AssetNotFoundException,
    ConceptNotFoundException,
    EpisodeNotFoundException,
    ModelWithRelationsDeletionException,
    EditNotFoundException,
    SceneNotFoundException,
    ShotNotFoundException,
    SequenceNotFoundException,
)
from zou.app import db
from zou.app.models.task import Task
from zou.app.models.output_file import OutputFile
from zou.app.models.person import Person
from zou.app.models.preview_file import PreviewFile
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)
from zou.app.models.project import Project
from zou.app.models.search_filter import SearchFilter
from zou.app.models.search_filter_group import SearchFilterGroup
from zou.app.models.schedule_item import ScheduleItem

UNKNOWN = "00000000-0000-0000-0000-000000000000"


class AssetRemovalTestCase(AssetsTestCase):
    def test_remove_asset(self):
        asset_id = self.asset.id
        cascade_deletion_service.remove_asset(asset_id)
        self.assertRaises(
            AssetNotFoundException, assets_service.get_asset, asset_id
        )

    def test_remove_asset_carrying_tasks(self):
        """
        An asset someone has worked on is kept and marked canceled, so the
        history of those tasks survives. Only force really deletes it.
        """
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_task()
        asset_id = str(self.asset.id)
        assets_service.get_asset(asset_id)

        cascade_deletion_service.remove_asset(asset_id)
        self.assertTrue(assets_service.get_asset(asset_id)["canceled"])

        cascade_deletion_service.remove_asset(asset_id, force=True)
        self.assertRaises(
            AssetNotFoundException, assets_service.get_asset, asset_id
        )

    def test_remove_asset_reparents_its_children(self):
        child = Entity.create(
            name="Child",
            entity_type_id=self.asset_type.id,
            project_id=self.project.id,
            parent_id=self.asset.id,
        )
        cascade_deletion_service.remove_asset(self.asset.id)
        self.assertIsNone(Entity.get(child.id).parent_id)

    def test_cancel_asset(self):
        asset_id = str(self.asset.id)
        # Read it once so the serialization is memoized: canceling writes
        # the same column as the canceling branch of remove_asset and drops
        # the same cache.
        assets_service.get_asset(asset_id)
        cascade_deletion_service.cancel_asset(asset_id)
        self.assertTrue(assets_service.get_asset(asset_id)["canceled"])


class ConceptRemovalTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()

    def a_concept(self, name, project=None, **kwargs):
        return concepts_service.create_concept(
            str((project or self.project).id), name, **kwargs
        )

    def a_concept_with_a_task(self, name):
        """
        A concept and one task on it, with the whole chain a task needs.
        """
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        concept = self.a_concept(name)
        task = self.generate_fixture_task(
            entity_id=concept["id"], task_type_id=self.task_type.id
        )
        return concept, task

    def test_remove_concept(self):
        concept = self.a_concept("To Remove")
        result = cascade_deletion_service.remove_concept(concept["id"])
        self.assertEqual(result["id"], concept["id"])
        with self.assertRaises(ConceptNotFoundException):
            concepts_service.get_concept_raw(concept["id"])

    def test_remove_concept_with_task_cancels(self):
        # A concept someone has worked on is canceled rather than deleted.
        concept, _ = self.a_concept_with_a_task("With Task")

        result = cascade_deletion_service.remove_concept(concept["id"])

        self.assertTrue(result["canceled"])
        self.assertIsNotNone(concepts_service.get_concept_raw(concept["id"]))

    def test_remove_concept_with_task_force(self):
        concept, _ = self.a_concept_with_a_task("Force Remove")
        result = cascade_deletion_service.remove_concept(
            concept["id"], force=True
        )
        self.assertEqual(result["id"], concept["id"])
        with self.assertRaises(ConceptNotFoundException):
            concepts_service.get_concept_raw(concept["id"])


class RemoveEpisodeTestCase(DeletionTestCase):
    """
    An episode is the top of a tree: sequences, shots, assets and their
    tasks hang off it, and it only goes when the tree does.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        self.episode_id = str(self.episode.id)

    def test_remove_episode_refuses_what_is_still_linked(self):
        # Nothing is read back afterwards: the refusal rolls the session
        # back, and the fixtures of this test are uncommitted work that
        # goes with it. In production each request owns its transaction.
        with self.assertRaises(ModelWithRelationsDeletionException):
            cascade_deletion_service.remove_episode(self.episode_id)

    def test_remove_episode_force_takes_the_tree_with_it(self):
        sequence_id = str(self.sequence.id)
        shot_id = str(self.shot.id)
        task_id = str(self.shot_task.id)

        result = cascade_deletion_service.remove_episode(
            self.episode_id, force=True
        )

        self.assertEqual(result["id"], self.episode_id)
        for entity_id in [self.episode_id, sequence_id, shot_id]:
            self.assertIsNone(Entity.get(entity_id))
        self.assertIsNone(Task.get(task_id))

    def test_remove_episode_announces_it(self):
        captured = self.capture_events("episode:delete")

        cascade_deletion_service.remove_episode(self.episode_id, force=True)

        self.assertEqual(
            [(event["episode_id"], event["project_id"]) for event in captured],
            [(self.episode_id, str(self.project.id))],
        )

    def test_remove_episode_not_found(self):
        with self.assertRaises(EpisodeNotFoundException):
            cascade_deletion_service.remove_episode(UNKNOWN)

    def test_removing_an_episode_leaves_the_other_one_alone(self):
        here = self.episode_id
        elsewhere = self.generate_fixture_episode("E02")
        other_sequence = self.generate_fixture_sequence(
            "S02", episode_id=elsewhere.id
        )

        cascade_deletion_service.remove_episode(here, force=True)

        self.assertIsNotNone(Entity.get(str(elsewhere.id)))
        self.assertIsNotNone(Entity.get(str(other_sequence.id)))


class RemoveProjectTestCase(DeletionTestCase):
    def test_remove_project_with_production_schedule_version(self):
        # Regression: deleting a project that had a production schedule
        # version failed on the FK constraint because the version (and its
        # task links + self-reference) were never cleaned up.
        project_id = str(self.project.id)
        version = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        derived = ProductionScheduleVersion.create(
            name="v2",
            project_id=self.project.id,
            production_schedule_from=version.id,
        )
        ProductionScheduleVersionTaskLink.create(
            production_schedule_version_id=version.id,
            task_id=self.task.id,
        )
        version_id = str(version.id)
        derived_id = str(derived.id)

        cascade_deletion_service.remove_project(project_id)

        self.assertIsNone(Project.get(project_id))
        self.assertIsNone(ProductionScheduleVersion.get(version_id))
        self.assertIsNone(ProductionScheduleVersion.get(derived_id))

    def test_remove_project_with_a_grouped_search_filter(self):
        # Regression: the search filter groups of the project were deleted
        # before the filters they hold, which the foreign key refused. A
        # group takes its filters with it, even one set on no project.
        project_id = str(self.project.id)
        group = SearchFilterGroup.create(
            list_type="asset", name="Props", project_id=self.project.id
        )
        removed = [(SearchFilterGroup, str(group.id))]
        for filter_project_id in [self.project.id, None]:
            search_filter = SearchFilter.create(
                list_type="asset",
                name="Chairs",
                search_query="chair",
                project_id=filter_project_id,
                search_filter_group_id=group.id,
            )
            removed.append((SearchFilter, str(search_filter.id)))

        cascade_deletion_service.remove_project(project_id)

        self.assertIsNone(Project.get(project_id))
        for model, row_id in removed:
            self.assertIsNone(model.get(row_id), model.__name__)

    def test_remove_project_with_an_applied_production_schedule_version(
        self,
    ):
        # Regression: applying a version points the project at it, and that
        # reference blocked the deletion of the version, hence of the
        # project, until the key got its SET NULL rule.
        project_id = str(self.project.id)
        version = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        self.project.update({"from_schedule_version_id": version.id})
        version_id = str(version.id)

        cascade_deletion_service.remove_project(project_id)

        self.assertIsNone(Project.get(project_id))
        self.assertIsNone(ProductionScheduleVersion.get(version_id))

    def test_remove_project_leaves_the_other_productions_alone(self):
        """
        remove_project walks a dozen tables, each scoped to the production
        it was given. One row of every shape lives in a second production
        here, and all of them must survive.
        """
        self.generate_fixture_project_standard()
        other_asset = self.generate_fixture_asset(
            "Car", project_id=self.project_standard.id
        )
        other_task = self.generate_fixture_task(
            name="other", entity_id=other_asset.id
        )
        other_task.update({"project_id": self.project_standard.id})
        other_preview = PreviewFile.create(
            name="other.png",
            revision=1,
            extension="png",
            task_id=other_task.id,
            person_id=self.person.id,
        )
        other_version = ProductionScheduleVersion.create(
            name="v1", project_id=self.project_standard.id
        )
        # The version rows are deleted by project id, but the task links
        # and the self references are broken by the id list built above
        # them, which is scoped separately.
        other_link = ProductionScheduleVersionTaskLink.create(
            production_schedule_version_id=other_version.id,
            task_id=other_task.id,
        )
        self.generate_fixture_output_type()
        other_output = self.generate_fixture_output_file(task=other_task)
        # The filters held by a group are deleted through a join on the
        # group table, scoped by the project of the group.
        other_group = SearchFilterGroup.create(
            list_type="asset",
            name="Props",
            project_id=self.project_standard.id,
        )
        other_filter = SearchFilter.create(
            list_type="asset",
            name="Chairs",
            search_query="chair",
            project_id=self.project_standard.id,
            search_filter_group_id=other_group.id,
        )
        survivors = [
            (Task, str(other_task.id)),
            (PreviewFile, str(other_preview.id)),
            (ProductionScheduleVersion, str(other_version.id)),
            (ProductionScheduleVersionTaskLink, str(other_link.id)),
            (OutputFile, str(other_output.id)),
            (SearchFilterGroup, str(other_group.id)),
            (SearchFilter, str(other_filter.id)),
        ]

        cascade_deletion_service.remove_project(str(self.project.id))

        for model, row_id in survivors:
            self.assertIsNotNone(model.get(row_id), model.__name__)
        self.assertIsNotNone(Project.get(str(self.project_standard.id)))


class RemovePersonTestCase(DeletionTestCase):
    def generate_search_filter_group(self, person):
        return SearchFilterGroup.create(
            list_type="asset",
            name="Props",
            is_shared=True,
            person_id=person.id,
            project_id=self.project.id,
        )

    def generate_search_filter(self, person, group):
        return SearchFilter.create(
            list_type="asset",
            name="Chairs",
            search_query="chair",
            is_shared=True,
            person_id=person.id,
            project_id=self.project.id,
            search_filter_group_id=group.id,
        )

    def test_remove_person_with_a_grouped_search_filter(self):
        """
        Regression: the search filter groups of the person were deleted
        before the filters they hold, which the foreign key refused. A
        shared group may hold the filter of someone else: it goes with the
        group, as when the group is removed on its own. The groups of the
        others stay.
        """
        person = Person.create(first_name="Jane", last_name="Doe")
        group = self.generate_search_filter_group(person)
        own_filter = self.generate_search_filter(person, group)
        other_filter = self.generate_search_filter(self.person, group)
        other_group = self.generate_search_filter_group(self.person)
        kept_filter = self.generate_search_filter(self.person, other_group)
        removed = [
            (Person, str(person.id)),
            (SearchFilterGroup, str(group.id)),
            (SearchFilter, str(own_filter.id)),
            (SearchFilter, str(other_filter.id)),
        ]
        kept = [
            (SearchFilterGroup, str(other_group.id)),
            (SearchFilter, str(kept_filter.id)),
        ]

        cascade_deletion_service.remove_person(str(person.id))

        for model, row_id in removed:
            self.assertIsNone(model.get(row_id), model.__name__)
        for model, row_id in kept:
            self.assertIsNotNone(model.get(row_id), model.__name__)


class EditRemovalTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_episode()
        self.generate_fixture_edit(parent_id=self.episode.id)
        self.generate_fixture_asset()

    def the_chain_a_task_needs(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()

    def test_remove_edit_with_a_task_cancels_it(self):
        # An edit someone has worked on is canceled rather than deleted.
        self.the_chain_a_task_needs()
        self.generate_fixture_edit_task()

        cascade_deletion_service.remove_edit(str(self.edit.id))

        self.assertTrue(edits_service.get_edit(self.edit.id)["canceled"])

    def test_remove_edit_with_a_task_can_be_forced(self):
        self.the_chain_a_task_needs()
        self.generate_fixture_edit_task()

        cascade_deletion_service.remove_edit(str(self.edit.id), force=True)

        with pytest.raises(EditNotFoundException):
            edits_service.get_edit(self.edit.id)

    def test_remove_edit(self):
        edit_id = str(self.edit.id)
        self.assertIsNotNone(edit_id)
        edits_service.get_edit(edit_id)

        cascade_deletion_service.remove_edit(edit_id)
        with pytest.raises(EditNotFoundException):
            edits_service.get_edit(edit_id)

    def test_remove_edit_deletes_schedule_items(self):
        self.generate_fixture_task_type()
        edit_id = str(self.edit.id)
        schedule_item = ScheduleItem.create(
            project_id=self.project.id,
            task_type_id=self.task_type.id,
            object_id=self.edit.id,
        )
        schedule_item_id = schedule_item.id

        cascade_deletion_service.remove_edit(edit_id)
        self.assertIsNone(ScheduleItem.get(schedule_item_id))


class ShotRemovalTestCase(ShotsTestCase):
    """
    Removing an entity that other rows still point at. A shot that carries
    tasks is canceled rather than deleted, unless the caller forces it.
    """

    def test_a_shot_with_no_task_is_deleted(self):
        """
        The casting of a shot points at it from a link table: leaving the
        links behind would keep the asset cast in a shot that no longer
        exists, and the delete would fail on the foreign key anyway.
        """
        shot_id = str(self.shot.id)
        breakdown_service.create_casting_link(shot_id, str(self.asset.id))

        cascade_deletion_service.remove_shot(shot_id)

        with pytest.raises(ShotNotFoundException):
            shots_service.get_shot(shot_id)
        self.assertEqual(
            EntityLink.query.filter_by(entity_in_id=shot_id).count(), 0
        )

    def test_a_shot_with_tasks_is_canceled(self):
        self.generate_shot_task()
        shot_id = str(self.shot.id)

        cascade_deletion_service.remove_shot(shot_id)

        self.assertTrue(shots_service.get_shot(shot_id)["canceled"])

    def test_a_forced_removal_takes_the_tasks_with_it(self):
        self.generate_shot_task()
        shot_id = str(self.shot.id)

        cascade_deletion_service.remove_shot(shot_id, force=True)

        with pytest.raises(ShotNotFoundException):
            shots_service.get_shot(shot_id)
        self.assertEqual(Task.query.filter_by(entity_id=shot_id).count(), 0)

    def test_a_forced_removal_skips_a_task_deleted_meanwhile(self):
        """
        Another request may delete a task of the shot while the removal
        walks them. Every removal commits, which expires the instances left
        to walk: reading the id of the deleted one reloaded a missing row
        and raised ObjectDeletedError.
        """
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        shot_id = str(self.shot.id)
        # No assignee, so that a plain DELETE can take either of them.
        for task_type in [self.task_type_layout, self.task_type_animation]:
            Task.create(
                name=task_type.name,
                project_id=self.project.id,
                task_type_id=task_type.id,
                task_status_id=self.task_status.id,
                entity_id=self.shot.id,
            )
        remove_task = deletion_service.remove_task

        def delete_the_other_task_first(
            task_id, force=False, restore_main=True
        ):
            # Straight on the table, out of sight of the session, as the
            # other request does.
            db.session.execute(
                text(
                    "DELETE FROM task "
                    "WHERE entity_id = :shot_id AND id != :task_id"
                ),
                {"shot_id": shot_id, "task_id": str(task_id)},
            )
            db.session.commit()
            return remove_task(task_id, force=force, restore_main=restore_main)

        with patch.object(
            deletion_service,
            "remove_task",
            side_effect=delete_the_other_task_first,
        ):
            cascade_deletion_service.remove_shot(shot_id, force=True)

        with pytest.raises(ShotNotFoundException):
            shots_service.get_shot(shot_id)
        self.assertEqual(Task.query.filter_by(entity_id=shot_id).count(), 0)

    def test_a_scene_is_deleted(self):
        scene_id = str(self.scene.id)
        cascade_deletion_service.remove_scene(scene_id)
        with pytest.raises(SceneNotFoundException):
            shots_service.get_scene(scene_id)

    def test_a_sequence_still_holding_shots_is_not_removed(self):
        """
        Without force the caller is told, rather than left with a branch of
        the production hanging from nothing.

        Nothing is read back afterwards: the rolled back delete takes the
        fixtures of this test with it, since they were never committed.
        """
        self.assertRaises(
            ModelWithRelationsDeletionException,
            cascade_deletion_service.remove_sequence,
            str(self.sequence.id),
        )

    def test_a_forced_sequence_removal_takes_its_children_with_it(self):
        """
        Scenes hang from a sequence too: walking its children as if they
        were all shots raises halfway through, after part of the sequence
        is already gone.
        """
        sequence_id = str(self.sequence.id)
        shot_id = str(self.shot.id)
        scene_id = str(self.scene.id)

        cascade_deletion_service.remove_sequence(sequence_id, force=True)

        with pytest.raises(SequenceNotFoundException):
            shots_service.get_sequence(sequence_id)
        with pytest.raises(ShotNotFoundException):
            shots_service.get_shot(shot_id)
        with pytest.raises(SceneNotFoundException):
            shots_service.get_scene(scene_id)
