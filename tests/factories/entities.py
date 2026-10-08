from zou.app.services import (
    breakdown_service,
)

from zou.app.models.asset_instance import AssetInstance
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType


class EntityFactories:
    """
    Entity types, assets, shots, sequences, episodes, edits and asset instances.
    """

    def generate_fixture_asset_type(self):
        if hasattr(self, "asset_type"):
            return
        self.asset_type = EntityType.create(name="Props")
        self.asset_type_props = self.asset_type
        self.shot_type = EntityType.create(name="Shot")
        self.sequence_type = EntityType.create(name="Sequence")
        self.episode_type = EntityType.create(name="Episode")
        self.scene_type = EntityType.create(name="Scene")
        self.edit_type = EntityType.create(name="Edit")

    def generate_fixture_asset_types(self):
        if hasattr(self, "asset_type_character"):
            return
        self.asset_type_character = EntityType.create(name="Character")
        self.asset_type_environment = EntityType.create(name="Environment")
        self.asset_type_camera = EntityType.create(name="Camera")

    # Entities

    def generate_fixture_asset(
        self,
        name="Tree",
        description="Description Tree",
        asset_type_id=None,
        project_id=None,
    ):
        if (
            name == "Tree"
            and description == "Description Tree"
            and asset_type_id is None
            and project_id is None
            and hasattr(self, "asset")
        ):
            return self.asset
        self.generate_fixture_asset_type()
        if not hasattr(self, "project"):
            self.generate_fixture_project()
        if asset_type_id is None:
            asset_type_id = self.asset_type.id

        if project_id is None:
            project_id = self.project_id

        self.asset = Entity.create(
            name=name,
            description=description,
            project_id=project_id,
            entity_type_id=asset_type_id,
        )
        return self.asset

    def generate_fixture_asset_character(
        self, name="Rabbit", description="Main char"
    ):
        if (
            name == "Rabbit"
            and description == "Main char"
            and hasattr(self, "asset_character")
        ):
            return self.asset_character
        self.generate_fixture_asset_types()
        self.generate_fixture_project()
        self.asset_character = Entity.create(
            name=name,
            description=description,
            project_id=self.project.id,
            entity_type_id=self.asset_type_character.id,
        )
        return self.asset_character

    def generate_fixture_asset_camera(self):
        if hasattr(self, "asset_camera"):
            return
        self.generate_fixture_asset_types()
        self.generate_fixture_project()
        self.asset_camera = Entity.create(
            name="Main camera",
            description="Description Camera",
            project_id=self.project.id,
            entity_type_id=self.asset_type_camera.id,
        )

    def generate_fixture_asset_standard(self):
        if hasattr(self, "asset_standard"):
            return
        self.generate_fixture_asset_type()
        self.generate_fixture_project_standard()
        self.asset_standard = Entity.create(
            name="Car",
            project_id=self.project_standard.id,
            entity_type_id=self.asset_type.id,
        )

    def generate_fixture_episode(self, name="E01", project_id=None):
        self.generate_fixture_asset_type()
        self.generate_fixture_project()
        if project_id is None:
            project_id = self.project.id
        self.episode = Entity.create(
            name=name,
            project_id=project_id,
            entity_type_id=self.episode_type.id,
        )
        return self.episode

    def generate_fixture_sequence(
        self, name="S01", episode_id=None, project_id=None
    ):
        if (
            name == "S01"
            and episode_id is None
            and project_id is None
            and hasattr(self, "sequence")
        ):
            return self.sequence
        self.generate_fixture_asset_type()
        self.generate_fixture_project()
        if episode_id is None and hasattr(self, "episode"):
            episode_id = self.episode.id

        if project_id is None:
            project_id = self.project.id

        self.sequence = Entity.create(
            name=name,
            project_id=project_id,
            entity_type_id=self.sequence_type.id,
            parent_id=episode_id,
        )
        return self.sequence

    def generate_fixture_sequence_standard(self):
        if hasattr(self, "sequence_standard"):
            return self.sequence_standard
        self.generate_fixture_asset_type()
        self.generate_fixture_project_standard()
        self.sequence_standard = Entity.create(
            name="S01",
            project_id=self.project_standard.id,
            entity_type_id=self.sequence_type.id,
        )
        return self.sequence_standard

    def generate_fixture_shot(self, name="P01", nb_frames=0, sequence_id=None):
        if (
            name == "P01"
            and nb_frames == 0
            and sequence_id is None
            and hasattr(self, "shot")
            and self.shot.parent_id == self.sequence.id
        ):
            return self.shot
        self.generate_fixture_asset_type()
        self.generate_fixture_project()
        self.generate_fixture_sequence()
        if sequence_id is None:
            sequence_id = self.sequence.id
        self.shot = Entity.create(
            name=name,
            description="Description Shot 01",
            data={"fps": 25, "frame_in": 0, "frame_out": 100},
            project_id=self.project.id,
            entity_type_id=self.shot_type.id,
            parent_id=sequence_id,
            nb_frames=nb_frames,
        )
        return self.shot

    def generate_fixture_shot_standard(self, name="SH01"):
        if name == "SH01" and hasattr(self, "shot_standard"):
            return self.shot_standard
        self.generate_fixture_asset_type()
        self.generate_fixture_project_standard()
        self.generate_fixture_sequence_standard()
        self.shot_standard = Entity.create(
            name=name,
            description="Description Shot 01",
            data={"fps": 25, "frame_in": 0, "frame_out": 100},
            project_id=self.project_standard.id,
            entity_type_id=self.shot_type.id,
            parent_id=self.sequence_standard.id,
        )
        return self.shot_standard

    def generate_fixture_scene(
        self, name="SC01", project_id=None, sequence_id=None
    ):
        if (
            name == "SC01"
            and project_id is None
            and sequence_id is None
            and hasattr(self, "scene")
        ):
            return self.scene
        self.generate_fixture_asset_type()
        self.generate_fixture_project()
        self.generate_fixture_sequence()
        if project_id is None:
            project_id = self.project.id

        if sequence_id is None:
            sequence_id = self.sequence.id

        self.scene = Entity.create(
            name=name,
            description="Description Scene 01",
            data={},
            project_id=project_id,
            entity_type_id=self.scene_type.id,
            parent_id=self.sequence.id,
        )
        return self.scene

    def generate_fixture_edit(self, name="Edit", parent_id=None):
        self.generate_fixture_asset_type()
        self.generate_fixture_project()
        self.edit = Entity.create(
            name=name,
            description="Description of the Edit",
            project_id=self.project.id,
            entity_type_id=self.edit_type.id,
            parent_id=parent_id,
        )
        return self.edit

    # Asset instances

    def generate_fixture_shot_asset_instance(
        self, shot, asset_instance, number=1
    ):
        self.shot.instance_casting.append(asset_instance)
        self.shot.save()
        return self.shot

    def generate_fixture_scene_asset_instance(
        self, asset=None, scene=None, number=1
    ):
        if asset is None:
            asset = self.asset
        if scene is None:
            scene = self.scene
        self.asset_instance = AssetInstance.create(
            asset_id=asset.id,
            scene_id=scene.id,
            number=number,
            name=breakdown_service.build_asset_instance_name(
                self.asset.id, number
            ),
            description="Asset instance description",
        )
        return self.asset_instance

    def generate_fixture_asset_asset_instance(
        self, asset=None, target_asset=None, number=1
    ):
        if asset is None:
            asset = self.asset_character
        if target_asset is None:
            target_asset = self.asset
        self.asset_instance = AssetInstance.create(
            asset_id=asset.id,
            target_asset_id=target_asset.id,
            number=number,
            name=breakdown_service.build_asset_instance_name(asset.id, number),
            description="Asset instance description",
        )
        return self.asset_instance
