from flasgger import swag_from
from sqlalchemy.exc import IntegrityError

from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.build_job import BuildJob
from zou.app.models.comment import Comment
from zou.app.models.entity import Entity, EntityLink
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.milestone import Milestone
from zou.app.models.news import News
from zou.app.models.notification import Notification
from zou.app.models.playlist import Playlist
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task
from zou.app.models.time_spent import TimeSpent
from zou.app.mixin import ArgsMixin
from zou.app.utils import events, fields, permissions
from zou.app.exceptions import WrongParameterException
from zou.app.services import (
    entities_service,
    tasks_service,
    entity_types_service,
)


def _project_id_from_task(entry):
    task_id = entry.get("task_id")
    task = Task.get(task_id) if task_id else None
    return str(task.project_id) if task is not None else None


def _project_id_from_playlist(entry):
    playlist_id = entry.get("playlist_id")
    playlist = Playlist.get(playlist_id) if playlist_id else None
    return str(playlist.project_id) if playlist is not None else None


def _project_id_from_attachment(entry):
    comment_id = entry.get("comment_id")
    if comment_id:
        comment = Comment.get(comment_id)
        if comment is not None and comment.object_id is not None:
            task = Task.get(comment.object_id)
            if task is not None:
                return str(task.project_id)
    return None


class BaseImportKitsuResource(MethodView, ArgsMixin):
    def __init__(self, model):
        MethodView.__init__(self)
        self.model = model

    @jwt_required()
    @swag_from("openapi/BaseImportKitsuResource_post.yml")
    def post(self):
        """
        Import kitsu resource
        """
        kitsu_entries = request.json
        if not isinstance(kitsu_entries, list):
            raise WrongParameterException("A list of entities is expected.")

        # Bulk imports (sync-push) pass ?silent=true to skip per-row
        # event emission: each emit persists an api_event row and triggers
        # a Redis PUBLISH, which adds up to thousands of writes on a
        # project-wide import. Connected UIs miss the live updates but
        # the target instance stays responsive.
        silent = request.args.get("silent", "").lower() in ("1", "true", "yes")

        instances = []
        for entry in kitsu_entries:
            if self.check_access(entry):
                try:
                    instance, is_updated = self.model.create_from_import(entry)
                    if not silent:
                        if is_updated:
                            self.emit_event("update", entry)
                        else:
                            self.emit_event("new", entry)
                except IntegrityError as exc:
                    raise WrongParameterException(exc.orig)
                instances.append(instance)
        return fields.serialize_models(instances)

    def emit_event(self, event_type, entry):
        pass

    def check_access(self, entry):
        return permissions.has_admin_permissions()


class ImportKitsuCommentsResource(BaseImportKitsuResource):
    def __init__(self):
        BaseImportKitsuResource.__init__(self, Comment)

    @jwt_required()
    @swag_from("openapi/ImportKitsuCommentsResource_post.yml")
    def post(self):
        """
        Import kitsu comments
        """
        return super().post()

    def emit_event(self, event_type, entry):
        task = tasks_service.get_task(str(entry["object_id"]))
        # As stored: an imported update may leave the client flag out.
        comment = Comment.get(entry["id"]).serialize()
        events.emit(
            f"comment:{event_type}",
            {
                "comment_id": entry["id"],
                "task_id": task["id"],
                "person_id": comment["person_id"],
                "for_client": comment["for_client"],
            },
            project_id=task["project_id"],
        )


class ImportKitsuEntitiesResource(BaseImportKitsuResource):
    def __init__(self):
        BaseImportKitsuResource.__init__(self, Entity)

    @jwt_required()
    @swag_from("openapi/ImportKitsuEntitiesResource_post.yml")
    def post(self):
        """
        Import kitsu entities
        """
        return super().post()

    def emit_event(self, event_type, entry):
        project_id = entry["project_id"]
        name = entity_types_service.get_base_entity_type_name(entry)
        events.emit(
            f"{name.lower()}:{event_type}",
            {f"{name}_id": entry["id"]},
            project_id=project_id,
        )


class ImportKitsuProjectsResource(BaseImportKitsuResource):
    def __init__(self):
        BaseImportKitsuResource.__init__(self, Project)

    @jwt_required()
    @swag_from("openapi/ImportKitsuProjectsResource_post.yml")
    def post(self):
        """
        Import kitsu projects
        """
        return super().post()

    def emit_event(self, event_type, entry):
        events.emit(f"project:{event_type}", project_id=entry["id"])


class ImportKitsuTasksResource(BaseImportKitsuResource):
    def __init__(self):
        BaseImportKitsuResource.__init__(self, Task)

    @jwt_required()
    @swag_from("openapi/ImportKitsuTasksResource_post.yml")
    def post(self):
        """
        Import kitsu tasks
        """
        return super().post()

    def emit_event(self, event_type, entry):
        events.emit(f"task:{event_type}", project_id=entry["project_id"])


