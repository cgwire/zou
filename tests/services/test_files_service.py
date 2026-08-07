import pytest

from sqlalchemy import event

from tests.base import ApiDBTestCase

from zou.app import app, db
from zou.app.models.file_status import FileStatus
from zou.app.models.software import Software
from zou.app.models.working_file import WorkingFile
from zou.app.services import deletion_service, files_service
from zou.app.services.exception import (
    EntryAlreadyExistsException,
    OutputFileNotFoundException,
    OutputTypeNotFoundException,
    PreviewBackgroundFileNotFoundException,
    PreviewFileNotFoundException,
    SoftwareNotFoundException,
    WorkingFileNotFoundException,
)
from zou.app.utils import cache, fields


class DefaultFileStatusTestCase(ApiDBTestCase):
    """
    A fresh instance holds no file status at all, and every output file
    needs one. It is created on the first read, and only once.
    """

    def setUp(self):
        super().setUp()
        cache.cache.delete_memoized(files_service.get_default_status)

    def test_the_default_status_is_created_on_first_read(self):
        self.assertEqual(FileStatus.query.count(), 0)

        file_status = files_service.get_default_status()

        self.assertEqual(
            file_status["name"], app.config["DEFAULT_FILE_STATUS"]
        )
        self.assertEqual(FileStatus.query.count(), 1)
        self.assertEqual(files_service.get_default_status(), file_status)


