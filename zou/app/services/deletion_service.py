"""
Cascade removals: the items that go with a task, a preview, an entity, an
episode or a whole project.

This service is at the top of the service layers. It is above the entity
services (assets, shots, edits, concepts), which call remove_task for
their force branch. This module imports those services inside the
functions that need them, not at module level. Those services import
this module, so a module-level import here makes an import cycle.
"""

import datetime
import logging

from zou.app.exceptions import (
    CommentNotFoundException,
    PreviewBackgroundFileNotFoundException,
    PreviewFileNotFoundException,
)
from zou.app.models.comment import Comment
from zou.app.models.entity import (
    Entity,
)
from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog
from zou.app.models.news import News
from zou.app.models.notification import Notification
from zou.app.models.output_file import OutputFile
from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.models.preview_file import PreviewFile
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task
from zou.app.models.time_spent import TimeSpent
from zou.app.models.working_file import WorkingFile
from zou.app.services import (
    attachment_files_service,
    entities_service,
    files_service,
    news_service,
    projects_service,
    tasks_service,
)
from zou.app.stores import file_store
from zou.app.utils import date_helpers, events, fields

logger = logging.getLogger(__name__)

# The previews that have a thumbnail. The service stores pictures as png
# and movies as mp4. The other files keep their own extension.
THUMBNAIL_EXTENSIONS = ("png", "mp4")


def _remove_older_than(model, date_column, days_old):
    """
    Delete all the rows of the given model that are older than *days_old*.
    """
    limit_date = date_helpers.get_utc_now_datetime() - datetime.timedelta(
        days=days_old
    )
    model.query.filter(date_column < limit_date).delete()
    model.commit()


def get_task_ids(*criterions, **kw):
    """
    Return the IDs of the tasks that match the given filters, as strings.
    The removal loops use these IDs, not ORM instances. Each removal does a
    commit, which expires the remaining instances. If another request
    deleted one of them, a read of its ID raises ObjectDeletedError.
    remove_task skips a task that does not exist any more.
    """
    return [
        str(row[0])
        for row in Task.query.with_entities(Task.id)
        .filter(*criterions)
        .filter_by(**kw)
        .all()
    ]


def remove_comment(comment_id):
    """
    Remove a comment and all the related data from the database:
    notifications, news, preview files and attachment files. Then emit a
    comment:delete event.
    """
    comment = Comment.get(comment_id)
    if comment is None:
        raise CommentNotFoundException

    task = Task.get(comment.object_id)
    notifications = Notification.query.filter_by(comment_id=comment.id)
    for notification in notifications:
        notification.delete()

    news_service.delete_news(
        News.get_all_by(comment_id=comment.id),
        str(task.project_id) if task is not None else None,
    )

    if comment.preview_file_id is not None:
        preview_file = PreviewFile.get(comment.preview_file_id)
        comment.preview_file_id = None
        comment.save()
        remove_preview_file(preview_file)

    previews = [preview for preview in comment.previews]
    attachments = [attachment for attachment in comment.attachment_files]
    comment.delete()

    for preview in previews:
        remove_preview_file(preview)

    for attachment in attachments:
        attachment_files_service.remove_attachment_file(attachment)

    if task is not None:
        events.emit(
            "comment:delete",
            {"comment_id": comment.id, "task_id": str(task.id)},
            project_id=str(task.project_id),
        )
    else:
        # The task can be already deleted. Notify the listeners all the
        # same, so that they remove the comment from their state.
        events.emit("comment:delete", {"comment_id": comment.id})
    return comment.serialize()


