import datetime

from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity, EntityLink
from zou.app.models.task import Task
from zou.app.services import (
    breakdown_service,
    persons_service,
    shots_service,
    tasks_service,
)
from zou.app.utils import fields
from zou.app.services.exception import (
    EpisodeNotFoundException,
    ModelWithRelationsDeletionException,
    SceneNotFoundException,
    ShotNotFoundException,
    SequenceNotFoundException,
)


class FirstEpisodeTestCase(ApiDBTestCase):
    """
    The first episode of a production, on its own so that no asset, shot or
    sequence of a fuller fixture set can be picked instead.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()

    def test_the_first_episode_is_the_first_by_name(self):
        self.generate_fixture_episode("E02")
        first = self.generate_fixture_episode("E01")

        episode = shots_service.get_or_create_first_episode(
            str(self.project.id)
        )

        self.assertEqual(episode["id"], str(first.id))

    def test_only_an_episode_can_be_the_first_episode(self):
        # The name is sorted on, and every entity type shares the column: an
        # asset named before the first episode must not be taken for one.
        self.generate_fixture_asset("Aardvark")
        first = self.generate_fixture_episode("E01")

        episode = shots_service.get_or_create_first_episode(
            str(self.project.id)
        )

        self.assertEqual(episode["id"], str(first.id))

    def test_a_production_with_no_episode_gets_one(self):
        episode = shots_service.get_or_create_first_episode(
            str(self.project.id)
        )

        self.assertEqual(episode["name"], "E01")
        self.assertEqual(episode["status"], "running")
        self.assertEqual(
            episode["entity_type_id"], shots_service.get_episode_type()["id"]
        )


class ShotsTestCase(ApiDBTestCase):
    """
    One production holding an episode, a sequence, a shot, a scene and an
    asset: the five kinds this service tells apart.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()
        self.generate_fixture_asset()

    def generate_shot_task(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        return self.generate_fixture_shot_task()


class EntityTypeTestCase(ShotsTestCase):
    """
    Shots, sequences, episodes and scenes are all rows of the entity table:
    only the entity type tells them apart.
    """

    def test_each_temporal_type_is_named_after_itself(self):
        for get_type, name in [
            (shots_service.get_shot_type, "Shot"),
            (shots_service.get_sequence_type, "Sequence"),
            (shots_service.get_episode_type, "Episode"),
            (shots_service.get_scene_type, "Scene"),
            (shots_service.get_edit_type, "Edit"),
        ]:
            with self.subTest(name=name):
                self.assertEqual(get_type()["name"], name)

    def test_an_entity_is_recognized_by_its_type(self):
        entities = {
            "shot": self.shot,
            "sequence": self.sequence,
            "scene": self.scene,
            "episode": self.episode,
            "asset": self.asset,
        }
        predicates = {
            "shot": shots_service.is_shot,
            "sequence": shots_service.is_sequence,
            "scene": shots_service.is_scene,
            "episode": shots_service.is_episode,
        }
        for kind, is_kind in predicates.items():
            for name, entity in entities.items():
                with self.subTest(predicate=kind, entity=name):
                    self.assertEqual(is_kind(entity.serialize()), kind == name)


class LookupTestCase(ShotsTestCase):
    """
    Reading one entity by id, by name or by the id it had on import.
    """

    def test_an_entity_is_read_by_id(self):
        for name, entity, get in [
            ("shot", self.shot, shots_service.get_shot),
            ("sequence", self.sequence, shots_service.get_sequence),
            ("episode", self.episode, shots_service.get_episode),
            ("scene", self.scene, shots_service.get_scene),
        ]:
            with self.subTest(entity=name):
                self.assertEqual(get(entity.id)["id"], str(entity.id))

    def test_an_unknown_id_raises_the_exception_of_its_type(self):
        for name, get, exception in [
            ("shot", shots_service.get_shot, ShotNotFoundException),
            (
                "sequence",
                shots_service.get_sequence,
                SequenceNotFoundException,
            ),
            ("episode", shots_service.get_episode, EpisodeNotFoundException),
            ("scene", shots_service.get_scene, SceneNotFoundException),
        ]:
            with self.subTest(entity=name):
                self.assertRaises(exception, get, fields.gen_uuid())

    def test_an_entity_of_another_type_is_not_found(self):
        """
        The four lookups share a table: asking for the shot of a sequence id
        must miss rather than hand back the sequence.
        """
        self.assertRaises(
            ShotNotFoundException, shots_service.get_shot, self.sequence.id
        )
        self.assertRaises(
            SequenceNotFoundException,
            shots_service.get_sequence,
            self.shot.id,
        )

    def test_a_full_entity_carries_the_names_of_its_parents(self):
        self.generate_shot_task()

        shot = shots_service.get_full_shot(self.shot.id)
        self.assertEqual(shot["sequence_name"], self.sequence.name)
        self.assertEqual(shot["episode_name"], self.episode.name)
        self.assertEqual(len(shot["tasks"]), 1)

        scene = shots_service.get_full_scene(self.scene.id)
        self.assertEqual(scene["sequence_name"], self.sequence.name)
        self.assertEqual(scene["episode_name"], self.episode.name)

        sequence = shots_service.get_full_sequence(self.sequence.id)
        self.assertEqual(sequence["episode_name"], self.episode.name)

        episode = shots_service.get_full_episode(self.episode.id)
        self.assertEqual(episode["project_name"], self.project.name)

    def test_a_shot_leads_to_its_sequence_and_its_episode(self):
        self.assertEqual(
            shots_service.get_sequence_from_shot(self.shot.serialize())[
                "name"
            ],
            "S01",
        )
        self.assertEqual(
            shots_service.get_episode_from_sequence(self.sequence.serialize())[
                "name"
            ],
            "E01",
        )

    def test_a_shot_hanging_from_nothing_leads_to_no_sequence(self):
        orphan = Entity.create(
            name="P01NOSEQ",
            project_id=self.project.id,
            entity_type_id=self.shot_type.id,
        )
        self.assertRaises(
            SequenceNotFoundException,
            shots_service.get_sequence_from_shot,
            orphan,
        )

    def test_an_episode_is_read_by_name_inside_its_production(self):
        """
        Case insensitive, and scoped to the production: two productions may
        both own an E01.
        """
        episode_id = str(self.episode.id)
        self.generate_fixture_project_standard()
        # Same name, other production, created second: asking the lending
        # production must not hand back the first one.
        namesake = self.generate_fixture_episode(
            name="E01", project_id=self.project_standard.id
        )

        self.assertEqual(
            shots_service.get_episode_by_name(self.project.id, "e01")["id"],
            episode_id,
        )
        self.assertEqual(
            shots_service.get_episode_by_name(self.project_standard.id, "e01")[
                "id"
            ],
            str(namesake.id),
        )
        self.assertRaises(
            EpisodeNotFoundException,
            shots_service.get_episode_by_name,
            self.project.id,
            "E02",
        )

    def test_an_entity_is_read_by_the_id_it_had_on_import(self):
        """
        The shotgun id is stored at import time and is the only handle the
        importer has to match a row it already created. Shotgun numbers its
        entities per type, so the same id is given to all four here: the
        entity type is what tells them apart.
        """
        entities = {
            "shot": (self.shot, shots_service.get_shot_by_shotgun_id),
            "scene": (self.scene, shots_service.get_scene_by_shotgun_id),
            "sequence": (
                self.sequence,
                shots_service.get_sequence_by_shotgun_id,
            ),
            "episode": (
                self.episode,
                shots_service.get_episode_by_shotgun_id,
            ),
        }
        for entity, _ in entities.values():
            entity.update({"shotgun_id": 42})
        for name, (entity, getter) in entities.items():
            with self.subTest(entity=name):
                self.assertEqual(getter(42)["id"], str(entity.id))

        self.assertRaises(
            ShotNotFoundException, shots_service.get_shot_by_shotgun_id, 404
        )


class ListingTestCase(ShotsTestCase):
    """
    The listings the production pages are drawn from.
    """

    def test_every_entity_of_a_type_is_listed(self):
        for name, get_all, entity in [
            ("episodes", shots_service.get_episodes, self.episode),
            ("sequences", shots_service.get_sequences, self.sequence),
            ("scenes", shots_service.get_scenes, self.scene),
        ]:
            with self.subTest(listing=name):
                self.assertEqual(
                    [row["id"] for row in get_all()], [str(entity.id)]
                )

    def test_the_shots_are_listed_with_the_names_of_their_parents(self):
        shot_dict = self.shot.serialize(obj_type="Shot")
        shot_dict["project_name"] = self.project.name
        shot_dict["sequence_name"] = self.sequence.name
        # Named to come first while created last, so the listing order is
        # the query's rather than the insertion one.
        self.generate_fixture_shot("A01")

        shots = shots_service.get_shots()

        self.assertEqual([shot["name"] for shot in shots], ["A01", "P01"])
        self.assertDictEqual(shots[1], shot_dict)

    def test_the_episodes_are_listed_by_id(self):
        self.generate_fixture_episode("E02")
        episode_map = shots_service.get_episode_map()
        self.assertEqual(len(episode_map.keys()), 2)
        self.assertEqual(
            episode_map[str(self.episode.id)]["name"], self.episode.name
        )

    def test_the_shots_are_listed_with_their_tasks(self):
        self.generate_shot_task()
        self.generate_fixture_shot_task(name="Secondary")
        self.generate_fixture_shot("P02")

        shots = sorted(
            shots_service.get_shots_and_tasks(), key=lambda s: s["name"]
        )

        self.assertEqual(len(shots), 2)
        self.assertEqual(len(shots[0]["tasks"]), 2)
        self.assertEqual(shots[1]["tasks"], [])
        self.assertEqual(shots[0]["episode_id"], str(self.episode.id))
        self.assertEqual(shots[0]["sequence_id"], str(self.sequence.id))
        self.assertEqual(
            shots[0]["tasks"][0]["assignees"][0], str(self.person.id)
        )
        self.assertEqual(
            shots[0]["tasks"][0]["task_status_id"],
            str(self.shot_task.task_status_id),
        )
        self.assertEqual(
            shots[0]["tasks"][0]["task_type_id"],
            str(self.shot_task.task_type_id),
        )

    def test_the_listings_of_a_production_are_scoped_to_it(self):
        """
        Both listings are scoped to the production, and both answer the
        assigned only variant from the tasks hanging under them.
        """
        episode_id = str(self.episode.id)
        sequence_id = str(self.sequence.id)
        self.generate_shot_task()

        # The other production needs an assigned task of its own, or the
        # assignee filter alone would keep it out and the project filter
        # would have nothing to do.
        self.generate_fixture_project_standard()
        other_episode = self.generate_fixture_episode(
            name="E99", project_id=self.project_standard.id
        )
        other_sequence = self.generate_fixture_sequence(
            name="SQ99",
            project_id=self.project_standard.id,
            episode_id=other_episode.id,
        )
        other_shot = self.generate_fixture_shot(
            "SH99", sequence_id=other_sequence.id
        )
        self.generate_fixture_shot_task(name="other", shot_id=other_shot.id)

        project_id = str(self.project.id)
        self.assertEqual(
            [
                episode["id"]
                for episode in shots_service.get_episodes_for_project(
                    project_id
                )
            ],
            [episode_id],
        )
        self.assertEqual(
            [
                sequence["id"]
                for sequence in shots_service.get_sequences_for_project(
                    project_id
                )
            ],
            [sequence_id],
        )

        # The assigned only variant runs its own queries rather than going
        # through get_entities_for_project, so it needs its own check. The
        # caller comes from the request context, which a service test has
        # none of.
        with patch.object(
            shots_service.user_service,
            "build_assignee_filter",
            return_value=Task.assignees.contains(
                persons_service.get_person_raw(self.person.id)
            ),
        ):
            self.assertEqual(
                [
                    episode["id"]
                    for episode in shots_service.get_episodes_for_project(
                        project_id, only_assigned=True
                    )
                ],
                [episode_id],
            )
            self.assertEqual(
                [
                    sequence["id"]
                    for sequence in shots_service.get_sequences_for_project(
                        project_id, only_assigned=True
                    )
                ],
                [sequence_id],
            )

    def test_the_scenes_of_a_production_are_scoped_to_it(self):
        self.generate_fixture_project_standard()
        self.generate_fixture_scene(
            project_id=self.project_standard.id, sequence_id=self.sequence.id
        )
        self.assertEqual(
            len(shots_service.get_scenes_for_project(self.project.id)), 1
        )

    def test_the_scenes_of_a_sequence_are_scoped_to_it(self):
        """
        Scoped to the sequence and ordered by name, whatever production the
        scenes belong to.
        """
        self.generate_fixture_project_standard()
        self.generate_fixture_sequence_standard()
        self.generate_fixture_sequence(name="SQ02")
        self.generate_fixture_scene(
            name="SC02",
            project_id=self.project_standard.id,
            sequence_id=self.sequence.id,
        )
        self.generate_fixture_scene(
            name="SC01",
            project_id=self.project_standard.id,
            sequence_id=self.sequence.id,
        )

        scenes = shots_service.get_scenes_for_sequence(self.sequence.id)

        self.assertEqual([scene["name"] for scene in scenes], ["SC01", "SC02"])

    def test_the_shots_of_an_episode_are_scoped_to_it(self):
        other_episode = self.generate_fixture_episode("E02")
        other_sequence = self.generate_fixture_sequence(
            name="S02", episode_id=other_episode.id
        )
        self.generate_fixture_shot("P02", sequence_id=other_sequence.id)

        self.assertEqual(
            [
                shot["id"]
                for shot in shots_service.get_shots_for_episode(
                    self.episode.id
                )
            ],
            [str(self.shot.id)],
        )

    def test_every_shot_of_the_instance_is_walked_for_the_index(self):
        # The indexer walks every shot, productions included.
        self.assertEqual(
            [shot.id for shot in shots_service.get_all_raw_shots()],
            [self.shot.id],
        )


class CreationTestCase(ShotsTestCase):
    """
    Creating the four kinds. Each is idempotent on its name inside its
    parent, since the importers replay their rows.
    """

    def test_an_episode_is_created_once_per_name(self):
        episode = shots_service.create_episode(self.project.id, "NE01")
        self.assertEqual(episode["name"], "NE01")
        self.assertEqual(
            shots_service.create_episode(self.project.id, "NE01")["id"],
            episode["id"],
        )

    def test_an_episode_of_an_unknown_status_falls_back_to_running(self):
        self.assertEqual(
            shots_service.create_episode(
                self.project.id, "NE02", status="whatever"
            )["status"],
            "running",
        )

    def test_a_sequence_is_created_under_its_episode(self):
        parent_id = str(self.episode.id)
        sequence = shots_service.create_sequence(
            self.project.id, parent_id, "NSE01"
        )
        self.assertEqual(sequence["name"], "NSE01")
        self.assertEqual(sequence["parent_id"], parent_id)
        self.assertEqual(
            shots_service.create_sequence(self.project.id, parent_id, "NSE01")[
                "id"
            ],
            sequence["id"],
        )

    def test_a_shot_is_created_under_its_sequence(self):
        parent_id = str(self.sequence.id)
        shot = shots_service.create_shot(self.project.id, parent_id, "NSH01")
        self.assertEqual(shot["name"], "NSH01")
        self.assertEqual(shot["parent_id"], parent_id)
        self.assertEqual(
            shots_service.create_shot(self.project.id, parent_id, "NSH01")[
                "id"
            ],
            shot["id"],
        )

    def test_a_shot_can_hang_from_no_sequence(self):
        """
        The route lets the sequence be left out, and a production that has
        not laid out its sequences yet does exactly that.
        """
        shot = shots_service.create_shot(self.project.id, None, "NOSEQ01")

        self.assertEqual(shot["name"], "NOSEQ01")
        self.assertIsNone(shot["parent_id"])

    def test_a_scene_is_created_under_its_sequence(self):
        parent_id = str(self.sequence.id)
        scene = shots_service.create_scene(
            str(self.project.id), parent_id, "NSC01"
        )
        self.assertEqual(scene["name"], "NSC01")
        self.assertEqual(scene["parent_id"], parent_id)

    def test_a_parent_of_another_production_is_refused(self):
        """
        The route checks the caller against the production it names, and
        nothing else: a parent borrowed from elsewhere would put the new
        row under a production the caller was never checked against.
        """
        self.generate_fixture_project_standard()
        other_project_id = str(self.project_standard.id)

        self.assertRaises(
            EpisodeNotFoundException,
            shots_service.create_sequence,
            other_project_id,
            str(self.episode.id),
            "NSE02",
        )
        self.assertRaises(
            SequenceNotFoundException,
            shots_service.create_shot,
            other_project_id,
            str(self.sequence.id),
            "NSH02",
        )
        self.assertRaises(
            SequenceNotFoundException,
            shots_service.create_scene,
            other_project_id,
            str(self.sequence.id),
            "NSC02",
        )

    def test_a_shot_created_twice_at_once_is_created_once(self):
        shot_name = "RACE_SHOT"
        parent_id = str(self.sequence.id)
        shot_type = shots_service.get_shot_type()
        existing = Entity.create(
            entity_type_id=shot_type["id"],
            project_id=self.project.id,
            parent_id=self.sequence.id,
            name=shot_name,
        )
        existing_id = str(existing.id)

        real_get_by = Entity.get_by
        state = {"first_shot_lookup": True, "create_called": False}

        def fake_get_by(**kw):
            if (
                kw.get("name") == shot_name
                and kw.get("entity_type_id") == shot_type["id"]
                and state["first_shot_lookup"]
            ):
                state["first_shot_lookup"] = False
                return None
            return real_get_by(**kw)

        def fake_create(**kw):
            state["create_called"] = True
            raise IntegrityError("INSERT", {}, Exception("duplicate"))

        with (
            patch.object(Entity, "get_by", side_effect=fake_get_by),
            patch.object(Entity, "create", side_effect=fake_create),
        ):
            shot = shots_service.create_shot(
                self.project.id, parent_id, shot_name
            )

        self.assertTrue(state["create_called"])
        self.assertEqual(shot["id"], existing_id)

    def test_a_new_shot_is_announced(self):
        captured = self.capture_events("shot:new")

        shots_service.create_shot(
            self.project.id, str(self.sequence.id), "NSH03"
        )

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["episode_id"], str(self.episode.id))

    def test_an_updated_shot_is_read_back_updated(self):
        shot_id = str(self.shot.id)
        shots_service.get_shot(shot_id)
        captured = self.capture_events("shot:update")

        shots_service.update_shot(shot_id, {"nb_frames": 42})

        self.assertEqual(shots_service.get_shot(shot_id)["nb_frames"], 42)
        self.assertEqual(len(captured), 1)