class FilesTestCase(ApiDBTestCase):
    """
    An asset and a shot, each with a task, a working file and an output
    file: the smallest set every listing of this service reads from.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_task_type()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        self.generate_fixture_software()
        self.generate_fixture_working_file()
        self.generate_fixture_output_type()
        self.generate_fixture_output_file()


class LookupTestCase(FilesTestCase):
    """
    The get_*_raw / get_* pairs. Each raises its own exception rather than
    returning None, and an unreadable id is a miss, not a crash.
    """

    def test_a_working_file_is_read_by_id(self):
        working_file = files_service.get_working_file(self.working_file.id)
        self.assertEqual(working_file["id"], str(self.working_file.id))
        self.assertEqual(
            files_service.get_working_file_raw(self.working_file.id).id,
            self.working_file.id,
        )

    def test_an_output_file_is_read_by_id(self):
        output_file = files_service.get_output_file(self.output_file.id)
        self.assertEqual(output_file["id"], str(self.output_file.id))
        self.assertEqual(
            files_service.get_output_file_raw(self.output_file.id).id,
            self.output_file.id,
        )

    def test_a_software_is_read_by_id(self):
        software = files_service.get_software(self.software.id)
        self.assertEqual(software["id"], str(self.software.id))
        self.assertEqual(
            files_service.get_software_raw(self.software.id).id,
            self.software.id,
        )

    def test_an_output_type_is_read_by_id(self):
        self.assertEqual(
            files_service.get_output_type(self.output_type.id)["id"],
            str(self.output_type.id),
        )
        self.assertEqual(
            files_service.get_output_type_raw(self.output_type.id).id,
            self.output_type.id,
        )

    def test_a_preview_file_is_read_by_id(self):
        self.generate_fixture_preview_file()
        self.assertEqual(
            files_service.get_preview_file(self.preview_file.id)["id"],
            str(self.preview_file.id),
        )
        self.assertEqual(
            files_service.get_preview_file_raw(self.preview_file.id).id,
            self.preview_file.id,
        )

    def test_a_preview_background_file_is_read_by_id(self):
        self.generate_fixture_preview_background_file()
        self.assertEqual(
            files_service.get_preview_background_file_raw(
                self.preview_background_file.id
            ).id,
            self.preview_background_file.id,
        )

    def test_an_unknown_id_raises_the_exception_of_its_model(self):
        """
        A string that is not even a uuid is a miss too: the routes hand the
        path parameter over untouched, and the StatementError it raises in
        the driver must not reach the client as a 500.
        """
        for get, exception in [
            (files_service.get_working_file, WorkingFileNotFoundException),
            (files_service.get_working_file_raw, WorkingFileNotFoundException),
            (files_service.get_output_file, OutputFileNotFoundException),
            (files_service.get_output_file_raw, OutputFileNotFoundException),
            (files_service.get_software, SoftwareNotFoundException),
            (files_service.get_software_raw, SoftwareNotFoundException),
            (files_service.get_output_type, OutputTypeNotFoundException),
            (files_service.get_output_type_raw, OutputTypeNotFoundException),
            (files_service.get_preview_file, PreviewFileNotFoundException),
            (files_service.get_preview_file_raw, PreviewFileNotFoundException),
            (
                files_service.get_preview_file_for_access,
                PreviewFileNotFoundException,
            ),
            (
                files_service.get_preview_background_file_raw,
                PreviewBackgroundFileNotFoundException,
            ),
        ]:
            with self.subTest(get=get.__name__):
                self.assertRaises(exception, get, "unknown")
                self.assertRaises(exception, get, fields.gen_uuid())

    def test_a_software_is_created_only_once(self):
        self.assertIsNone(Software.get_by(name="Maya"))
        software = files_service.get_or_create_software("Maya", "may", ".ma")
        self.assertIsNotNone(Software.get_by(name="Maya"))
        self.assertEqual(
            files_service.get_or_create_software("Maya", "may", ".ma")["id"],
            software["id"],
        )

    def test_an_output_type_is_created_only_once(self):
        output_type = files_service.get_or_create_output_type("NewType", "nt")
        self.assertEqual(output_type["name"], "NewType")
        self.assertEqual(
            files_service.get_or_create_output_type("NewType", "nt")["id"],
            output_type["id"],
        )

    def test_a_preview_file_for_access_carries_no_annotation(self):
        """
        The download routes only need the task to check the permission and
        the date for the Last-Modified header. The annotations and the data
        of a long shot weigh several MB, so the point of this lookup is the
        columns it does not read: watch the statement, not the result.
        """
        self.generate_fixture_preview_file()
        # Read out of the fixture first: touching it under the recorder
        # would log the lazy load of the whole row, which is not the
        # statement under test.
        preview_file_id = str(self.preview_file.id)
        task_id = str(self.preview_file.task_id)
        statements = []

        def record(conn, cursor, statement, *args):
            statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", record)
        try:
            result = files_service.get_preview_file_for_access(preview_file_id)
        finally:
            event.remove(db.engine, "before_cursor_execute", record)

        self.assertEqual(
            set(result.keys()), {"id", "task_id", "updated_at", "extension"}
        )
        self.assertEqual(result["id"], preview_file_id)
        self.assertEqual(result["task_id"], task_id)
        self.assertNotIn("annotations", " ".join(statements))


class WorkingFileTestCase(FilesTestCase):
    """
    Working files: one revision line per (task, name).
    """

    def test_the_revisions_of_a_task_come_newest_first(self):
        for revision in [2, 3, 4, 5]:
            self.generate_fixture_working_file(name="main", revision=revision)
        working_files = files_service.get_working_files_for_task(self.task.id)
        self.assertEqual(
            [working_file["revision"] for working_file in working_files],
            [5, 4, 3, 2, 1],
        )

    def test_the_last_revision_is_read_per_name_and_per_task(self):
        for revision in [2, 3, 4, 5]:
            self.generate_fixture_working_file(name="main", revision=revision)
        for revision in [1, 2, 3]:
            self.generate_fixture_working_file(
                name="hotfix", revision=revision
            )
        # Same name, another task, and further along: the two revision
        # lines are separate even though they share a name.
        self.generate_fixture_shot_working_file()
        WorkingFile.get(self.working_file.id).update({"revision": 9})

        working_files = files_service.get_last_working_files_for_task(
            self.task.id
        )

        self.assertEqual(working_files["main"]["revision"], 5)
        self.assertEqual(working_files["hotfix"]["revision"], 3)
        self.assertEqual(
            files_service.get_last_working_files_for_task(self.shot_task.id)[
                "main"
            ]["revision"],
            9,
        )

    def test_the_next_revision_follows_the_last_one_of_the_name(self):
        self.generate_fixture_working_file(name="hotfix", revision=7)
        for next_revision in [
            files_service.get_next_working_revision,
            files_service.get_next_working_file_revision,
        ]:
            with self.subTest(next_revision=next_revision.__name__):
                self.assertEqual(next_revision(self.task.id, "main"), 2)
                self.assertEqual(next_revision(self.task.id, "hotfix"), 8)
                self.assertEqual(next_revision(self.task.id, "unknown"), 1)

    def test_a_new_revision_numbers_itself(self):
        self.working_file.delete()
        for expected in [1, 2]:
            working_file = files_service.create_new_working_revision(
                self.task.id, self.person.id, self.software.id, "main", "/path"
            )
            self.assertEqual(working_file["revision"], expected)
        self.assertEqual(
            len(files_service.get_working_files_for_task(self.task.id)), 2
        )

    def test_a_revision_already_taken_is_refused(self):
        with pytest.raises(EntryAlreadyExistsException):
            files_service.create_new_working_revision(
                self.task.id,
                self.person.id,
                self.software.id,
                "main",
                "/path",
                revision=1,
            )

    def test_a_new_revision_is_announced(self):
        captured = self.capture_events("working-file:new")
        files_service.create_new_working_revision(
            self.task.id, self.person.id, self.software.id, "main", "/path"
        )
        self.assertEqual(len(captured), 1)

    def test_the_revisions_of_an_entity_are_narrowed_by_task_and_name(self):
        asset_working_file_id = str(self.working_file.id)
        # Repoints self.working_file at the shot one.
        shot_working_file_id = str(
            self.generate_fixture_shot_working_file().id
        )

        working_files = files_service.get_working_files_for_entity(
            self.asset.id
        )
        self.assertEqual(
            [working_file["id"] for working_file in working_files],
            [asset_working_file_id],
        )
        self.assertEqual(
            [
                working_file["id"]
                for working_file in files_service.get_working_files_for_entity(
                    self.shot.id
                )
            ],
            [shot_working_file_id],
        )
        self.assertEqual(
            files_service.get_working_files_for_entity(
                self.asset.id, task_id=self.shot_task.id
            ),
            [],
        )
        self.assertEqual(
            files_service.get_working_files_for_entity(
                self.asset.id, name="unknown"
            ),
            [],
        )

    def test_an_updated_working_file_is_read_back_updated(self):
        working_file_id = self.working_file.id
        files_service.get_working_file(working_file_id)
        result = files_service.update_working_file(
            working_file_id, {"comment": "updated"}
        )
        self.assertEqual(result["comment"], "updated")
        self.assertEqual(
            files_service.get_working_file(working_file_id)["comment"],
            "updated",
        )


class OutputFileTestCase(FilesTestCase):
    """
    Output files: a revision line per (entity, output type, task type,
    name), each revision holding one row per representation.
    """

    def test_the_next_revision_follows_the_last_one(self):
        self.assertEqual(
            files_service.get_next_output_file_revision(
                self.asset.id, self.output_type.id, self.task_type.id
            ),
            2,
        )
        self.assertEqual(
            files_service.get_next_output_file_revision(
                self.asset.id,
                self.output_type.id,
                self.task_type.id,
                name="unknown",
            ),
            1,
        )

    def test_a_new_revision_numbers_itself(self):
        self.output_file.delete()
        for expected in [1, 2]:
            output_file = files_service.create_new_output_revision(
                self.asset.id,
                self.working_file.id,
                self.output_type.id,
                self.person.id,
                self.task_type.id,
            )
            self.assertEqual(output_file["revision"], expected)
        self.assertEqual(
            files_service.get_last_output_revision(
                self.asset.id, self.output_type.id, self.task_type.id
            )["revision"],
            2,
        )

    def test_a_revision_already_taken_is_refused(self):
        with pytest.raises(EntryAlreadyExistsException):
            files_service.create_new_output_revision(
                self.asset.id,
                self.working_file.id,
                self.output_type.id,
                self.person.id,
                self.task_type.id,
                revision=1,
            )

    def test_a_new_revision_is_announced(self):
        captured = self.capture_events("output-file:new")
        files_service.create_new_output_revision(
            self.asset.id,
            self.working_file.id,
            self.output_type.id,
            self.person.id,
            self.task_type.id,
        )
        self.assertEqual(len(captured), 1)

    def test_an_entity_with_no_output_file_has_no_last_revision(self):
        from zou.app.services.exception import NoOutputFileException

        self.assertRaises(
            NoOutputFileException,
            files_service.get_last_output_revision,
            self.shot.id,
            self.output_type.id,
            self.task_type.id,
        )

    def test_the_revisions_of_an_entity_come_newest_first(self):
        for revision in [2, 3]:
            self.generate_fixture_output_file(self.output_type, revision)
        output_files = files_service.get_output_files_for_entity(self.asset.id)
        self.assertEqual(
            [output_file["revision"] for output_file in output_files],
            [3, 2, 1],
        )

    def test_the_files_of_an_instance_stay_out_of_the_entity_listing(self):
        """
        An instance of an asset publishes its own files, under the asset it
        instantiates. Counting them among the files of the asset itself
        would show the same revision several times.
        """
        self.generate_fixture_scene()
        asset_instance = self.generate_fixture_scene_asset_instance()
        self.generate_fixture_output_file(
            self.output_type,
            2,
            asset_instance=asset_instance,
            temporal_entity_id=str(self.scene.id),
        )
        output_files = files_service.get_output_files_for_entity(self.asset.id)
        self.assertEqual(
            [output_file["revision"] for output_file in output_files], [1]
        )

    def test_the_last_revision_is_read_per_output_type(self):
        geometry = self.output_type
        cache_type = self.generate_fixture_output_type(
            name="Cache", short_name="cch"
        )
        for revision in [2, 3, 4, 5]:
            self.generate_fixture_output_file(geometry, revision)
        for revision in [1, 2, 3]:
            self.generate_fixture_output_file(cache_type, revision)
        # An instance of the asset, further along than the asset itself.
        self.generate_fixture_scene()
        self.generate_fixture_output_file(
            geometry,
            9,
            asset_instance=self.generate_fixture_scene_asset_instance(),
            temporal_entity_id=str(self.scene.id),
        )

        last_output_files = files_service.get_last_output_files_for_entity(
            self.asset.id
        )

        self.assertEqual(
            {
                output_file["output_type_id"]: output_file["revision"]
                for output_file in last_output_files
            },
            {str(geometry.id): 5, str(cache_type.id): 3},
        )

    def test_a_listing_is_narrowed_by_output_type_and_representation(self):
        geometry = self.output_type
        for revision in [1, 2, 3, 4]:
            self.generate_fixture_output_file(
                geometry, revision, representation="obj"
            )
        for revision in [1, 2, 3]:
            self.generate_fixture_output_file(
                geometry, revision, representation="max"
            )

        # An instance of the asset publishes under the same output type:
        # its files belong to the instance, not to the asset.
        self.generate_fixture_scene()
        self.generate_fixture_output_file(
            geometry,
            9,
            asset_instance=self.generate_fixture_scene_asset_instance(),
            temporal_entity_id=str(self.scene.id),
        )

        get_files = files_service.get_output_files_for_output_type_and_entity
        # Newest revision first, both representations interleaved.
        self.assertEqual(
            [
                output_file["revision"]
                for output_file in get_files(self.asset.id, geometry.id)
            ],
            [4, 3, 3, 2, 2, 1, 1, 1],
        )
        self.assertEqual(
            len(
                get_files(
                    str(self.asset.id), geometry.id, representation="obj"
                )
            ),
            4,
        )
        self.assertEqual(
            len(
                get_files(
                    str(self.asset.id), geometry.id, representation="max"
                )
            ),
            3,
        )

    def test_the_output_types_of_an_entity_are_listed_once_each(self):
        cache_type = self.generate_fixture_output_type(
            name="Cache", short_name="cch"
        )
        self.generate_fixture_output_file(cache_type, 1)
        self.generate_fixture_output_file(self.output_type, 2)
        # Another entity publishes a type this asset never used.
        rig_type = self.generate_fixture_output_type(
            name="Rig", short_name="rig"
        )
        self.generate_fixture_output_file(rig_type, 1, task=self.shot_task)

        self.assertEqual(
            [
                output_type["name"]
                for output_type in files_service.get_output_types_for_entity(
                    self.asset.id
                )
            ],
            ["Cache", "Geometry"],
        )
        self.assertEqual(
            [
                output_type["name"]
                for output_type in files_service.get_output_types_for_entity(
                    self.shot.id
                )
            ],
            ["Rig"],
        )

    def test_an_updated_output_file_is_read_back_updated(self):
        output_file_id = self.output_file.id
        files_service.get_output_file(output_file_id)
        result = files_service.update_output_file(
            output_file_id, {"comment": "updated"}
        )
        self.assertEqual(result["comment"], "updated")
        self.assertEqual(
            files_service.get_output_file(output_file_id)["comment"], "updated"
        )


class AssetInstanceOutputFileTestCase(FilesTestCase):
    """
    The same output files, published by an instance of an asset rather than
    by the asset: they are keyed by the instance and the temporal entity it
    appears in.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_scene()
        self.asset_instance = self.generate_fixture_scene_asset_instance()
        self.geometry = self.output_type
        self.cache = self.generate_fixture_output_type(
            name="Cache", short_name="cch"
        )
        self.scene_id = str(self.scene.id)
        self.shot_id = str(self.shot.id)

    def publish(self, output_type, revision, **kwargs):
        return self.generate_fixture_output_file(
            output_type,
            revision,
            asset_instance=self.asset_instance,
            temporal_entity_id=kwargs.pop("temporal_entity_id", self.scene_id),
            **kwargs,
        )

    def test_the_three_criterions_are_all_applied(self):
        """
        The same instance seen under another temporal entity, and its files
        of another output type, stay out. Newest revision first.
        """
        for revision, representation in [(1, "obj"), (2, "obj"), (1, "max")]:
            self.publish(
                self.geometry, revision, representation=representation
            )
        self.publish(self.cache, 1)
        self.publish(self.geometry, 1, temporal_entity_id=self.shot_id)

        get_files = (
            files_service.get_output_files_for_output_type_and_asset_instance
        )
        self.assertEqual(
            [
                output_file["revision"]
                for output_file in get_files(
                    self.asset_instance.id, self.scene_id, self.geometry.id
                )
            ],
            [2, 1, 1],
        )
        self.assertEqual(
            len(
                get_files(
                    self.asset_instance.id,
                    self.scene_id,
                    self.geometry.id,
                    representation="obj",
                )
            ),
            2,
        )
        self.assertEqual(
            len(
                get_files(
                    self.asset_instance.id, self.shot_id, self.geometry.id
                )
            ),
            1,
        )

    def test_every_revision_of_an_instance_is_listed_newest_first(self):
        for revision, representation in [(1, "obj"), (2, "obj"), (1, "max")]:
            self.publish(
                self.geometry, revision, representation=representation
            )
        self.publish(self.cache, 1)
        self.publish(self.geometry, 1, temporal_entity_id=self.shot_id)

        output_files = files_service.get_output_files_for_instance(
            self.asset_instance.id, self.scene_id
        )
        self.assertEqual(
            [output_file["revision"] for output_file in output_files],
            [2, 1, 1, 1],
        )
        self.assertEqual(
            {output_file["output_type_id"] for output_file in output_files},
            {str(self.geometry.id), str(self.cache.id)},
        )
        self.assertEqual(
            len(
                files_service.get_output_files_for_instance(
                    self.asset_instance.id,
                    self.scene_id,
                    output_type_id=self.cache.id,
                )
            ),
            1,
        )
        self.assertEqual(
            len(
                files_service.get_output_files_for_instance(
                    self.asset_instance.id,
                    self.scene_id,
                    representation="obj",
                )
            ),
            2,
        )

    def test_the_last_revision_is_read_per_output_type(self):
        for revision in [1, 2]:
            self.publish(self.geometry, revision)
        last_geometry = self.publish(self.geometry, 3)
        last_cache = self.publish(self.cache, 1)
        # The same instance under another temporal entity: its own line,
        # and its own last revision.
        self.publish(self.geometry, 9, temporal_entity_id=self.shot_id)

        last_output_files = files_service.get_last_output_files_for_instance(
            self.asset_instance.id, self.scene_id
        )

        self.assertEqual(
            {output_file["id"] for output_file in last_output_files},
            {str(last_geometry.id), str(last_cache.id)},
        )

    def test_the_output_types_of_an_instance_are_listed_once_each(self):
        self.publish(self.geometry, 1)
        self.publish(self.cache, 1)
        rig_type = self.generate_fixture_output_type(
            name="Rig", short_name="rig"
        )
        self.publish(rig_type, 1, temporal_entity_id=self.shot_id)

        self.assertEqual(
            [
                output_type["name"]
                for output_type in files_service.get_output_types_for_instance(
                    self.asset_instance.id, self.scene_id
                )
            ],
            ["Cache", "Geometry"],
        )
        self.assertEqual(
            [
                output_type["name"]
                for output_type in files_service.get_output_types_for_instance(
                    self.asset_instance.id, self.shot_id
                )
            ],
            ["Rig"],
        )