def remove_task(task_id, force=False, restore_main=True):
    """
    Remove the given task. If the task has related comments and files, force
    the deletion. This deletes all of them.

    If an entity showed a preview of the task, the entity gets the newest
    main preview of its other tasks (see _restore_entity_main_preview). The
    entity removal and the project removal pass restore_main=False, because
    the entity also goes. _remove_task_batch also passes it, and restores
    the preview once at the end.
    """

    task = Task.get(task_id)
    if task is None:
        return None
    project_id = str(task.project_id)
    if force:
        working_files = WorkingFile.query.filter_by(task_id=task_id)
        for working_file in working_files:
            output_files = OutputFile.query.filter_by(
                source_file_id=working_file.id
            )
            for output_file in output_files:
                output_file.delete()
            working_file.delete()

        comments = Comment.query.filter_by(object_id=task_id)
        for comment in comments:
            notifications = Notification.query.filter_by(comment_id=comment.id)
            for notification in notifications:
                notification.delete()
            news_service.delete_news(
                News.get_all_by(comment_id=comment.id), project_id
            )
            comment.delete()

        subscriptions = Subscription.query.filter_by(task_id=task_id)
        for subscription in subscriptions:
            subscription.delete()

        preview_files = PreviewFile.query.filter_by(task_id=task_id).all()
        entity = Entity.get(task.entity_id)
        is_entity_main = any(
            preview_file.id == entity.preview_file_id
            for preview_file in preview_files
        )
        # A restore after each removal announces previews that go next.
        # The service tells the entity once, after the last removal.
        for preview_file in preview_files:
            remove_preview_file(preview_file, restore_main=False)
        if restore_main and is_entity_main:
            _restore_entity_main_preview(entity)

        time_spents = TimeSpent.query.filter_by(task_id=task_id)
        for time_spent in time_spents:
            time_spent.delete()

        notifications = Notification.query.filter_by(task_id=task_id)
        for notification in notifications:
            notification.delete()

        news_service.delete_news(News.get_all_by(task_id=task.id), project_id)

    task.delete()
    tasks_service.clear_task_cache(task_id)
    task_serialized = task.serialize()
    events.emit(
        "task:delete",
        {
            "task_id": task_id,
            "entity_id": task_serialized["entity_id"],
            "task_type_id": task_serialized["task_type_id"],
        },
        project_id=task_serialized["project_id"],
    )
    return task_serialized


def remove_output_files_for_entity(entity_id):
    """
    Remove all the OutputFile rows that reference the given entity
    (entity_id). This prevents an FK violation when the entity is deleted.
    Before the deletion of each OutputFile, clear the PreviewFile
    source_file_id references to it.
    """
    output_files = OutputFile.query.filter_by(entity_id=entity_id).all()
    for output_file in output_files:
        PreviewFile.query.filter_by(source_file_id=output_file.id).update(
            {"source_file_id": None}
        )
        output_file.delete()
    return output_files


def remove_output_files_for_project(project_id):
    """
    Remove all the OutputFile rows that reference an entity of the project.
    The caller removed the preview files and tasks before this call.
    Because of this, it is not necessary to clear PreviewFile.source_file_id.
    """
    output_files = (
        OutputFile.query.join(Entity, OutputFile.entity_id == Entity.id)
        .filter(Entity.project_id == project_id)
        .all()
    )
    for output_file in output_files:
        output_file.delete()
    return output_files


def remove_preview_file_by_id(preview_file_id, force=False):
    """
    Remove all the files related to the preview file that has the given ID.
    Then remove the preview file entry from the database.
    """
    preview_file = PreviewFile.get(preview_file_id)
    if preview_file is None:
        raise PreviewFileNotFoundException
    return remove_preview_file(preview_file, force=force)


def remove_preview_file(preview_file, force=False, restore_main=True):
    """
    Remove all the files related to the given preview file. Then remove the
    preview file entry from the database.

    The task and the entity that showed it as their main preview get back
    the previous one (see _restore_task_main_preview and
    _restore_entity_main_preview). The bulk removals pass
    restore_main=False, because they remove all the previews of the task or
    of the project. A restore there can select a preview that goes next and
    announce it.
    """
    task = Task.get(preview_file.task_id)
    entity = Entity.get(task.entity_id)
    news = News.get_by(preview_file_id=preview_file.id)
    is_task_main = task.last_preview_file_id == preview_file.id
    is_entity_main = entity.preview_file_id == preview_file.id

    if is_entity_main:
        entity.update({"preview_file_id": None})

    if news is not None:
        news.update({"preview_file_id": None})
        news_service.clear_news_cache([news], task.project_id)
    # The news of a comment lists all the preview files of its revision,
    # also the preview files that it does not point to.
    for comment in preview_file.comments:
        news_service.clear_comment_news_cache(comment.id, task.project_id)

    preview_file_id = str(preview_file.id)
    extension = preview_file.extension

    preview_file.comments = []
    preview_file.save()
    preview_file.delete()
    # The download routes get all their authorization data from the
    # memoized serialization. If the serialization stays, it continues
    # to give the task that the permission check uses. Then the service
    # continues to serve the file.
    files_service.clear_preview_file_cache(preview_file_id)

    # Mark the physical files as deleted only after the DB row is
    # deleted. If the delete fails, the row must not point to missing
    # files. The service always marks them. REMOVE_FILES and force only
    # decide if the purge removes them.
    if extension == "png":
        clear_picture_files(preview_file_id, force=force)
    elif extension == "mp4":
        clear_movie_files(preview_file_id, force=force)
    else:
        clear_generic_files(preview_file_id, force=force)

    if restore_main:
        if is_task_main:
            _restore_task_main_preview(task)
        if is_entity_main:
            _restore_entity_main_preview(entity)
    elif is_entity_main:
        entities_service.clear_entity_cache(entity.id)

    return preview_file.serialize()


