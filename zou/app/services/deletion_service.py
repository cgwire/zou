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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.budget import Budget
from zou.app.models.budget_entry import BudgetEntry
from zou.app.models.comment import Comment
from zou.app.models.desktop_login_log import DesktopLoginLog
from zou.app.models.entity import (
    Entity,
    EntityLink,
    EntityVersion,
    EntityConceptLink,
)
from zou.app.models.event import ApiEvent
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.login_log import LoginLog
from zou.app.models.milestone import Milestone
from zou.app.models.notification import Notification
from zou.app.models.news import News
from zou.app.models.output_file import OutputFile
from zou.app.models.person import Person
from zou.app.models.playlist import Playlist
from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.models.preview_file import PreviewFile
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)
from zou.app.models.project import Project
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.search_filter import SearchFilter
from zou.app.models.search_filter_group import SearchFilterGroup
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task
from zou.app.models.time_spent import TimeSpent
from zou.app.models.working_file import WorkingFile

from zou.app.utils import events, fields, date_helpers
from zou.app.stores import file_store
from zou.app import config

from zou.app.services import base_service, files_service
from zou.app.exceptions import (
    ProjectNotFoundException,
    AttachmentFileNotFoundException,
    CommentNotFoundException,
    EntityNotFoundException,
    ModelWithRelationsDeletionException,
    PersonInProtectedAccounts,
    PreviewBackgroundFileNotFoundException,
    PreviewFileNotFoundException,
)

logger = logging.getLogger(__name__)


def _remove_quietly(remove_from_store, prefix, file_id, force=False):
    """
    Mark a stored file deleted, ignoring a failure: the database row is
    already gone, a leftover object in the store must not fail the
    deletion.
    """
    try:
        remove_from_store(prefix, file_id, force=force)
    except Exception:
        logger.warning(
            f"Stored file {prefix}-{file_id} could not be removed.", exc_info=1
        )


def _remove_older_than(model, date_column, days_old):
    """
    Delete every row of given model older than *days_old*.
    """
    limit_date = date_helpers.get_utc_now_datetime() - datetime.timedelta(
        days=days_old
    )
    model.query.filter(date_column < limit_date).delete()
    model.commit()


def _remove_search_filters(**kw):
    """
    Delete the search filters and search filter groups matching given
    column values. A group takes the filters it holds with it, whoever
    owns them, as removing a single group does: they go first, since they
    reference their group. A shared filter shows in the listing of every
    user, so the memoized listings are dropped for all of them.
    """
    from zou.app.services import user_service

    group_ids = SearchFilterGroup.query.with_entities(
        SearchFilterGroup.id
    ).filter_by(**kw)
    SearchFilter.delete_all_by(
        SearchFilter.search_filter_group_id.in_(group_ids)
    )
    SearchFilter.delete_all_by(**kw)
    SearchFilterGroup.delete_all_by(**kw)
    user_service.clear_filter_cache()
    user_service.clear_filter_group_cache()


def _get_task_ids(*criterions, **kw):
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

    from zou.app.services import news_service

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
        remove_attachment_file(attachment)

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
    from zou.app.services import news_service, tasks_service

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
            from zou.app.services import tasks_service

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


def remove_attachment_file_by_id(attachment_file_id):
    """
    Remove all files related to given attachment file, then remove the
    attachment file entry from the database.
    """
    attachment_file = AttachmentFile.get(attachment_file_id)
    if attachment_file is None:
        raise AttachmentFileNotFoundException
    return remove_attachment_file(attachment_file)


def remove_attachment_file(attachment_file):
    """
    Remove all files related to given attachment file, then remove the
    attachment file entry from the database.
    """
    from zou.app.services import comments_service

    _remove_quietly(file_store.remove_file, "attachments", attachment_file.id)
    attachment_dict = attachment_file.serialize()
    attachment_file.delete()
    comments_service.clear_attachment_file_cache(attachment_dict["id"])
    return attachment_dict


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
    for task_id in _get_task_ids(
        Task.project_id == project_id, Task.id.in_(task_ids)
    ):
        remove_task(task_id, force=True)
    return task_ids