class PreviewFileTestCase(FilesTestCase):
    """
    Preview files: the rows the download routes read before serving a
    picture or a movie.
    """

    def test_the_previews_of_a_task_come_newest_first(self):
        for revision in [1, 2, 3]:
            self.generate_fixture_preview_file(revision=revision)
        self.assertEqual(
            [
                preview["revision"]
                for preview in files_service.get_preview_files_for_task(
                    self.task.id
                )
            ],
            [3, 2, 1],
        )

    def test_a_new_preview_starts_as_processing(self):
        preview = files_service.create_preview_file(
            "main", 1, self.task.id, self.person.id
        )
        self.assertEqual(preview["name"], "main")
        self.assertEqual(preview["revision"], 1)
        self.assertEqual(preview["status"], "processing")

    def test_the_previews_of_a_production_come_last_touched_first(self):
        project_id = str(self.project.id)
        self.generate_fixture_project_standard()
        first = self.generate_fixture_preview_file()
        second = self.generate_fixture_preview_file(revision=2)

        self.assertEqual(
            [
                preview["id"]
                for preview in files_service.get_preview_files_for_project(
                    project_id
                )
            ],
            [str(second.id), str(first.id)],
        )
        self.assertEqual(
            files_service.get_preview_files_for_project(
                str(self.project_standard.id)
            ),
            [],
        )

    def test_a_removed_preview_is_no_longer_read(self):
        self.generate_fixture_preview_file()
        preview_file_id = str(self.preview_file.id)
        files_service.get_preview_file(preview_file_id)
        files_service.get_preview_file_for_access(preview_file_id)

        files_service.remove_preview_file(preview_file_id)

        for get in [
            files_service.get_preview_file,
            files_service.get_preview_file_for_access,
        ]:
            with self.subTest(get=get.__name__):
                self.assertRaises(
                    PreviewFileNotFoundException, get, preview_file_id
                )

    def test_a_removed_preview_is_announced(self):
        self.generate_fixture_preview_file()
        captured = self.capture_events("preview-file:delete")
        files_service.remove_preview_file(self.preview_file.id)
        self.assertEqual(len(captured), 1)

    def test_a_deleted_preview_stops_being_downloadable(self):
        """
        get_preview_file_for_access is the only check the download routes
        run: the permission is read off the task it returns. A serialization
        left in the cache keeps serving the file the deletion was meant to
        take away, for the whole memoization window.
        """
        self.generate_fixture_preview_file()
        preview_file = self.preview_file
        preview_file_id = str(preview_file.id)
        files_service.get_preview_file(preview_file_id)
        files_service.get_preview_file_for_access(preview_file_id)

        deletion_service.remove_preview_file(preview_file)

        for get in [
            files_service.get_preview_file,
            files_service.get_preview_file_for_access,
        ]:
            with self.subTest(get=get.__name__):
                self.assertRaises(
                    PreviewFileNotFoundException, get, preview_file_id
                )


