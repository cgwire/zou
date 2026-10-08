"""
Cascading removals: what goes with a task, a preview, an entity, an episode
or a whole project.

This is the top of the service layers, above the entity services (assets,
shots, edits, concepts) that call remove_task for their force branch. Those
services are imported inside the functions that need them rather than at
module level: importing them here at module level would close the cycle
they open by importing this module.
"""

import logging
import datetime

from zou.app.models.comment import Comment
from zou.app.models.entity import (
    Entity,
)
from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog
from zou.app.models.notification import Notification
from zou.app.models.news import News
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

from zou.app.utils import events, fields, date_helpers
from zou.app.stores import file_store

from zou.app.services import (
    files_service,
    news_service,
    tasks_service,
    attachment_files_service,
)
from zou.app.exceptions import (
    CommentNotFoundException,
    PreviewBackgroundFileNotFoundException,
    PreviewFileNotFoundException,
)

logger = logging.getLogger(__name__)


def _remove_older_than(model, date_column, days_old):
    """
    Delete every row of given model older than *days_old*.
    """
    limit_date = date_helpers.get_utc_now_datetime() - datetime.timedelta(
        days=days_old
    )
    model.query.filter(date_column < limit_date).delete()
    model.commit()


def get_task_ids(*criterions, **kw):
    """
    Return the ids of the tasks matching given filters, as strings. The
    removal loops walk these rather than ORM instances: every removal
    commits, which expires the instances left to walk, and reading the id
    of one that another request deleted meanwhile would raise
    ObjectDeletedError. remove_task skips a task that is already gone.
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
    Remove a comment from database and everything related (notifs, news, and
    preview files)
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
            {"comment_id": comment.id},
            project_id=str(task.project_id),
        )
    else:
        # The task may already be gone; still notify listeners so
        # they drop the comment from their state.
        events.emit("comment:delete", {"comment_id": comment.id})
    return comment.serialize()


def remove_task(task_id, force=False):
    """
    Remove given task. Force deletion if the task has some comments and files
    related. This will lead to the deletion of all of them.
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

        preview_files = PreviewFile.query.filter_by(task_id=task_id)
        for preview_file in preview_files:
            remove_preview_file(preview_file)

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
    Remove all OutputFile rows that reference the given entity (entity_id).
    This avoids FK violation when deleting the entity. Clears PreviewFile
    source_file_id references before deleting each OutputFile.
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
    Remove all OutputFile rows that reference any entity in the project.
    Called after preview files and tasks are already removed, so no need to
    clear PreviewFile.source_file_id.
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
    Remove all files related to the preview file matching given id, then
    remove the preview file entry from the database.
    """
    preview_file = PreviewFile.get(preview_file_id)
    if preview_file is None:
        raise PreviewFileNotFoundException
    return remove_preview_file(preview_file, force=force)


def remove_preview_file(preview_file, force=False):
    """
    Remove all files related to given preview file, then remove the preview file
    entry from the database.
    """
    task = Task.get(preview_file.task_id)
    entity = Entity.get(task.entity_id)
    news = News.get_by(preview_file_id=preview_file.id)

    if entity.preview_file_id == preview_file.id:
        entity.update({"preview_file_id": None})

    if news is not None:
        news.update({"preview_file_id": None})

    preview_file_id = str(preview_file.id)
    extension = preview_file.extension

    preview_file.comments = []
    preview_file.save()
    preview_file.delete()
    # The download routes read their whole authorization off the memoized
    # serialization: left in place, it keeps handing out the task the
    # permission is checked against, and the file goes on being served.
    files_service.clear_preview_file_cache(preview_file_id)

    # Mark the physical files deleted only once the DB row is gone: if
    # the delete fails, the row must not end up pointing at missing files.
    # They are always marked, REMOVE_FILES and force only decide whether
    # the purge removes them.
    if extension == "png":
        clear_picture_files(preview_file_id, force=force)
    elif extension == "mp4":
        clear_movie_files(preview_file_id, force=force)
    else:
        clear_generic_files(preview_file_id, force=force)

    # Update last preview file uploaded on task
    if task.last_preview_file_id == preview_file.id:
        new_last_preview_file = (
            PreviewFile.query.filter(
                PreviewFile.task_id == preview_file.task_id
            )
            .order_by(PreviewFile.created_at.desc())
            .first()
        )
        if new_last_preview_file is not None:

            tasks_service.update_preview_file_info(
                new_last_preview_file.serialize()
            )
        else:
            task.update({"last_preview_file_id": None})

    return preview_file.serialize()


def remove_preview_background_file_by_id(
    preview_background_file_id, force=False
):
    """
    Remove all files related to given preview background file, then remove the
    preview background file entry from the database.
    """
    preview_background_file = PreviewBackgroundFile.get(
        preview_background_file_id
    )
    if preview_background_file is None:
        raise PreviewBackgroundFileNotFoundException
    return remove_preview_background_file(preview_background_file, force=force)


def remove_preview_background_file(preview_background_file, force=False):
    """
    Remove all files related to given preview background file, then remove the
    preview background file entry from the database.
    """
    clear_preview_background_files(preview_background_file.id, force=force)
    preview_background_file.delete()
    return preview_background_file.serialize()


def _remove_files_quietly(files, force=False):
    """
    Mark deleted the given (bucket, prefix, id) stored files at once,
    ignoring a failure, see _remove_quietly.
    """
    try:
        file_store.remove_files(files, force=force)
    except Exception:
        logger.warning(
            f"Stored files {files} could not be removed.", exc_info=1
        )


def clear_preview_background_files(preview_background_id, force=False):
    """
    Mark deleted all files related to given preview background file.
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
    Mark deleted all files related to given preview file, supposing the
    original file was a picture.
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
    Mark deleted all files related to given preview file, supposing the
    original file was a movie.
    """
    files = [
        ("movies", movie_type, str(preview_file_id))
        for movie_type in files_service.MOVIE_PREFIXES
    ]
    # The movie pipeline also stores the first frame as the "original"
    # picture, next to the thumbnails cut from it.
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
    Mark deleted all files related to given preview file, supposing the
    original file was a generic file.
    """
    _remove_files_quietly(
        [("files", "previews", str(preview_file_id))], force=force
    )


