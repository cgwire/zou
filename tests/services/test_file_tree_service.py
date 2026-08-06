import os
import tempfile

from tests.base import ApiDBTestCase

from zou.app.services import file_tree_service, files_service
from zou.app.services.exception import (
    MalformedFileTreeException,
    WrongFileTreeFileException,
    WrongPathFormatException,
)

from zou.app.models.entity import Entity


class FileTreeTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_project_standard()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()
        self.generate_fixture_sequence_standard()
        self.generate_fixture_shot_standard()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        self.generate_fixture_shot_task_standard()
        self.generate_fixture_software()
        self.asset_standard = Entity(
            name="Car",
            project_id=self.project_standard.id,
            entity_type_id=self.asset_type.id,
        )
        self.asset_standard.save()
        self.sequence_standard = Entity(
            name="Seq1",
            project_id=self.project.id,
            entity_type_id=self.sequence_type.id,
        )
        self.sequence_standard.save()
        self.shot_standard = Entity(
            name="P001",
            project_id=self.project_standard.id,
            entity_type_id=self.shot_type.id,
            parent_id=self.sequence_standard.id,
        )
        self.shot_standard.save()
        self.output_type_materials = files_service.get_or_create_output_type(
            "Materials"
        )
        self.output_type_cache = files_service.get_or_create_output_type(
            "Cache"
        )
        self.output_type_image = files_service.get_or_create_output_type(
            "Images"
        )

    def test_get_tree_from_file(self):
        simple_tree = file_tree_service.get_tree_from_file("simple")
        self.assertIsNotNone(simple_tree["working"])

    def test_get_tree_from_file_rejects_a_path(self):
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
                with self.assertRaises(WrongFileTreeFileException):
                    file_tree_service.get_tree_from_file(tree_name)
        finally:
            os.remove(secret.name)

    def test_get_tree_from_project(self):
        simple_tree = file_tree_service.get_tree_from_project(
            self.project.serialize()
        )
        self.assertIsNotNone(simple_tree["working"])

    def test_join_path(self):
        self.assertEqual(file_tree_service.join_path("", "PROD"), "PROD")
        self.assertEqual(
            file_tree_service.join_path("ROOT", "PROD"), "ROOT/PROD"
        )
        self.assertEqual(
            file_tree_service.join_path("ROOT", "PROD", "\\"), "ROOT\\PROD"
        )

    def test_get_root_path(self):
        tree = file_tree_service.get_tree_from_file("simple")
        path = file_tree_service.get_root_path(tree, "working", "/")
        self.assertEqual(path, "/simple/productions/")

    def test_get_project(self):
        project = file_tree_service.get_project(self.asset.serialize())
        self.assertEqual(project["name"], self.project.name)

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
        }
        for section, (tree_name, get_template) in lookups.items():
            tree = file_tree_service.get_tree_from_file(tree_name)
            for kind, entity in entities.items():
                with self.subTest(section=section, kind=kind):
                    self.assertEqual(
                        get_template(tree, "working", entity.serialize()),
                        tree["working"][section][kind],
                    )

    def test_get_folder_from_datatype(self):
        """
        The dispatch every file tree template rests on: one row per token the
        templates accept, so a token absent from this table is a token
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
            ("Episode", {"entity": shot, "task": task}, "E01"),
            ("Episode", {"entity": sequence, "task": task}, "E01"),
            ("Asset", {"entity": asset, "task": task}, self.asset.name),
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
            ("Task", {"entity": asset, "task": task}, self.task.name),
            ("TaskType", {"entity": asset, "task": task}, self.task_type.name),
            (
                "TaskType",
                {"entity": asset, "task_type": self.task_type.serialize()},
                self.task_type.name,
            ),
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

    def test_get_folder_raise_exception(self):
        self.assertRaises(
            MalformedFileTreeException,
            file_tree_service.get_folder_from_datatype,
            "Unknown",
            self.asset.serialize(),
            self.task.serialize(),
        )

    def test_get_working_folder_path_shot(self):
        path = file_tree_service.get_working_folder_path(
            self.shot_task.serialize(), software=self.software_max.serialize()
        )
        self.assertEqual(
            path,
            "/simple/productions/cosmos_landromat/shots/s01/p01/animation/"
            "3dsmax",
        )

    def test_get_working_folder_path_with_separator(self):
        path = file_tree_service.get_working_folder_path(
            self.shot_task.serialize(),
            software=self.software_max.serialize(),
            sep="\\",
        )
        self.assertEqual(
            path,
            "/simple\\productions\\cosmos_landromat\\shots\\s01\\p01\\"
            "animation\\3dsmax",
        )

    def test_get_output_folder_path(self):
        path = file_tree_service.get_output_folder_path(
            self.shot.serialize(),
            output_type=self.output_type_cache,
            task_type=self.task_type_animation.serialize(),
            sep="/",
        )
        self.assertEqual(
            path,
            "/simple/productions/export/cosmos_landromat/shots/s01/p01/"
            "animation/cache",
        )

    def test_get_working_folder_path_with_software(self):
        path = file_tree_service.get_working_folder_path(
            self.task.serialize(), software=self.software.serialize()
        )
        self.assertEqual(
            path,
            "/simple/productions/cosmos_landromat/assets/props/tree/shaders/"
            "blender",
        )

    def test_get_working_file_name_asset(self):
        file_name = file_tree_service.get_working_file_name(
            self.task.serialize(), revision=3
        )
        self.assertEqual(file_name, "cosmos_landromat_props_tree_shaders_v003")

    def test_get_output_file_name_asset(self):
        file_name = file_tree_service.get_output_file_name(
            self.asset.serialize(), name="main", revision=3
        )
        self.assertEqual(
            file_name, "cosmos_landromat_props_tree_geometry_main_v003"
        )

    def test_get_output_file_name_shot_image_sequence(self):
        file_name = file_tree_service.get_output_file_name(
            self.shot.serialize(),
            name="main",
            revision=3,
            output_type=self.output_type_image,
            nb_elements=50,
        )
        self.assertEqual(
            file_name, "cosmos_landromat_s01_p01_images_main_v003_[1-50]"
        )

    def test_get_working_file_name_shot(self):
        file_name = file_tree_service.get_working_file_name(
            self.shot_task.serialize(), revision=3
        )
        self.assertEqual(file_name, "cosmos_landromat_s01_p01_animation_v003")

    def test_get_working_file_path_asset(self):
        file_name = file_tree_service.get_working_file_path(
            self.task.serialize(),
            software=self.software.serialize(),
            revision=3,
        )
        self.assertEqual(
            file_name,
            "/simple/productions/cosmos_landromat/assets/props/tree/shaders/"
            "blender/"
            "cosmos_landromat_props_tree_shaders_v003",
        )

    def test_get_file_path_scene(self):
        scene_task = self.generate_fixture_scene_task()
        file_name = file_tree_service.get_working_file_path(
            scene_task.serialize(),
            software=self.software_max.serialize(),
            revision=3,
        )
        self.assertEqual(
            file_name,
            "/simple/productions/cosmos_landromat/scenes/s01/sc01/animation/"
            "3dsmax/"
            "cosmos_landromat_sc01_animation_v003",
        )

    def test_get_folder_path_shot_asset_instance(self):
        self.generate_fixture_scene_asset_instance()
        self.generate_fixture_shot_asset_instance(
            self.shot, self.asset_instance
        )
        path = file_tree_service.get_instance_folder_path(
            self.asset_instance.serialize(),
            self.shot.serialize(),
            output_type=self.output_type_cache,
            task_type=self.task_type_animation.serialize(),
            representation="abc",
        )
        self.assertEqual(
            path,
            "/simple/productions/export/cosmos_landromat/shot/s01/p01/"
            "animation/cache/props/tree/instance_0001/abc",
        )

    def test_get_file_name_shot_asset_instance(self):
        self.generate_fixture_scene_asset_instance()
        self.generate_fixture_shot_asset_instance(
            self.shot, self.asset_instance
        )
        file_name = file_tree_service.get_instance_file_name(
            self.asset_instance.serialize(),
            self.shot.serialize(),
            output_type=self.output_type_cache,
            task_type=self.task_type_animation.serialize(),
            name="main",
            revision=3,
        )
        self.assertEqual(
            file_name,
            "cosmos_landromat_s01_p01_animation_cache_main" "_tree_0001_v003",
        )

    def test_get_folder_path_scene_asset_instance(self):
        self.generate_fixture_scene_asset_instance()
        path = file_tree_service.get_instance_folder_path(
            self.asset_instance.serialize(),
            self.scene.serialize(),
            task_type=self.task_type_animation.serialize(),
            output_type=self.output_type_cache,
            representation="abc",
        )
        self.assertEqual(
            path,
            "/simple/productions/export/cosmos_landromat/scene/s01/sc01/"
            "animation/cache/props/tree/instance_0001/abc",
        )

    def test_get_file_name_scene_asset_instance(self):
        self.generate_fixture_scene_asset_instance()
        file_name = file_tree_service.get_instance_file_name(
            self.asset_instance.serialize(),
            self.scene.serialize(),
            output_type=self.output_type_cache,
            task_type=self.task_type_animation.serialize(),
            name="main",
            revision=3,
        )

        self.assertEqual(
            file_name,
            "cosmos_landromat_s01_sc01_animation_cache_main_tree_0001_v003",
        )

    def test_get_folder_path_asset_asset_instance(self):
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()
        self.generate_fixture_asset_asset_instance()
        path = file_tree_service.get_instance_folder_path(
            self.asset_instance.serialize(),
            self.asset.serialize(),
            task_type=self.task_type.serialize(),
            output_type=self.output_type_materials,
            representation="ml",
        )
        self.assertEqual(
            path,
            "/simple/productions/export/cosmos_landromat/assets/props/tree/"
            "shaders/materials/character/rabbit/instance_0001/ml",
        )

    def test_get_file_name_asset_asset_instance(self):
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()
        self.generate_fixture_asset_asset_instance()
        file_name = file_tree_service.get_instance_file_name(
            self.asset_instance.serialize(),
            self.asset.serialize(),
            output_type=self.output_type_materials,
            task_type=self.task_type.serialize(),
            name="main",
            revision=3,
        )

        self.assertEqual(
            file_name,
            "cosmos_landromat_props_tree_shaders_materials_main_"
            "rabbit_0001_v003",
        )

    def test_get_output_file_path(self):
        path = file_tree_service.get_output_file_path(
            self.shot.serialize(),
            output_type=self.output_type_cache,
            task_type=self.task_type_animation.serialize(),
            name="main",
            revision=3,
            sep="/",
        )
        self.assertEqual(
            path,
            "/simple/productions/export/cosmos_landromat/shots/s01/p01/"
            "animation/cache/"
            "cosmos_landromat_s01_p01_animation_cache_main_v003",
        )

    def test_get_shot_task_from_path(self):
        # The tokens are matched against entity names as they are stored, not
        # against the lowercase style the templates render paths with. The
        # shot template carries no <Episode> token, so the sequence is looked
        # up with no parent: only a flat production resolves.
        shot = Entity.create(
            name="P002",
            project_id=self.project.id,
            entity_type_id=self.shot_type.id,
            parent_id=self.sequence_standard.id,
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

    def test_get_asset_task_from_path(self):
        task = file_tree_service.get_asset_task_from_path(
            "/simple/productions/cosmos_landromat/assets/Props/Tree/Shaders/"
            "blender",
            self.project.serialize(),
        )
        self.assertEqual(task["id"], str(self.task.id))

    def test_get_task_from_path_rejects_a_path_of_another_shape(self):
        with self.assertRaises(WrongPathFormatException):
            file_tree_service.get_shot_task_from_path(
                "/simple/productions/cosmos_landromat/shots/S01/P01",
                self.project.serialize(),
            )

    def test_change_folder_path_separators(self):
        result = file_tree_service.change_folder_path_separators(
            "/simple/big_buck_bunny/props", "\\"
        )
        self.assertEqual(result, "\\simple\\big_buck_bunny\\props")

    def test_update_variable(self):
        name = file_tree_service.update_variable(
            "<AssetType>_<Asset>",
            asset=self.asset.serialize(),
            task=self.task.serialize(),
        )
        self.assertEqual(name, "props_tree")

    def test_apply_style(self):
        file_name = "Shaders"
        result = file_tree_service.apply_style(file_name, "uppercase")
        self.assertEqual(result, "SHADERS")
        result = file_tree_service.apply_style(file_name, "lowercase")
        self.assertEqual(result, "shaders")

    def test_update_variable_short_name(self):
        name = file_tree_service.update_variable(
            "<TaskType.short_name>",
            asset=self.asset.serialize(),
            task=self.task.serialize(),
        )
        self.assertEqual(name, "shd")