class RemovalTestCase(ShotsTestCase):
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

        shots_service.remove_shot(shot_id)

        with pytest.raises(ShotNotFoundException):
            shots_service.get_shot(shot_id)
        self.assertEqual(
            EntityLink.query.filter_by(entity_in_id=shot_id).count(), 0
        )

    def test_a_shot_with_tasks_is_canceled(self):
        self.generate_shot_task()
        shot_id = str(self.shot.id)

        shots_service.remove_shot(shot_id)

        self.assertTrue(shots_service.get_shot(shot_id)["canceled"])

    def test_a_forced_removal_takes_the_tasks_with_it(self):
        self.generate_shot_task()
        shot_id = str(self.shot.id)

        shots_service.remove_shot(shot_id, force=True)

        with pytest.raises(ShotNotFoundException):
            shots_service.get_shot(shot_id)
        self.assertEqual(Task.query.filter_by(entity_id=shot_id).count(), 0)

    def test_a_scene_is_deleted(self):
        scene_id = str(self.scene.id)
        shots_service.remove_scene(scene_id)
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
            shots_service.remove_sequence,
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

        shots_service.remove_sequence(sequence_id, force=True)

        with pytest.raises(SequenceNotFoundException):
            shots_service.get_sequence(sequence_id)
        with pytest.raises(ShotNotFoundException):
            shots_service.get_shot(shot_id)
        with pytest.raises(SceneNotFoundException):
            shots_service.get_scene(scene_id)


