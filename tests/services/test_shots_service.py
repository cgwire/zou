import datetime

from unittest.mock import patch

from sqlalchemy.exc import IntegrityError

from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity, EntityVersion
from zou.app.models.task import Task
from zou.app.services import (
    persons_service,
    shots_service,
    entity_types_service,
)
from zou.app.utils import fields
from zou.app.exceptions import (
    EpisodeNotFoundException,
    SceneNotFoundException,
    ShotNotFoundException,
    SequenceNotFoundException,
)
from tests.services.cases import ShotsTestCase


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
            episode["entity_type_id"],
            entity_types_service.get_episode_type()["id"],
        )


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
            orphan.serialize(),
        )

    def test_a_sequence_outside_any_episode_leads_to_no_episode(self):
        # Entity.get(None) returns None rather than raising, so the missing
        # parent used to surface as an AttributeError.
        flat = Entity.create(
            name="SQFLAT",
            project_id=self.project.id,
            entity_type_id=self.sequence_type.id,
        )
        self.assertRaises(
            EpisodeNotFoundException,
            shots_service.get_episode_from_sequence,
            flat.serialize(),
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
            persons_service,
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
        shot_type = entity_types_service.get_shot_type()
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


class VersionTestCase(ShotsTestCase):
    """
    The versions recorded when the frame range or the name of a shot
    changes.
    """

    def test_an_unversioned_shot_has_no_last_version(self):
        self.assertIsNone(
            shots_service.get_last_shot_version_raw(self.shot.id)
        )

    def test_the_last_version_is_the_most_recent_one(self):
        # Created out of order, so that neither the insertion order nor an
        # ascending sort gives the expected version.
        for day, frame_out in [(8, 110), (10, 130), (9, 120)]:
            EntityVersion.create(
                entity_id=self.shot.id,
                name=self.shot.name,
                data={"frame_out": frame_out},
                created_at=datetime.datetime(2024, 1, day),
            )
        version = shots_service.get_last_shot_version_raw(self.shot.id)
        self.assertEqual(version.data["frame_out"], 130)