class ImportKitsuEntityLinksResource(BaseImportKitsuResource):
    def __init__(self):
        BaseImportKitsuResource.__init__(self, EntityLink)

    @jwt_required()
    @swag_from("openapi/ImportKitsuEntityLinksResource_post.yml")
    def post(self):
        """
        Import kitsu entity links
        """
        return super().post()

    def emit_event(self, event_type, entry):
        entity = entities_service.get_entity(entry["entity_in_id"])
        project_id = entity["project_id"]
        events.emit(f"entity-link:{event_type}", project_id=project_id)


class _ProjectScopedImportResource(BaseImportKitsuResource):
    """
    Import resource whose entries carry a ``project_id`` directly.

    Admin-only by inheritance (BaseImportKitsuResource.check_access).

    """

    event_name = ""
    id_field = ""

    @jwt_required()
    @swag_from("openapi/BaseImportKitsuResource_post.yml")
    def post(self):
        return super().post()

    def emit_event(self, event_type, entry):
        events.emit(
            f"{self.event_name}:{event_type}",
            {self.id_field: entry["id"]},
            project_id=entry["project_id"],
        )


class _TaskScopedImportResource(BaseImportKitsuResource):
    """
    Import resource whose entries derive their project via ``task_id``.

    Admin-only by inheritance (BaseImportKitsuResource.check_access).

    """

    event_name = ""
    id_field = ""

    @jwt_required()
    @swag_from("openapi/BaseImportKitsuResource_post.yml")
    def post(self):
        return super().post()

    def emit_event(self, event_type, entry):
        events.emit(
            f"{self.event_name}:{event_type}",
            {self.id_field: entry["id"]},
            project_id=_project_id_from_task(entry),
        )


class ImportKitsuPreviewFilesResource(_TaskScopedImportResource):
    event_name = "preview-file"
    id_field = "preview_file_id"

    def __init__(self):
        BaseImportKitsuResource.__init__(self, PreviewFile)

    @jwt_required()
    @swag_from("openapi/BaseImportKitsuResource_post.yml")
    def post(self):
        # Flag every imported entry as binary-not-available so downstream
        # services (thumbnail regen, frame extraction) know not to touch
        # the local filesystem. The push only transfers metadata.
        entries = request.json
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                data = entry.get("data") or {}
                data["imported_only"] = True
                entry["data"] = data
        return super().post()


class ImportKitsuTimeSpentsResource(_TaskScopedImportResource):
    event_name = "time-spent"
    id_field = "time_spent_id"

    def __init__(self):
        BaseImportKitsuResource.__init__(self, TimeSpent)


class ImportKitsuSubscriptionsResource(_TaskScopedImportResource):
    event_name = "subscription"
    id_field = "subscription_id"

    def __init__(self):
        BaseImportKitsuResource.__init__(self, Subscription)


class ImportKitsuNotificationsResource(_TaskScopedImportResource):
    event_name = "notification"
    id_field = "notification_id"

    def __init__(self):
        BaseImportKitsuResource.__init__(self, Notification)


class ImportKitsuNewsResource(_TaskScopedImportResource):
    event_name = "news"
    id_field = "news_id"

    def __init__(self):
        BaseImportKitsuResource.__init__(self, News)


class ImportKitsuPlaylistsResource(_ProjectScopedImportResource):
    event_name = "playlist"
    id_field = "playlist_id"

    def __init__(self):
        BaseImportKitsuResource.__init__(self, Playlist)


class ImportKitsuMetadataDescriptorsResource(_ProjectScopedImportResource):
    event_name = "metadata-descriptor"
    id_field = "metadata_descriptor_id"

    def __init__(self):
        BaseImportKitsuResource.__init__(self, MetadataDescriptor)


class ImportKitsuScheduleItemsResource(_ProjectScopedImportResource):
    event_name = "schedule-item"
    id_field = "schedule_item_id"

    def __init__(self):
        BaseImportKitsuResource.__init__(self, ScheduleItem)


class ImportKitsuMilestonesResource(_ProjectScopedImportResource):
    event_name = "milestone"
    id_field = "milestone_id"

    def __init__(self):
        BaseImportKitsuResource.__init__(self, Milestone)


class ImportKitsuBuildJobsResource(BaseImportKitsuResource):
    """
    Admin-only by inheritance.
    """

    def __init__(self):
        BaseImportKitsuResource.__init__(self, BuildJob)

    @jwt_required()
    @swag_from("openapi/BaseImportKitsuResource_post.yml")
    def post(self):
        return super().post()

    def emit_event(self, event_type, entry):
        events.emit(
            f"build-job:{event_type}",
            {"build_job_id": entry["id"]},
            project_id=_project_id_from_playlist(entry),
        )


class ImportKitsuAttachmentFilesResource(BaseImportKitsuResource):
    """
    Admin-only by inheritance.
    """

    def __init__(self):
        BaseImportKitsuResource.__init__(self, AttachmentFile)

    @jwt_required()
    @swag_from("openapi/BaseImportKitsuResource_post.yml")
    def post(self):
        return super().post()

    def emit_event(self, event_type, entry):
        events.emit(
            f"attachment-file:{event_type}",
            {"attachment_file_id": entry["id"]},
            project_id=_project_id_from_attachment(entry),
        )
