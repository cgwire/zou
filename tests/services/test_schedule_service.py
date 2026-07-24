from datetime import datetime

from tests.base import ApiDBTestCase

from zou.app import db
from zou.app.models.entity import Entity
from zou.app.models.milestone import Milestone
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
    ProductionScheduleVersionTaskLinkPersonLink,
)
from zou.app.models.task import Task
from zou.app.services import schedule_service
from zou.app.services.exception import (
    ProductionScheduleVersionNotFoundException,
    WrongParameterException,
)


class ScheduleServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(ScheduleServiceTestCase, self).setUp()
        self.generate_shot_suite()
        self.generate_assigned_task()
        self.project_id = str(self.project.id)
        self.task_type_id = str(self.task_type.id)
        self.sequence_id = str(self.sequence.id)
        self.episode_id = str(self.episode.id)
        self.asset_type_id = str(self.asset_type.id)

    def test_get_schedule_items(self):
        items = schedule_service.get_task_types_schedule_items(self.project.id)
        self.assertEqual(len(items), 1)
        self.generate_fixture_shot_task()
        items = schedule_service.get_task_types_schedule_items(self.project.id)
        self.assertEqual(len(items), 2)
        task_type_ids = [item["task_type_id"] for item in items]
        self.assertTrue(str(self.task_type.id) in task_type_ids)
        self.assertTrue(str(self.task_type_animation.id) in task_type_ids)

        self.shot_task.delete()
        items = schedule_service.get_task_types_schedule_items(self.project.id)
        self.assertEqual(len(items), 1)

    def test_get_schedule_sequence_items(self):
        items = schedule_service.get_sequences_schedule_items(
            self.project.id, self.task_type_id
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], self.sequence_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)

    def test_get_schedule_sequence_items_for_episode(self):
        episode_2 = self.generate_fixture_episode(name="E02")
        sequence_2 = self.generate_fixture_sequence(
            name="S02", episode_id=episode_2.id
        )
        sequence_2_id = str(sequence_2.id)
        episode_2_id = str(episode_2.id)

        # Without episode filter, both sequences are returned.
        items = schedule_service.get_sequences_schedule_items(
            self.project.id, self.task_type_id
        )
        object_ids = {item["object_id"] for item in items}
        self.assertEqual(object_ids, {self.sequence_id, sequence_2_id})

        # Filtered on the first episode, only its sequence is returned.
        items = schedule_service.get_sequences_schedule_items(
            self.project.id, self.task_type_id, self.episode_id
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], self.sequence_id)

        # Filtered on the second episode, only its sequence is returned.
        items = schedule_service.get_sequences_schedule_items(
            self.project.id, self.task_type_id, episode_2_id
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], sequence_2_id)

    def test_get_schedule_episode_items(self):
        items = schedule_service.get_episodes_schedule_items(
            self.project.id, self.task_type_id
        )
        self.assertEqual(items[0]["object_id"], self.episode_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)

    def test_get_schedule_episode_items_for_episode(self):
        episode_1_id = self.episode_id
        episode_2 = self.generate_fixture_episode(name="E02")
        episode_2_id = str(episode_2.id)

        # Without episode filter, both episodes are returned.
        items = schedule_service.get_episodes_schedule_items(
            self.project.id, self.task_type_id
        )
        object_ids = {item["object_id"] for item in items}
        self.assertEqual(object_ids, {episode_1_id, episode_2_id})

        # Filtered on the first episode, only that episode is returned.
        items = schedule_service.get_episodes_schedule_items(
            self.project.id, self.task_type_id, episode_1_id
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], episode_1_id)

        # Filtered on the second episode, only that episode is returned.
        items = schedule_service.get_episodes_schedule_items(
            self.project.id, self.task_type_id, episode_2_id
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], episode_2_id)

    def test_get_schedule_edit_items(self):
        edit = self.generate_fixture_edit(parent_id=self.episode.id)
        edit_id = str(edit.id)
        items = schedule_service.get_edits_schedule_items(
            self.project.id, self.task_type_id
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], edit_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)

    def test_get_schedule_edit_items_for_episode(self):
        edit_1 = self.generate_fixture_edit(
            name="Edit E01", parent_id=self.episode.id
        )
        edit_1_id = str(edit_1.id)
        episode_2 = self.generate_fixture_episode(name="E02")
        episode_2_id = str(episode_2.id)
        edit_2 = self.generate_fixture_edit(
            name="Edit E02", parent_id=episode_2.id
        )
        edit_2_id = str(edit_2.id)

        # Without episode filter, both edits are returned.
        items = schedule_service.get_edits_schedule_items(
            self.project.id, self.task_type_id
        )
        object_ids = {item["object_id"] for item in items}
        self.assertEqual(object_ids, {edit_1_id, edit_2_id})

        # Filtered on the first episode, only its edit is returned.
        items = schedule_service.get_edits_schedule_items(
            self.project.id, self.task_type_id, self.episode_id
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], edit_1_id)

        # Filtered on the second episode, only its edit is returned.
        items = schedule_service.get_edits_schedule_items(
            self.project.id, self.task_type_id, episode_2_id
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], edit_2_id)

    def test_get_schedule_edit_items_ignores_canceled(self):
        edit = self.generate_fixture_edit()
        edit_id = str(edit.id)
        canceled_edit = self.generate_fixture_edit(name="Canceled Edit")
        canceled_edit.update({"canceled": True})

        items = schedule_service.get_edits_schedule_items(
            self.project.id, self.task_type_id
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], edit_id)

    def test_get_schedule_asset_type_items(self):
        items = schedule_service.get_asset_types_schedule_items(
            self.project.id, self.task_type_id
        )
        self.assertEqual(items[0]["object_id"], self.asset_type_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)

    def test_get_schedule_asset_type_items_for_episode(self):
        self.generate_fixture_asset_types()
        episode_1 = self.episode
        episode_2 = self.generate_fixture_episode(name="E02")
        episode_2_id = str(episode_2.id)
        asset_type_character_id = str(self.asset_type_character.id)

        # An asset natively belonging to the first episode...
        Entity.create(
            name="Tree E01",
            project_id=self.project.id,
            entity_type_id=self.asset_type.id,
            source_id=episode_1.id,
        )
        # ...and one of a different type belonging to the second episode.
        Entity.create(
            name="Rabbit E02",
            project_id=self.project.id,
            entity_type_id=self.asset_type_character.id,
            source_id=episode_2.id,
        )

        # Filtered on the first episode, only its asset type is returned.
        items = schedule_service.get_asset_types_schedule_items(
            self.project.id, self.task_type_id, self.episode_id
        )
        object_ids = {item["object_id"] for item in items}
        self.assertEqual(object_ids, {self.asset_type_id})

        # Filtered on the second episode, only its asset type is returned.
        items = schedule_service.get_asset_types_schedule_items(
            self.project.id, self.task_type_id, episode_2_id
        )
        object_ids = {item["object_id"] for item in items}
        self.assertEqual(object_ids, {asset_type_character_id})

    def test_get_all_schedule_items(self):
        schedule_service.get_task_types_schedule_items(self.project.id)
        items = schedule_service.get_schedule_items(self.project.id)
        self.assertGreater(len(items), 0)

    def test_get_milestones_for_project(self):
        milestones = schedule_service.get_milestones_for_project(
            self.project_id
        )
        self.assertEqual(len(milestones), 0)

        Milestone.create(
            name="Alpha",
            project_id=self.project.id,
            date="2024-06-01",
        )
        Milestone.create(
            name="Beta",
            project_id=self.project.id,
            date="2024-09-01",
        )
        milestones = schedule_service.get_milestones_for_project(
            self.project_id
        )
        self.assertEqual(len(milestones), 2)

    def test_get_production_schedule_version_raw(self):
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        result = schedule_service.get_production_schedule_version_raw(
            str(psv.id)
        )
        self.assertEqual(result.id, psv.id)

    def test_get_production_schedule_version_raw_not_found(self):
        with self.assertRaises(ProductionScheduleVersionNotFoundException):
            schedule_service.get_production_schedule_version_raw("wrong-id")

    def test_get_production_schedule_version(self):
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        result = schedule_service.get_production_schedule_version(str(psv.id))
        self.assertEqual(result["id"], str(psv.id))
        self.assertEqual(result["name"], "v1")

    def test_update_production_schedule_version(self):
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        result = schedule_service.update_production_schedule_version(
            str(psv.id), {"name": "v2"}
        )
        self.assertEqual(result["name"], "v2")

    def test_get_production_schedule_version_task_links(self):
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        links = schedule_service.get_production_schedule_version_task_links(
            str(psv.id)
        )
        self.assertEqual(len(links), 0)

    def _make_person(self, first_name, last_name):
        # generate_fixture_person reassigns self.person; restore it afterwards.
        original = self.person
        person = self.generate_fixture_person(
            first_name=first_name,
            last_name=last_name,
            desktop_login=f"{first_name}.{last_name}".lower(),
            email=f"{first_name}.{last_name}@example.com".lower(),
        )
        self.person = original
        return person

    def _make_task(self, name, entity_id, assignees):
        return Task.create(
            name=name,
            project_id=self.project.id,
            task_type_id=self.task_type.id,
            task_status_id=self.task_status.id,
            entity_id=entity_id,
            assignees=assignees,
            assigner_id=self.assigner.id,
            estimation=40,
        )

    def _assignees_by_task(self, psv_id):
        tl = ProductionScheduleVersionTaskLink
        pl = ProductionScheduleVersionTaskLinkPersonLink
        rows = (
            db.session.query(tl.task_id, pl.person_id)
            .join(pl, pl.production_schedule_version_task_link_id == tl.id)
            .filter(tl.production_schedule_version_id == psv_id)
            .all()
        )
        result = {}
        for task_id, person_id in rows:
            result.setdefault(str(task_id), set()).add(str(person_id))
        return result

    def test_set_production_schedule_version_task_links_from_production(self):
        # Two tasks assigned to DISTINCT people so a partial or cross-wired
        # assignee copy is detectable.
        jane = self._make_person("Jane", "Roe")
        asset2 = self.generate_fixture_asset(name="Asset2")
        task_john = self.task
        task_jane = self._make_task("Master", asset2.id, [jane])

        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        result = schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        self.assertEqual(result, {"success": True, "task_link_count": 2})

        links = schedule_service.get_production_schedule_version_task_links(
            str(psv.id), relations=True
        )
        self.assertEqual(len(links), 2)
        got = {link["task_id"]: set(link["assignees"]) for link in links}
        self.assertEqual(
            got,
            {
                str(task_john.id): {str(self.person.id)},
                str(task_jane.id): {str(jane.id)},
            },
        )

    def test_set_production_schedule_version_task_links_is_idempotent(self):
        # A second copy must not duplicate links nor change their assignees.
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        expected = self._assignees_by_task(str(psv.id))

        result = schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        self.assertEqual(result["task_link_count"], 1)
        self.assertEqual(self._assignees_by_task(str(psv.id)), expected)

        # The DELETE-then-reinsert leaves exactly one person link.
        tl = ProductionScheduleVersionTaskLink
        pl = ProductionScheduleVersionTaskLinkPersonLink
        person_link_count = (
            db.session.query(pl)
            .join(tl, tl.id == pl.production_schedule_version_task_link_id)
            .filter(tl.production_schedule_version_id == str(psv.id))
            .count()
        )
        self.assertEqual(person_link_count, 1)

    def test_set_production_schedule_version_task_links_updates_existing(self):
        # The ON CONFLICT DO UPDATE branch must refresh every copied value:
        # estimation AND the start/due dates.
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        self.task.update(
            {
                "estimation": 123,
                "start_date": datetime(2021, 3, 1),
                "due_date": datetime(2021, 3, 15),
            }
        )
        schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        links = schedule_service.get_production_schedule_version_task_links(
            str(psv.id)
        )
        self.assertEqual(len(links), 1)
        task = self.task.serialize()
        self.assertEqual(links[0]["estimation"], 123)
        self.assertEqual(links[0]["start_date"], task["start_date"])
        self.assertEqual(links[0]["due_date"], task["due_date"])

    def test_set_production_schedule_version_task_links_refreshes_assignees(
        self,
    ):
        # The scoped DELETE + INSERT must REFRESH assignees to their new set on
        # a re-copy: a removed assignee disappears and an added one appears.
        jane = self._make_person("Jane", "Roe")
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        self.assertEqual(
            self._assignees_by_task(str(psv.id)),
            {str(self.task.id): {str(self.person.id)}},
        )

        # self.person is dropped and jane is added.
        self.task.assignees = [jane]
        db.session.commit()
        schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        self.assertEqual(
            self._assignees_by_task(str(psv.id)),
            {str(self.task.id): {str(jane.id)}},
        )

    def test_set_production_schedule_version_task_links_unassigned_task(self):
        # A task with no assignee yields a link with no person link.
        asset2 = self.generate_fixture_asset(name="Asset2")
        self._make_task("Master", asset2.id, [])

        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        result = schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        self.assertEqual(result["task_link_count"], 2)
        self.assertEqual(
            self._assignees_by_task(str(psv.id)),
            {str(self.task.id): {str(self.person.id)}},
        )

    def test_set_production_schedule_version_task_links_no_task(self):
        # A production with no task must not crash and report an empty copy.
        empty_project = self.generate_fixture_project(name="Empty Project")
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=empty_project.id
        )
        result = schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        self.assertEqual(result, {"success": True, "task_link_count": 0})

    def test_set_production_schedule_version_task_links_from_version(self):
        # Copy version A -> B; two tasks assigned to distinct people.
        jane = self._make_person("Jane", "Roe")
        asset2 = self.generate_fixture_asset(name="Asset2")
        task_john = self.task
        task_jane = self._make_task("Master", asset2.id, [jane])

        source = ProductionScheduleVersion.create(
            name="A", project_id=self.project.id
        )
        schedule_service.set_production_schedule_version_task_links_from_production(
            str(source.id)
        )
        target = ProductionScheduleVersion.create(
            name="B", project_id=self.project.id
        )
        result = schedule_service.set_production_schedule_version_task_links_from_production_schedule_version(
            str(target.id), str(source.id)
        )
        self.assertEqual(result, {"success": True, "task_link_count": 2})
        self.assertEqual(
            self._assignees_by_task(str(target.id)),
            {
                str(task_john.id): {str(self.person.id)},
                str(task_jane.id): {str(jane.id)},
            },
        )
        # The copy records its origin version.
        copied = ProductionScheduleVersion.get(target.id)
        self.assertEqual(
            str(copied.production_schedule_from), str(source.id)
        )

    def test_set_production_schedule_version_task_links_from_version_preserves_unrelated(
        self,
    ):
        # A target link whose task is not in the source keeps its assignees.
        jane = self._make_person("Jane", "Roe")
        asset2 = self.generate_fixture_asset(name="Asset2")
        task_john = self.task
        task_jane = self._make_task("Master", asset2.id, [jane])

        source = ProductionScheduleVersion.create(
            name="A", project_id=self.project.id
        )
        source_link = ProductionScheduleVersionTaskLink.create(
            production_schedule_version_id=source.id, task_id=task_john.id
        )
        source_link.assignees = [self.person]

        target = ProductionScheduleVersion.create(
            name="B", project_id=self.project.id
        )
        unrelated_link = ProductionScheduleVersionTaskLink.create(
            production_schedule_version_id=target.id, task_id=task_jane.id
        )
        unrelated_link.assignees = [jane]
        db.session.commit()

        result = schedule_service.set_production_schedule_version_task_links_from_production_schedule_version(
            str(target.id), str(source.id)
        )
        # Only task_john is copied from the source; the count reflects the
        # copied links, not the 2 links now on the target.
        self.assertEqual(result, {"success": True, "task_link_count": 1})
        self.assertEqual(
            self._assignees_by_task(str(target.id)),
            {
                str(task_john.id): {str(self.person.id)},
                str(task_jane.id): {str(jane.id)},
            },
        )

    def test_set_production_schedule_version_task_links_from_version_rejects_self_copy(
        self,
    ):
        # Copying a version onto itself is rejected, not an assignee wipe.
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        with self.assertRaises(WrongParameterException):
            schedule_service.set_production_schedule_version_task_links_from_production_schedule_version(
                str(psv.id), str(psv.id)
            )
        self.assertEqual(
            self._assignees_by_task(str(psv.id)),
            {str(self.task.id): {str(self.person.id)}},
        )

    def test_set_task_links_from_version_rejects_cross_project(self):
        # The route rejects copying between two different projects with a 400.
        target = ProductionScheduleVersion.create(
            name="target", project_id=self.project.id
        )
        other_project = self.generate_fixture_project(name="Other Project")
        source = ProductionScheduleVersion.create(
            name="source", project_id=other_project.id
        )
        self.post(
            f"/actions/production-schedule-versions/{target.id}"
            "/set-task-links-from-production-schedule-version",
            {"production_schedule_version_id": str(source.id)},
            400,
        )

    def test_set_task_links_from_version_rejects_case_mismatched_self_copy(
        self,
    ):
        # An uppercase UUID in the path resolves (in SQL) to the same version
        # as the normalized source id, so the self-copy guard must still fire
        # and the assignees must not be wiped.
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        self.post(
            f"/actions/production-schedule-versions/{str(psv.id).upper()}"
            "/set-task-links-from-production-schedule-version",
            {"production_schedule_version_id": str(psv.id)},
            400,
        )
        self.assertEqual(
            self._assignees_by_task(str(psv.id)),
            {str(self.task.id): {str(self.person.id)}},
        )

    def test_apply_production_schedule_version_to_production(self):
        # apply copies the version's task-link values back onto the tasks,
        # locks the version and records it as the project's source version.
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        link = ProductionScheduleVersionTaskLink.get_by(
            production_schedule_version_id=psv.id, task_id=self.task.id
        )
        link.update(
            {
                "estimation": 321,
                "start_date": datetime(2022, 5, 2),
                "due_date": datetime(2022, 5, 20),
            }
        )

        result = schedule_service.apply_production_schedule_version_to_production(
            str(psv.id)
        )
        self.assertEqual(result, {"success": True, "task_count": 1})

        task = Task.get(self.task.id)
        self.assertEqual(task.estimation, 321)
        self.assertEqual(task.start_date, datetime(2022, 5, 2))
        self.assertEqual(task.due_date, datetime(2022, 5, 20))

        version = ProductionScheduleVersion.get(psv.id)
        self.assertTrue(version.locked)

        db.session.refresh(self.project)
        self.assertEqual(
            str(self.project.from_schedule_version_id), str(psv.id)
        )