def _get_last_main_preview_file(*criterions):
    """
    Return the newest main preview (position 1) that matches the given
    criterions, or None. The search is only on the ready pictures and
    movies, because only these get a thumbnail and become current after an
    upload.
    """
    return (
        PreviewFile.query.join(Task, PreviewFile.task_id == Task.id)
        .filter(PreviewFile.position == 1)
        .filter(PreviewFile.status == "ready")
        .filter(PreviewFile.extension.in_(THUMBNAIL_EXTENSIONS))
        .filter(*criterions)
        .order_by(PreviewFile.created_at.desc())
        .first()
    )


def _restore_task_main_preview(task):
    """
    For a removed preview, undo what its upload did to the task (see
    tasks_service.update_preview_file_info). The task gets back its newest
    remaining main preview. The service tells the clients, so that they
    drop the removed preview.
    """
    last_preview_file = _get_last_main_preview_file(
        PreviewFile.task_id == task.id
    )
    last_preview_file_id = None
    if last_preview_file is not None:
        last_preview_file_id = last_preview_file.id
    task.update({"last_preview_file_id": last_preview_file_id})
    tasks_service.clear_task_cache(task.id)
    events.emit(
        "task:update",
        {"task_id": str(task.id)},
        project_id=str(task.project_id),
    )


def _restore_entity_main_preview(entity):
    """
    For a removed preview, undo what its upload did to the entity. If the
    project sets the preview automatically, the entity gets back the newest
    main preview of all its tasks. An upload on any of these tasks sets it.
    If the project sets it manually, or if no such preview remains, the
    entity has no preview. In all cases, the service tells the clients, so
    that they drop the removed thumbnail.
    """
    main_preview_file = None
    project = projects_service.get_project(str(entity.project_id))
    if project["is_set_preview_automated"]:
        main_preview_file = _get_last_main_preview_file(
            Task.entity_id == entity.id
        )
    if main_preview_file is not None:
        try:
            tasks_service.update_entity_preview(
                entity.id, str(main_preview_file.id)
            )
        except PreviewFileNotFoundException:
            # Another deletion removed the preview file before this call.
            main_preview_file = None
    if main_preview_file is None:
        tasks_service.unset_entity_main_preview(entity.id)


def remove_preview_background_file_by_id(
    preview_background_file_id, force=False
):
    """
    Remove all the files related to the preview background file that has the
    given ID. Then remove the preview background file entry from the
    database.
    """
    preview_background_file = PreviewBackgroundFile.get(
        preview_background_file_id
    )
    if preview_background_file is None:
        raise PreviewBackgroundFileNotFoundException
    return remove_preview_background_file(preview_background_file, force=force)


def remove_preview_background_file(preview_background_file, force=False):
    """
    Remove all the files related to the given preview background file. Then
    remove the preview background file entry from the database.
    """
    clear_preview_background_files(preview_background_file.id, force=force)
    preview_background_file.delete()
    return preview_background_file.serialize()


def _remove_files_quietly(files, force=False):
    """
    Mark all the given (bucket, prefix, id) stored files as deleted in one
    operation. If this fails, log a warning and continue.
    """
    try:
        file_store.remove_files(files, force=force)
    except Exception:
        logger.warning(
            f"Stored files {files} could not be removed.", exc_info=1
        )


def clear_preview_background_files(preview_background_id, force=False):
    """
    Mark as deleted all the files related to the given preview background
    file.
    """
    _remove_files_quietly(
        [
            ("pictures", image_type, str(preview_background_id))
            for image_type in ["thumbnails", "preview-backgrounds"]
        ],
        force=force,
    )


def clear_picture_files(preview_file_id, force=False):
    """
    Mark as deleted all the files related to the given preview file. This
    function supposes that the original file was a picture.
    """
    _remove_files_quietly(
        [
            ("pictures", image_type, str(preview_file_id))
            for image_type in [
                "original",
                "thumbnails",
                "thumbnails-square",
                "previews",
            ]
        ],
        force=force,
    )


