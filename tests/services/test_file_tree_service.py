import copy
import os
import tempfile

from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.services import file_tree_service, files_service
from zou.app.services.exception import (
    MalformedFileTreeException,
    TaskNotFoundException,
    WrongFileTreeFileException,
    WrongPathFormatException,
)


class FileTreeTestCase(ApiDBTestCase):
    """
    One production laid out both ways: an asset under its type, and a shot
    under its sequence in an episode. Every template of the shipped trees
    reads from one of those two branches.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        self.generate_fixture_software()
        self.output_type_materials = files_service.get_or_create_output_type(
            "Materials"
        )
        self.output_type_cache = files_service.get_or_create_output_type(
            "Cache"
        )
        self.output_type_image = files_service.get_or_create_output_type(
            "Images"
        )


class TreeLookupTestCase(FileTreeTestCase):
    """
    Reading a tree, and picking the template of an entity inside it.
    """

    def test_a_shipped_tree_is_read_by_name(self):
        self.assertIsNotNone(
            file_tree_service.get_tree_from_file("simple")["working"]
        )

    def test_a_tree_name_that_is_a_path_is_refused(self):
        # The name reaches this from the request body, and the file content
        # ends up in the response: anything but a plain identifier is out.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as secret:
            secret.write('{"stolen": true}')
        stem = secret.name[: -len(".json")]
        try:
            for tree_name in [
                stem,
                f"../../../../{stem.lstrip('/')}",
                "../../file_trees/simple",
                "",
                None,
            ]:
                with self.subTest(tree_name=tree_name):
                    self.assertRaises(
                        WrongFileTreeFileException,
                        file_tree_service.get_tree_from_file,
                        tree_name,
                    )
        finally:
            os.remove(secret.name)

    def test_the_tree_of_a_production_is_read_off_the_production(self):
        self.assertIsNotNone(
            file_tree_service.get_tree_from_project(self.project.serialize())[
                "working"
            ]
        )

    def test_the_production_of_an_entity_is_read_off_the_entity(self):
        project = file_tree_service.get_project(self.asset.serialize())
        self.assertEqual(project["name"], self.project.name)

    def test_the_root_path_is_the_mountpoint_and_the_root(self):
        tree = file_tree_service.get_tree_from_file("simple")
        self.assertEqual(
            file_tree_service.get_root_path(tree, "working", "/"),
            "/simple/productions/",
        )
        self.assertEqual(
            file_tree_service.get_root_path(tree, "working", "\\"),
            "/simple\\productions\\",
        )

    def test_a_mode_with_no_root_stops_at_the_mountpoint(self):
        tree = copy.deepcopy(file_tree_service.get_tree_from_file("simple"))
        tree["working"]["root"] = ""
        self.assertEqual(
            file_tree_service.get_root_path(tree, "working", "/"), "/simple/"
        )

    def test_a_tree_that_cannot_serve_the_mode_is_malformed(self):
        tree = copy.deepcopy(file_tree_service.get_tree_from_file("simple"))
        del tree["working"]["mountpoint"]
        for bad_tree, mode in [
            (None, "working"),
            ({}, "working"),
            (tree, "unknown"),
            (tree, "working"),
        ]:
            with self.subTest(mode=mode):
                self.assertRaises(
                    MalformedFileTreeException,
                    file_tree_service.get_root_path,
                    bad_tree,
                    mode,
                    "/",
                )

    def test_the_template_lookup_follows_the_entity_type(self):
        """
        Both lookups read their section of the tree keyed by the kind of
        entity: a shot reads "shot", an asset "asset", a sequence
        "sequence".
        """
        lookups = {
            "file_name": ("default", file_tree_service.get_file_name_template),
            "folder_path": (
                "simple",
                file_tree_service.get_folder_path_template,
            ),
        }
        entities = {
            "shot": self.shot,
            "asset": self.asset,
            "sequence": self.sequence,
            "scene": self.scene,
            "episode": self.episode,
        }
        for section, (tree_name, get_template) in lookups.items():
            tree = file_tree_service.get_tree_from_file(tree_name)
            for kind, entity in entities.items():
                with self.subTest(section=section, kind=kind):
                    self.assertEqual(
                        get_template(tree, "working", entity.serialize()),
                        tree["working"][section][kind],
                    )

    def test_an_instance_reads_the_template_of_its_own_kind(self):
        """
        An instance sitting in a temporal entity and an instance sitting in
        an asset are two layouts, told apart by the asset the instance
        targets.
        """
        self.generate_fixture_scene_asset_instance()
        tree = file_tree_service.get_tree_from_file("simple")
        instance = self.asset_instance.serialize()

        self.assertEqual(
            file_tree_service.get_folder_path_template(
                tree, "output", instance
            ),
            tree["output"]["folder_path"]["instance"],
        )
        instance["target_asset_id"] = str(self.asset.id)
        self.assertEqual(
            file_tree_service.get_folder_path_template(
                tree, "output", instance
            ),
            tree["output"]["folder_path"]["instance_asset"],
        )

    def test_a_tree_missing_the_template_of_a_kind_is_malformed(self):
        tree = copy.deepcopy(file_tree_service.get_tree_from_file("simple"))
        del tree["working"]["folder_path"]["shot"]
        self.assertRaises(
            MalformedFileTreeException,
            file_tree_service.get_folder_path_template,
            tree,
            "working",
            self.shot.serialize(),
        )


class TokenTestCase(FileTreeTestCase):
    """
    The dispatch every template rests on: one <Token> in, one folder name
    out.
    """

    def test_every_token_the_templates_accept_is_resolved(self):
        """
        One row per token, so a token absent from this table is a token
        nothing exercises.
        """
        shot = self.shot.serialize()
        sequence = self.sequence.serialize()
        asset = self.asset.serialize()
        task = self.task.serialize()
        shot_task = self.shot_task.serialize()
        cases = [
            (
                "Project",
                {"entity": shot, "task": shot_task},
                self.project.name,
            ),
            ("Shot", {"entity": shot, "task": shot_task}, self.shot.name),
            (
                "Sequence",
                {"entity": shot, "task": shot_task},
                self.sequence.name,
            ),
            (
                "Sequence",
                {"entity": sequence, "task": shot_task},
                self.sequence.name,
            ),
            ("Sequence", {"entity": asset}, ""),
            ("Episode", {"entity": shot, "task": task}, "E01"),
            ("Episode", {"entity": sequence, "task": task}, "E01"),
            ("Episode", {"entity": self.episode.serialize()}, "E01"),
            # An asset leads to no episode: a flat production writes e001.
            ("Episode", {"entity": asset}, "e001"),
            ("Asset", {"entity": asset, "task": task}, self.asset.name),
            ("Asset", {"entity": None}, ""),
            (
                "AssetType",
                {"entity": asset, "task": task},
                self.asset_type.name,
            ),
            (
                "Department",
                {"entity": asset, "task": task},
                self.department.name,
            ),
            ("Department", {"entity": asset}, ""),
            ("Task", {"entity": asset, "task": task}, self.task.name),
            ("TaskType", {"entity": asset, "task": task}, self.task_type.name),
            (
                "TaskType",
                {"entity": asset, "task_type": self.task_type.serialize()},
                self.task_type.name,
            ),
            ("TaskType", {"entity": asset}, ""),
            (
                "Software",
                {"entity": asset, "software": self.software.serialize()},
                "Blender",
            ),
            (
                "OutputType",
                {"entity": asset, "output_type": self.output_type_cache},
                "cache",
            ),
            ("TemporalEntity", {"entity": shot}, self.shot.name),
            ("TemporalEntityType", {"entity": shot}, "shot"),
            ("Scene", {"entity": self.scene.serialize()}, self.scene.name),
            ("Scene", {"entity": None}, ""),
            ("Instance", {"asset_instance": None}, ""),
            ("Representation", {"representation": "obj"}, "obj"),
            ("Name", {"name": "main"}, "main"),
            ("OutputFile", {"name": "main"}, "main"),
            ("WorkingFile", {"name": "main"}, "main"),
            ("Version", {"revision": 7}, "007"),
            ("Revision", {"revision": 7}, "007"),
        ]
        for datatype, kwargs, expected in cases:
            with self.subTest(datatype=datatype, kwargs=sorted(kwargs)):
                self.assertEqual(
                    file_tree_service.get_folder_from_datatype(
                        datatype, **kwargs
                    ),
                    expected,
                )

    def test_a_missing_output_type_or_software_falls_back(self):
        """
        A template asking for one when the caller gave none must still
        render: the fallbacks are created on the fly.
        """
        self.assertEqual(
            file_tree_service.get_folder_from_datatype("OutputType"),
            "geometry",
        )
        self.assertEqual(
            file_tree_service.get_folder_from_datatype("Software"), "3dsmax"
        )

    def test_a_token_naming_no_entity_is_malformed(self):
        for datatype, kwargs in [
            ("Unknown", {"entity": self.asset.serialize()}),
            ("TemporalEntity", {"entity": None}),
            ("TemporalEntityType", {"entity": None}),
            ("AssetType", {"entity": None}),
        ]:
            with self.subTest(datatype=datatype):
                self.assertRaises(
                    MalformedFileTreeException,
                    file_tree_service.get_folder_from_datatype,
                    datatype,
                    **kwargs,
                )

    def test_a_sequence_named_after_its_number_is_normalized(self):
        """
        Seq2 and Seq02 name the same sequence to a human, so both land in
        the same folder.
        """
        for name, expected in [("Seq2", "S002"), ("Seq02", "S002")]:
            with self.subTest(name=name):
                sequence = self.generate_fixture_sequence(name=name)
                self.assertEqual(
                    file_tree_service.get_folder_from_datatype(
                        "Sequence", entity=sequence.serialize()
                    ),
                    expected,
                )

    def test_an_instance_falls_back_to_its_number(self):
        instance = {"number": 3, "name": None}
        self.assertEqual(
            file_tree_service.get_folder_from_asset_instance(instance, "name"),
            "0003",
        )
        self.assertEqual(
            file_tree_service.get_folder_from_asset_instance(
                {"number": 3, "name": "hero"}, "name"
            ),
            "hero",
        )
        self.assertEqual(
            file_tree_service.get_folder_from_asset_instance(
                {"number": 3, "name": "hero"}, "number"
            ),
            "0003",
        )

    def test_a_token_is_replaced_by_its_styled_value(self):
        self.assertEqual(
            file_tree_service.update_variable(
                "<AssetType>_<Asset>",
                asset=self.asset.serialize(),
                task=self.task.serialize(),
            ),
            "props_tree",
        )

    def test_a_token_can_name_the_field_it_reads(self):
        self.assertEqual(
            file_tree_service.update_variable(
                "<TaskType.short_name>",
                asset=self.asset.serialize(),
                task=self.task.serialize(),
            ),
            "shd",
        )

    def test_a_field_the_templates_do_not_allow_falls_back_to_the_name(self):
        """
        The field comes from the template, which comes from the client on
        the set-file-tree route: only the four listed fields are read.
        """
        self.assertEqual(
            file_tree_service.update_variable(
                "<TaskType.description>",
                task_type=self.task_type.serialize(),
            ),
            file_tree_service.update_variable(
                "<TaskType>", task_type=self.task_type.serialize()
            ),
        )

    def test_an_id_is_kept_verbatim(self):
        """
        Slugifying an id would lowercase and cut it: it has to come out of
        the template still usable as an id.
        """
        self.assertEqual(
            file_tree_service.update_variable(
                "<Asset.id>", asset=self.asset.serialize()
            ),
            str(self.asset.id),
        )
        # Rendering the whole name slugifies it and applies the style of
        # the tree: the id has to come through both untouched.
        tree = copy.deepcopy(file_tree_service.get_tree_from_file("simple"))
        tree["working"]["file_name"]["asset"] = "<Asset>_<Asset.id>_v<Version>"
        self.assertEqual(
            file_tree_service.get_file_name_root(
                tree,
                "working",
                entity=self.asset.serialize(),
                task=self.task.serialize(),
            ),
            f"tree_{self.asset.id}_v001",
        )


class WorkingPathTestCase(FileTreeTestCase):
    """
    The path a DCC saves its working file at.
    """

    def test_the_path_of_an_asset_task(self):
        self.assertEqual(
            file_tree_service.get_working_file_path(
                self.task.serialize(),
                software=self.software.serialize(),
                revision=3,
            ),
            "/simple/productions/cosmos_landromat/assets/props/tree/shaders/"
            "blender/cosmos_landromat_props_tree_shaders_v003",
        )

    def test_the_path_of_a_shot_task(self):
        self.assertEqual(
            file_tree_service.get_working_folder_path(
                self.shot_task.serialize(),
                software=self.software_max.serialize(),
            ),
            "/simple/productions/cosmos_landromat/shots/s01/p01/animation/"
            "3dsmax",
        )
        self.assertEqual(
            file_tree_service.get_working_file_name(
                self.shot_task.serialize(), revision=3
            ),
            "cosmos_landromat_s01_p01_animation_v003",
        )

    def test_the_path_of_a_scene_task(self):
        scene_task = self.generate_fixture_scene_task()
        self.assertEqual(
            file_tree_service.get_working_file_path(
                scene_task.serialize(),
                software=self.software_max.serialize(),
                revision=3,
            ),
            "/simple/productions/cosmos_landromat/scenes/s01/sc01/animation/"
            "3dsmax/cosmos_landromat_sc01_animation_v003",
        )

    def test_the_separator_of_the_target_platform_is_used_throughout(self):
        self.assertEqual(
            file_tree_service.get_working_folder_path(
                self.shot_task.serialize(),
                software=self.software_max.serialize(),
                sep="\\",
            ),
            "/simple\\productions\\cosmos_landromat\\shots\\s01\\p01\\"
            "animation\\3dsmax",
        )


class OutputPathTestCase(FileTreeTestCase):
    """
    The path a publish lands at. It starts from the entity, not from a
    task: an output file belongs to the entity and carries its task type.
    """

    def test_the_path_of_a_shot_output(self):
        self.assertEqual(
            file_tree_service.get_output_file_path(
                self.shot.serialize(),
                output_type=self.output_type_cache,
                task_type=self.task_type_animation.serialize(),
                name="main",
                revision=3,
                sep="/",
            ),
            "/simple/productions/export/cosmos_landromat/shots/s01/p01/"
            "animation/cache/"
            "cosmos_landromat_s01_p01_animation_cache_main_v003",
        )

    def test_the_folder_of_a_shot_output(self):
        self.assertEqual(
            file_tree_service.get_output_folder_path(
                self.shot.serialize(),
                output_type=self.output_type_cache,
                task_type=self.task_type_animation.serialize(),
                sep="/",
            ),
            "/simple/productions/export/cosmos_landromat/shots/s01/p01/"
            "animation/cache",
        )

    def test_the_name_of_an_asset_output(self):
        self.assertEqual(
            file_tree_service.get_output_file_name(
                self.asset.serialize(), name="main", revision=3
            ),
            "cosmos_landromat_props_tree_geometry_main_v003",
        )

    def test_an_output_covering_several_elements_carries_the_range(self):
        """
        The _[1-N] suffix is the notation the DCCs expand into one file per
        element.
        """
        self.assertEqual(
            file_tree_service.get_output_file_name(
                self.shot.serialize(),
                name="main",
                revision=3,
                output_type=self.output_type_image,
                nb_elements=50,
            ),
            "cosmos_landromat_s01_p01_images_main_v003_[1-50]",
        )
        self.assertEqual(
            file_tree_service.get_output_file_name(
                self.shot.serialize(),
                name="main",
                revision=3,
                output_type=self.output_type_image,
                nb_elements=1,
            ),
            "cosmos_landromat_s01_p01_images_main_v003",
        )


class InstancePathTestCase(FileTreeTestCase):
    """
    The path of what an instance of an asset publishes. The asset comes
    from the instance, the production from the entity it sits in.
    """

    def test_an_instance_in_a_shot(self):
        self.generate_fixture_scene_asset_instance()
        self.generate_fixture_shot_asset_instance(
            self.shot, self.asset_instance
        )
        self.assertEqual(
            file_tree_service.get_instance_folder_path(
                self.asset_instance.serialize(),
                self.shot.serialize(),
                output_type=self.output_type_cache,
                task_type=self.task_type_animation.serialize(),
                representation="abc",
            ),
            "/simple/productions/export/cosmos_landromat/shot/s01/p01/"
            "animation/cache/props/tree/instance_0001/abc",
        )
        self.assertEqual(
            file_tree_service.get_instance_file_name(
                self.asset_instance.serialize(),
                self.shot.serialize(),
                output_type=self.output_type_cache,
                task_type=self.task_type_animation.serialize(),
                name="main",
                revision=3,
            ),
            "cosmos_landromat_s01_p01_animation_cache_main_tree_0001_v003",
        )

    def test_an_instance_in_a_scene(self):
        self.generate_fixture_scene_asset_instance()
        self.assertEqual(
            file_tree_service.get_instance_folder_path(
                self.asset_instance.serialize(),
                self.scene.serialize(),
                task_type=self.task_type_animation.serialize(),
                output_type=self.output_type_cache,
                representation="abc",
            ),
            "/simple/productions/export/cosmos_landromat/scene/s01/sc01/"
            "animation/cache/props/tree/instance_0001/abc",
        )
        self.assertEqual(
            file_tree_service.get_instance_file_name(
                self.asset_instance.serialize(),
                self.scene.serialize(),
                output_type=self.output_type_cache,
                task_type=self.task_type_animation.serialize(),
                name="main",
                revision=3,
            ),
            "cosmos_landromat_s01_sc01_animation_cache_main_tree_0001_v003",
        )

    def test_an_instance_in_an_asset(self):
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()
        self.generate_fixture_asset_asset_instance()
        self.assertEqual(
            file_tree_service.get_instance_folder_path(
                self.asset_instance.serialize(),
                self.asset.serialize(),
                task_type=self.task_type.serialize(),
                output_type=self.output_type_materials,
                representation="ml",
            ),
            "/simple/productions/export/cosmos_landromat/assets/props/tree/"
            "shaders/materials/character/rabbit/instance_0001/ml",
        )
        self.assertEqual(
            file_tree_service.get_instance_file_name(
                self.asset_instance.serialize(),
                self.asset.serialize(),
                output_type=self.output_type_materials,
                task_type=self.task_type.serialize(),
                name="main",
                revision=3,
            ),
            "cosmos_landromat_props_tree_shaders_materials_main_"
            "rabbit_0001_v003",
        )


class PathToTaskTestCase(FileTreeTestCase):
    """
    The other direction: a path a DCC hands over, and the task it points
    at.
    """

    def test_an_asset_path_resolves_to_its_task(self):
        task = file_tree_service.get_asset_task_from_path(
            "/simple/productions/cosmos_landromat/assets/Props/Tree/Shaders/"
            "blender",
            self.project.serialize(),
        )
        self.assertEqual(task["id"], str(self.task.id))

    def test_a_shot_path_resolves_to_its_task(self):
        # The tokens are matched against entity names as they are stored,
        # not against the lowercase style the templates render paths with.
        # The shot template carries no <Episode> token, so the sequence is
        # looked up with no parent: only a flat production resolves.
        sequence = Entity.create(
            name="Seq1",
            project_id=self.project.id,
            entity_type_id=self.sequence_type.id,
        )
        shot = Entity.create(
            name="P002",
            project_id=self.project.id,
            entity_type_id=self.shot_type.id,
            parent_id=sequence.id,
        )
        shot_task = self.generate_fixture_shot_task(
            name="main", shot_id=shot.id
        )

        task = file_tree_service.get_shot_task_from_path(
            "/simple/productions/cosmos_landromat/shots/Seq1/P002/Animation/"
            "max",
            self.project.serialize(),
        )
        self.assertEqual(task["id"], str(shot_task.id))

    def test_a_path_of_another_shape_is_refused(self):
        for path in [
            "/simple/productions/cosmos_landromat/shots/S01/P01",
            "/simple/productions/cosmos_landromat/shots/S01/P01/A/B/C",
        ]:
            with self.subTest(path=path):
                self.assertRaises(
                    WrongPathFormatException,
                    file_tree_service.get_shot_task_from_path,
                    path,
                    self.project.serialize(),
                )

    def test_a_path_naming_no_task_type_is_refused(self):
        """
        Every token of the path comes from a client: one that matches
        nothing is a malformed path, not a crash.
        """
        self.assertRaises(
            WrongPathFormatException,
            file_tree_service.get_asset_task_from_path,
            "/simple/productions/cosmos_landromat/assets/Props/Tree/Nowhere/"
            "blender",
            self.project.serialize(),
        )

    def test_a_path_whose_task_does_not_exist_yet_is_reported(self):
        self.generate_fixture_asset(name="Rock")
        self.assertRaises(
            TaskNotFoundException,
            file_tree_service.get_asset_task_from_path,
            "/simple/productions/cosmos_landromat/assets/Props/Rock/Shaders/"
            "blender",
            self.project.serialize(),
        )

    def test_a_token_is_read_without_its_prefix_and_suffix(self):
        """
        A template element may wrap its token, as `v<Version>` does: only
        the value is kept.
        """
        self.assertEqual(
            file_tree_service.extract_variable_values_from_path(
                ["cosmos_landromat", "shots", "v003"],
                ["<Project>", "shots", "v<Version>"],
            ),
            {"Project": "cosmos landromat", "Version": "003"},
        )

    def test_a_fixed_element_that_differs_is_refused(self):
        self.assertRaises(
            WrongPathFormatException,
            file_tree_service.extract_variable_values_from_path,
            ["cosmos_landromat", "assets"],
            ["<Project>", "shots"],
        )


class GuessFromPathTestCase(FileTreeTestCase):
    """
    The route a DCC calls to find out what a path it holds stands for. It
    returns one entry per template of the tree, filled left to right and
    stopping at the first token that resolves to nothing.
    """

    def guess(self, path, project=None, sep="/"):
        matches = file_tree_service.guess_from_path(
            str((project or self.project).id), path, sep=sep
        )
        return {match["Template"]: match for match in matches}

    def test_an_asset_path_is_resolved_down_to_its_task_type(self):
        matches = self.guess(
            "/simple/productions/cosmos landromat/assets/props/tree/shaders/"
            "blender"
        )
        self.assertEqual(
            matches["asset"],
            {
                "Template": "asset",
                "Project": str(self.project.id),
                "AssetType": str(self.asset_type.id),
                "Asset": str(self.asset.id),
                "TaskType": str(self.task_type.id),
            },
        )

    def test_a_shot_path_is_resolved_down_to_its_task_type(self):
        """
        The shipped templates carry no <Episode> token: requiring one to
        resolve a sequence left every shot path stopping at the production.
        """
        matches = self.guess(
            "/simple/productions/cosmos landromat/shots/s01/p01/animation/max"
        )
        self.assertEqual(
            matches["shot"],
            {
                "Template": "shot",
                "Project": str(self.project.id),
                "Sequence": str(self.sequence.id),
                "Shot": str(self.shot.id),
                "TaskType": str(self.task_type_animation.id),
            },
        )

    def test_a_scene_path_is_resolved_down_to_its_scene(self):
        matches = self.guess(
            "/simple/productions/cosmos landromat/scenes/s01/sc01/animation/"
            "max"
        )
        self.assertEqual(matches["scene"]["Scene"], str(self.scene.id))

    def test_an_episode_narrows_the_sequence_when_the_path_carries_one(self):
        """
        Two episodes may hold a sequence of the same name, and then the
        episode is the only thing telling them apart.
        """
        other_episode = self.generate_fixture_episode(name="E02")
        other_sequence = self.generate_fixture_sequence(
            name="S01", episode_id=other_episode.id
        )
        project = self.project
        tree = copy.deepcopy(project.file_tree)
        tree["working"]["folder_path"][
            "shot"
        ] = "<Project>/<Episode>/<Sequence>/<Shot>"
        project.update({"file_tree": tree})

        matches = self.guess(
            "/simple/productions/cosmos landromat/e02/s01/p01"
        )

        self.assertEqual(matches["shot"]["Sequence"], str(other_sequence.id))

    def test_a_path_of_another_production_resolves_to_nothing(self):
        """
        The permission was checked against the production the caller named:
        a path naming another one must not come back carrying its ids.
        """
        self.generate_fixture_project_standard()

        matches = file_tree_service.guess_from_path(
            str(self.project_standard.id),
            "/simple/productions/cosmos landromat/assets/props/tree/shaders/"
            "blender",
        )

        self.assertEqual(
            [set(match) for match in matches],
            [{"Template"} for _ in matches],
        )

    def test_a_path_outside_the_root_resolves_to_nothing(self):
        self.assertEqual(
            file_tree_service.guess_from_path(
                str(self.project.id), "/elsewhere/cosmos landromat/assets"
            ),
            [],
        )


class HelpersTestCase(ApiDBTestCase):
    """
    The string helpers the rendering is built on.
    """

    def test_a_path_is_joined_without_an_empty_element(self):
        self.assertEqual(file_tree_service.join_path("", "PROD"), "PROD")
        self.assertEqual(file_tree_service.join_path("ROOT", ""), "ROOT")
        self.assertEqual(
            file_tree_service.join_path("ROOT", "PROD"), "ROOT/PROD"
        )
        self.assertEqual(
            file_tree_service.join_path("ROOT", "PROD", "\\"), "ROOT\\PROD"
        )

    def test_the_separators_of_a_template_are_rewritten(self):
        self.assertEqual(
            file_tree_service.change_folder_path_separators(
                "/simple/big_buck_bunny/props", "\\"
            ),
            "\\simple\\big_buck_bunny\\props",
        )

    def test_the_style_of_a_tree_is_applied(self):
        self.assertEqual(
            file_tree_service.apply_style("Shaders", "uppercase"), "SHADERS"
        )
        self.assertEqual(
            file_tree_service.apply_style("Shaders", "lowercase"), "shaders"
        )
        # Anything else is how a tree opts out.
        self.assertEqual(
            file_tree_service.apply_style("Shaders", ""), "Shaders"
        )