class QuotaTestCase(ShotsTestCase):
    """
    How much a person drew over a period. Every shot counted lands in four
    buckets at once.
    """

    def test_the_entries_add_up_by_day_week_month_and_year(self):
        """
        Shots sharing a period add up. The entries counters are distinct
        period counts: how many days a month holds, how many weeks and
        months a year does, which is why two days in January are needed to
        tell a sum from an assignment.
        """
        quotas = {}
        counted = [
            (datetime.datetime(2024, 1, 8), 100, 3),
            (datetime.datetime(2024, 1, 8), 50, 2),
            (datetime.datetime(2024, 1, 9), 25, 1),
            (datetime.datetime(2024, 2, 5), 75, 4),
        ]
        for date, nb_frames, nb_drawings in counted:
            shots_service._add_quota_entry(
                quotas, "person", date, "UTC", nb_frames, nb_drawings, 25
            )

        entry = quotas["person"]
        self.assertEqual(
            entry["day"],
            {
                "frames": {
                    "2024-01-08": 150,
                    "2024-01-09": 25,
                    "2024-02-05": 75,
                },
                "seconds": {
                    "2024-01-08": 6,
                    "2024-01-09": 1,
                    "2024-02-05": 3,
                },
                "count": {"2024-01-08": 2, "2024-01-09": 1, "2024-02-05": 1},
                "drawings": {
                    "2024-01-08": 5,
                    "2024-01-09": 1,
                    "2024-02-05": 4,
                },
                "entries": {"2024-01": 2, "2024-02": 1},
            },
        )
        self.assertEqual(
            entry["week"],
            {
                "frames": {"2024-2": 175, "2024-6": 75},
                "seconds": {"2024-2": 7, "2024-6": 3},
                "count": {"2024-2": 3, "2024-6": 1},
                "drawings": {"2024-2": 6, "2024-6": 4},
                "entries": {"2024": 2},
            },
        )
        self.assertEqual(
            entry["month"],
            {
                "frames": {"2024-01": 175, "2024-02": 75},
                "seconds": {"2024-01": 7, "2024-02": 3},
                "count": {"2024-01": 3, "2024-02": 1},
                "drawings": {"2024-01": 6, "2024-02": 4},
                "entries": {"2024": 2},
            },
        )
        self.assertEqual(
            entry["year"],
            {
                "frames": {"2024": 250},
                "seconds": {"2024": 10},
                "count": {"2024": 4},
                "drawings": {"2024": 10},
            },
        )

    def test_a_shot_is_weighted_by_the_share_of_the_task_it_took(self):
        """
        The shots a person worked on in the window, weighted by the share of
        the task duration they logged, and returned in full name order.
        """
        self.generate_shot_task()

        # Named to come first while created last, so the sort has work to
        # do. generate_fixture_shot repoints self.shot, hence the local.
        first_shot = self.shot
        shots = [first_shot, self.generate_fixture_shot("A01")]
        tasks = {}
        for shot in shots:
            task = self.generate_fixture_shot_task(
                name=f"quota {shot.name}", shot_id=shot.id
            )
            task.update({"end_date": fields.get_date_object("2018-06-10")})
            # The task duration is the sum of every time spent on it, so a
            # second worker is what makes the share below one.
            tasks_service.create_or_update_time_spent(
                str(task.id), str(self.person.id), "2018-06-04", 250
            )
            tasks_service.create_or_update_time_spent(
                str(task.id), self.user["id"], "2018-06-04", 750
            )
            tasks[shot.name] = task

        # A second day logged on one shot, for the same duration as the
        # first: the two shares have to add up rather than the last one
        # winning, and the rows must stay apart even though everything the
        # query selects of them is equal.
        tasks_service.create_or_update_time_spent(
            str(tasks["A01"].id), str(self.person.id), "2018-06-05", 250
        )

        quota_shots = shots_service.get_weighted_quota_shots_between(
            str(self.person.id),
            "2018-06-01T00:00:00",
            "2018-06-30T00:00:00",
            project_id=str(self.project.id),
            task_type_id=str(self.task_type_animation.id),
        )

        self.assertEqual(
            [(shot["name"], shot["weight"]) for shot in quota_shots],
            [("A01", 0.4), ("P01", 0.25)],
        )

    def test_a_shot_outside_the_window_is_not_counted(self):
        self.generate_shot_task()
        task = self.generate_fixture_shot_task(
            name="quota", shot_id=self.shot.id
        )
        task.update({"end_date": fields.get_date_object("2018-06-10")})
        tasks_service.create_or_update_time_spent(
            str(task.id), str(self.person.id), "2018-06-04", 250
        )

        self.assertEqual(
            shots_service.get_weighted_quota_shots_between(
                str(self.person.id),
                "2018-07-01T00:00:00",
                "2018-07-30T00:00:00",
                project_id=str(self.project.id),
                task_type_id=str(self.task_type_animation.id),
            ),
            [],
        )