def remove_tasks(project_id, task_ids):
    """
    Remove fully given tasks and related for given project. The project id
    filter is there to facilitate right management.
    """
    task_ids = [task_id for task_id in task_ids if fields.is_valid_id(task_id)]
    for task_id in get_task_ids(
        Task.project_id == project_id, Task.id.in_(task_ids)
    ):
        remove_task(task_id, force=True)
    return task_ids


def remove_tasks_for_entity(entity_id):
    """
    Remove fully all tasks and related for given entity.
    """
    for task_id in get_task_ids(entity_id=entity_id):
        remove_task(task_id, force=True)


def remove_tasks_for_project_and_task_type(project_id, task_type_id):
    """
    Remove fully all tasks and related for given project and task type.
    """
    task_ids = get_task_ids(project_id=project_id, task_type_id=task_type_id)
    for task_id in task_ids:
        remove_task(task_id, force=True)
    return task_ids


def remove_production_schedule_versions_for_project(project_id):
    """
    Delete production schedule versions of a project together with their
    task links. Done explicitly because, until migration d7a3e5b1c9f2, the
    databases initialized from the squashed migration had no delete rule on
    the keys of these tables, and the table self-references through
    ``production_schedule_from``.
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

    # Break self-references so the rows can be deleted in any order.
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
    Remove events older than *days_old*.
    """
    _remove_older_than(ApiEvent, ApiEvent.created_at, days_old)


def remove_old_login_logs(days_old=90):
    """
    Remove login logs older than *days_old*.
    """
    _remove_older_than(LoginLog, LoginLog.created_at, days_old)


def remove_old_notifications(days_old=90):
    """
    Remove notifications older than *days_old*.
    """
    _remove_older_than(Notification, Notification.created_at, days_old)


def remove_preview_file_row(preview_file_id):
    """
    Delete a preview file row and tell the clients, nothing else: no
    stored binary, no task or entity pointing at it. The whole cascade is
    remove_preview_file, which this name stays apart from.
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