def remove_entities(project_id, entity_ids, force=False):
    """
    Delete a list of a project's entities, dispatching each to the right
    removal by its type (asset, shot, edit, concept). Without force, entities
    with tasks are canceled on first deletion, then removed for real when
    already canceled; concepts are always removed. With force, every entity is
    removed for real along with its tasks. Absent entities and entities that
    do not belong to the project or are not one of those types are skipped.
    Returns the ids of the entities that were removed.
    """
    from zou.app.services import (
        assets_service,
        concepts_service,
        edits_service,
        entities_service,
        shots_service,
    )

    shot_type_id = shots_service.get_shot_type()["id"]
    edit_type_id = edits_service.get_edit_type()["id"]
    concept_type_id = concepts_service.get_concept_type()["id"]

    to_remove = []
    for entity_id in entity_ids:
        try:
            entity = entities_service.get_entity(entity_id)
        except EntityNotFoundException:
            # Already gone (e.g. deleted by someone else): the deletion is
            # idempotent, skip it like remove_tasks ignores unknown ids.
            continue
        if entity["project_id"] != project_id:
            continue
        entity_type_id = entity["entity_type_id"]
        entity_force = force or entity["canceled"]
        if entity_type_id == shot_type_id:
            remove = shots_service.remove_shot
        elif entity_type_id == edit_type_id:
            remove = edits_service.remove_edit
        elif entity_type_id == concept_type_id:
            remove = concepts_service.remove_concept
            entity_force = True
        elif assets_service.is_asset_dict(entity):
            remove = assets_service.remove_asset
        else:
            continue
        to_remove.append((entity_id, remove, entity_force))

    for entity_id, remove, entity_force in to_remove:
        remove(entity_id, force=entity_force)
    return [entity_id for entity_id, _, _ in to_remove]


def remove_tasks_for_entity(entity_id):
    """
    Remove fully all tasks and related for given entity.
    """
    for task_id in _get_task_ids(entity_id=entity_id):
        remove_task(task_id, force=True)


def remove_tasks_for_project_and_task_type(project_id, task_type_id):
    """
    Remove fully all tasks and related for given project and task type.
    """
    task_ids = _get_task_ids(project_id=project_id, task_type_id=task_type_id)
    for task_id in task_ids:
        remove_task(task_id, force=True)
    return task_ids


def remove_project(project_id):
    """
    Remove a project and everything it owns: previews, tasks, budgets, entity
    links, playlists, entities, metadata, schedule and news.
    """
    from zou.app.services import playlists_service

    preview_files = (
        PreviewFile.query.join(Task)
        .filter(Task.project_id == project_id)
        .all()
    )
    for preview_file in preview_files:
        remove_preview_file(preview_file, force=True)

    for task_id in _get_task_ids(project_id=project_id):
        remove_task(task_id, force=True)

    budgets = Budget.get_all_by(project_id=project_id)
    for budget in budgets:
        BudgetEntry.delete_all_by(budget_id=budget.id)
        budget.delete()

    EntityLink.query.filter(
        EntityLink.entity_in_id == Entity.id,
        Entity.project_id == project_id,
    ).delete()
    EntityConceptLink.query.filter(
        EntityConceptLink.entity_in_id == Entity.id,
        Entity.project_id == project_id,
    ).delete()
    EntityConceptLink.query.filter(
        EntityConceptLink.entity_out_id == Entity.id,
        Entity.project_id == project_id,
    ).delete()
    EntityVersion.query.filter(
        EntityVersion.entity_id == Entity.id, Entity.project_id == project_id
    ).delete()
    playlists = Playlist.query.filter_by(project_id=project_id)
    for playlist in playlists:
        playlists_service.remove_playlist(playlist.id)

    ApiEvent.delete_all_by(project_id=project_id)
    remove_output_files_for_project(project_id)
    Entity.delete_all_by(project_id=project_id)

    descriptors = MetadataDescriptor.query.filter_by(project_id=project_id)
    for descriptor in descriptors:
        descriptor.departments = []
        descriptor.save()
    MetadataDescriptor.delete_all_by(project_id=project_id)
    Milestone.delete_all_by(project_id=project_id)
    ScheduleItem.delete_all_by(project_id=project_id)
    remove_production_schedule_versions_for_project(project_id)
    _remove_search_filters(project_id=project_id)
    News.query.filter(
        News.task_id == Task.id, Task.project_id == project_id
    ).delete()
    project = base_service.get_instance(
        Project, project_id, ProjectNotFoundException
    )
    project.delete()
    events.emit("project:delete", {"project_id": project.id})
    return project_id


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