class FramesFromPreviewTestCase(ShotsTestCase):
    """
    Backfilling the frame count of a shot from the movie actually
    delivered on it.
    """

    def test_the_frames_are_read_off_the_last_preview_of_the_task_type(self):
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        project_id = str(self.project.id)
        task_type_id = str(self.task_type_animation.id)
        (
            episode_01,
            episode_02,
            _sequence_01,
            _sequence_02,
            shot_01,
            shot_02,
            shot_03,
            shot_e201,
            *_,
        ) = self.generate_fixture_shot_tasks_and_previews(task_type_id)

        shots_service.set_frames_from_task_type_preview_files(
            project_id, task_type_id, episode_id=episode_01.id
        )

        self.assertEqual(
            3, len(shots_service.get_shots_for_episode(episode_01.id))
        )
        self.assertEqual(
            1, len(shots_service.get_shots_for_episode(episode_02.id))
        )
        # The memoized lookups key on the argument, so a UUID object and
        # its string form are two entries and only the string one is ever
        # dropped: read the way the routes do.
        self.assertEqual(
            shots_service.get_shot(str(shot_01.id))["nb_frames"], 750
        )
        self.assertEqual(
            shots_service.get_shot(str(shot_02.id))["nb_frames"], 500
        )
        self.assertEqual(
            shots_service.get_shot(str(shot_03.id))["nb_frames"], 250
        )
        # Another episode, left alone by the scoped call.
        self.assertEqual(
            shots_service.get_shot(str(shot_e201.id))["nb_frames"], 0
        )

        shots_service.set_frames_from_task_type_preview_files(
            project_id, task_type_id
        )

        self.assertEqual(
            shots_service.get_shot(str(shot_e201.id))["nb_frames"], 1000
        )