def clear_movie_files(preview_file_id, force=False):
    """
    Mark as deleted all the files related to the given preview file. This
    function supposes that the original file was a movie.
    """
    files = [
        ("movies", movie_type, str(preview_file_id))
        for movie_type in files_service.MOVIE_PREFIXES
    ]
    # The movie pipeline also stores the first frame as the "original"
    # picture, with the thumbnails made from it.
    files += [
        ("pictures", image_type, str(preview_file_id))
        for image_type in [
            "original",
            "thumbnails",
            "thumbnails-square",
            "previews",
            "tiles",
        ]
    ]
    _remove_files_quietly(files, force=force)


def clear_generic_files(preview_file_id, force=False):
    """
    Mark as deleted all the files related to the given preview file. This
    function supposes that the original file was a generic file.
    """
    _remove_files_quietly(
        [("files", "previews", str(preview_file_id))], force=force
    )


def _remove_task_batch(task_ids):
    """
    Fully remove the given tasks. If an entity showed a preview of one of
    them, the entity gets its main preview back once, after the last task.
    A restore after each task can select the preview of a task that goes
    next and announce it.
    """
    entity_ids = [
        str(row[0])
        for row in Entity.query.with_entities(Entity.id)
        .join(PreviewFile, Entity.preview_file_id == PreviewFile.id)
        .filter(PreviewFile.task_id.in_(task_ids))
        .all()
    ]
    for task_id in task_ids:
        remove_task(task_id, force=True, restore_main=False)
    for entity_id in entity_ids:
        _restore_entity_main_preview(Entity.get(entity_id))


def remove_tasks(project_id, task_ids):
    """
    Fully remove the given tasks and the related data for the given project.
    The project ID filter makes the permission management easier.
    """
    task_ids = [task_id for task_id in task_ids if fields.is_valid_id(task_id)]
    _remove_task_batch(
        get_task_ids(Task.project_id == project_id, Task.id.in_(task_ids))
    )
    for task_id in task_ids:
        tasks_service.clear_task_cache(task_id)
    return task_ids


def remove_tasks_for_entity(entity_id):
    """
    Fully remove all the tasks and the related data for the given entity.
    The caller deletes the entity next.
    """
    for task_id in get_task_ids(entity_id=entity_id):
        remove_task(task_id, force=True, restore_main=False)


def remove_tasks_for_project_and_task_type(project_id, task_type_id):
    """
    Fully remove all the tasks and the related data for the given project
    and task type.
    """
    task_ids = get_task_ids(project_id=project_id, task_type_id=task_type_id)
    _remove_task_batch(task_ids)
    for task_id in task_ids:
        tasks_service.clear_task_cache(task_id)
    return task_ids


def remove_production_schedule_versions_for_project(project_id):
    """
    Delete the production schedule versions of a project and their task
    links. This function does it explicitly for these reasons:

    - Until migration d7a3e5b1c9f2, the databases initialized from the
      squashed migration had no delete rule on the keys of these tables.
    - The table references itself through ``production_schedule_from``.
    """
    version_ids = [
        str(row[0])
        for row in ProductionScheduleVersion.query.with_entities(
            ProductionScheduleVersion.id
        )
        .filter_by(project_id=project_id)
        .all()
    ]
    if not version_ids:
        return

    # Remove the self-references, so that the rows can be deleted in any
    # order.
    ProductionScheduleVersion.query.filter(
        ProductionScheduleVersion.production_schedule_from.in_(version_ids)
    ).update({"production_schedule_from": None}, synchronize_session=False)
    ProductionScheduleVersionTaskLink.query.filter(
        ProductionScheduleVersionTaskLink.production_schedule_version_id.in_(
            version_ids
        )
    ).delete(synchronize_session=False)
    ProductionScheduleVersion.delete_all_by(project_id=project_id)


def remove_old_events(days_old=90):
    """
    Remove the events that are older than *days_old*.
    """
    _remove_older_than(ApiEvent, ApiEvent.created_at, days_old)


def remove_old_login_logs(days_old=90):
    """
    Remove the login logs that are older than *days_old*.
    """
    _remove_older_than(LoginLog, LoginLog.created_at, days_old)


def remove_old_notifications(days_old=90):
    """
    Remove the notifications that are older than *days_old*.
    """
    _remove_older_than(Notification, Notification.created_at, days_old)


def remove_preview_file_row(preview_file_id):
    """
    Delete a preview file row and tell the clients. Do nothing more: do not
    remove a stored binary, and do not change a task or an entity that
    points to it. The full cascade is remove_preview_file. Keep this name
    different from it.
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    preview_file.delete()
    files_service.clear_preview_file_cache(str(preview_file_id))
    task = Task.get(preview_file.task_id)
    events.emit(
        "preview-file:delete",
        {"preview_file_id": preview_file_id},
        project_id=str(task.project_id),
    )
    return preview_file.serialize()
