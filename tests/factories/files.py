from zou.app.models.file_status import FileStatus
from zou.app.models.output_file import OutputFile
from zou.app.models.output_type import OutputType
from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.models.preview_file import PreviewFile
from zou.app.models.software import Software
from zou.app.models.working_file import WorkingFile


class FileFactories:
    """
    Working files, output files and previews.
    """

    def generate_fixture_file_status(self):
        if hasattr(self, "file_status"):
            return
        self.file_status = FileStatus.create(name="To review", color="#FFFFFF")

    def generate_fixture_working_file(self, name="main", revision=1):
        if not hasattr(self, "task"):
            self.generate_fixture_task()
        self.generate_fixture_software()
        self.working_file = WorkingFile.create(
            name=name,
            comment="",
            revision=revision,
            task_id=self.task.id,
            entity_id=self.asset.id,
            person_id=self.person.id,
            software_id=self.software.id,
        )
        return self.working_file

    def generate_fixture_shot_working_file(self):
        self.generate_fixture_shot_task()
        self.generate_fixture_software()
        self.working_file = WorkingFile.create(
            name="main",
            comment="",
            revision=1,
            task_id=self.shot_task.id,
            entity_id=self.shot.id,
            person_id=self.person.id,
            software_id=self.software.id,
        )
        return self.working_file

    def generate_fixture_output_file(
        self,
        output_type=None,
        revision=1,
        name="main",
        representation="",
        asset_instance=None,
        temporal_entity_id=None,
        task=None,
    ):
        self.generate_fixture_task_type()
        self.generate_fixture_person()
        self.generate_fixture_file_status()
        if output_type is None:
            output_type = self.output_type

        if task is None:
            task_type_id = self.task_type.id
            asset_id = self.asset.id
        else:
            task_type_id = task.task_type_id
            asset_id = task.entity_id

        if asset_instance is None:
            asset_instance_id = None
        else:
            asset_instance_id = asset_instance.id
            if temporal_entity_id is None:
                temporal_entity_id = self.scene.id

        self.output_file = OutputFile.create(
            comment="",
            revision=revision,
            task_type_id=task_type_id,
            entity_id=asset_id,
            person_id=self.person.id,
            file_status_id=self.file_status.id,
            output_type_id=output_type.id,
            asset_instance_id=asset_instance_id,
            representation=representation,
            temporal_entity_id=temporal_entity_id,
            name=name,
        )
        return self.output_file

    def generate_fixture_output_type(self, name="Geometry", short_name="Geo"):
        self.output_type = OutputType.create(name=name, short_name=short_name)
        return self.output_type

    def generate_fixture_software(self):
        if hasattr(self, "software"):
            return
        self.software = Software.create(
            name="Blender", short_name="bdr", file_extension=".blender"
        )
        self.software_max = Software.create(
            name="3dsMax", short_name="max", file_extension=".max"
        )

    def generate_fixture_preview_file(
        self,
        revision=1,
        name="main",
        position=1,
        status="ready",
        duration=10,
        task_id=None,
    ):
        if not hasattr(self, "task"):
            self.generate_fixture_task()
        self.generate_fixture_person()
        task_id = task_id or self.task.id
        self.preview_file = PreviewFile.create(
            name=name,
            revision=revision,
            description="test description",
            source="pytest",
            task_id=task_id,
            extension="mp4",
            person_id=self.person.id,
            position=position,
            status=status,
            duration=duration,
        )
        return self.preview_file

    def generate_fixture_preview_background_file(
        self,
        name="test",
        is_default=False,
    ):
        self.preview_background_file = PreviewBackgroundFile.create(
            name=name, is_default=is_default
        )
        return self.preview_background_file