class PreviewBackgroundFileTestCase(FilesTestCase):
    """
    The HDRI backgrounds a production sets behind its 3D previews. One of
    them is the default, and there is only ever one.
    """

    def test_the_backgrounds_are_listed(self):
        self.assertEqual(files_service.get_preview_background_files(), [])
        self.generate_fixture_preview_background_file()
        files_service.clear_preview_background_file_cache(
            self.preview_background_file.id
        )
        self.assertEqual(len(files_service.get_preview_background_files()), 1)

    def test_an_updated_background_is_read_back_updated(self):
        self.generate_fixture_preview_background_file()
        background_id = self.preview_background_file.id
        files_service.get_preview_background_file(background_id)
        result = files_service.update_preview_background_file(
            background_id, {"name": "updated"}
        )
        self.assertEqual(result["name"], "updated")
        self.assertEqual(
            files_service.get_preview_background_file(background_id)["name"],
            "updated",
        )

    def test_a_new_default_unseats_the_previous_one(self):
        """
        The rows the reset writes to are read one by one by the download
        routes, so they are the ones whose cache has to go: the row that
        keeps announcing itself as the default is the one that just lost
        the title.
        """
        self.generate_fixture_preview_background_file()
        previous = self.preview_background_file
        previous.update({"is_default": True})
        files_service.clear_preview_background_file_cache(str(previous.id))
        new_default = self.generate_fixture_preview_background_file(
            name="Alt background", is_default=True
        )
        self.assertTrue(
            files_service.get_preview_background_file(str(previous.id))[
                "is_default"
            ]
        )

        files_service.reset_default_preview_background_files(new_default.id)

        self.assertFalse(
            files_service.get_preview_background_file(str(previous.id))[
                "is_default"
            ]
        )
        self.assertTrue(
            files_service.get_preview_background_file(str(new_default.id))[
                "is_default"
            ]
        )