def remove_person(person_id, force=True):
    """
    Remove a person. With force, everything they own is deleted or detached
    first: comments, notifications, logs, subscriptions, time spents, team
    memberships and task assignations.
    """
    person = Person.get(person_id)
    if person.email in config.PROTECTED_ACCOUNTS:
        raise PersonInProtectedAccounts(
            "Can't delete this person it's a protected account."
        )
    if force:
        for comment in Comment.get_all_by(person_id=person_id):
            remove_comment(comment.id)
        comments = Comment.query.filter(
            Comment.acknowledgements.contains(person)
        )
        for comment in comments:
            comment.acknowledgements = [
                member
                for member in comment.acknowledgements
                if str(member.id) != person_id
            ]
            comment.save()
        ApiEvent.delete_all_by(user_id=person_id)
        Notification.delete_all_by(person_id=person_id)
        Notification.delete_all_by(author_id=person_id)
        _remove_search_filters(person_id=person_id)
        DesktopLoginLog.delete_all_by(person_id=person_id)
        LoginLog.delete_all_by(person_id=person_id)
        Subscription.delete_all_by(person_id=person_id)
        TimeSpent.delete_all_by(person_id=person_id)
        for project in Project.query.filter(Project.team.contains(person)):
            project.team = [
                member
                for member in project.team
                if str(member.id) != person_id
            ]
            project.save()
        for task in Task.query.options(selectinload(Task.assignees)).filter(
            Task.assignees.contains(person)
        ):
            task.assignees = [
                assignee
                for assignee in task.assignees
                if str(assignee.id) != person_id
            ]
            task.save()
        for task in Task.get_all_by(assigner_id=person_id):
            task.update({"assigner_id": None})
        for output_file in OutputFile.get_all_by(person_id=person_id):
            output_file.update({"person_id": None})
        for working_file in WorkingFile.get_all_by(person_id=person_id):
            working_file.update({"person_id": None})
        for preview_file in PreviewFile.get_all_by(person_id=person_id):
            preview_file.update({"person_id": None})
    try:
        person.delete()
        events.emit("person:delete", {"person_id": person.id})
    except IntegrityError:
        raise ModelWithRelationsDeletionException(
            "Some data are still linked to given person."
        )

    return person.serialize_safe()


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


def remove_episode(episode_id, force=False):
    """
    Remove an episode and all related sequences and shots.
    """
    from zou.app.services import shots_service, assets_service

    episode = shots_service.get_episode_raw(episode_id)
    if force:
        for sequence in Entity.get_all_by(parent_id=episode_id):
            shots_service.remove_sequence(sequence.id, force=True)
        for asset in Entity.get_all_by(source_id=episode_id):
            assets_service.remove_asset(asset.id, force=True)
        remove_tasks_for_entity(episode_id)
        Playlist.delete_all_by(episode_id=episode_id)
        ScheduleItem.delete_all_by(object_id=episode_id)
        EntityVersion.delete_all_by(entity_id=episode_id)
        Subscription.delete_all_by(entity_id=episode_id)
        EntityLink.delete_all_by(entity_in_id=episode_id)
        EntityLink.delete_all_by(entity_out_id=episode_id)
        EntityConceptLink.delete_all_by(entity_in_id=episode_id)
        EntityConceptLink.delete_all_by(entity_out_id=episode_id)
        remove_output_files_for_entity(episode_id)
    try:
        episode.delete()
        events.emit(
            "episode:delete",
            {"episode_id": episode_id},
            project_id=str(episode.project_id),
        )
    except IntegrityError:
        raise ModelWithRelationsDeletionException(
            "Some data are still linked to this episode."
        )
    shots_service.clear_episode_cache(episode_id)
    return episode.serialize(obj_type="Episode")
