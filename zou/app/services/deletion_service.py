import datetime
from sqlalchemy.exc import IntegrityError


from zou.app.models.attachment_file import AttachmentFile
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

from zou.app.services.exception import (
    AttachmentFileNotFoundException,
    CommentNotFoundException,
    ModelWithRelationsDeletionException,
    PersonInProtectedAccounts,
)


def remove_comment(comment_id):
    """
    Remove a comment from database and everything related (notifs, news, and
    preview files)
    """
    comment = Comment.get(comment_id)
    if comment is not None:
        task = Task.get(comment.object_id)
        notifications = Notification.query.filter_by(comment_id=comment.id)
        for notification in notifications:
            notification.delete()

        news_list = News.query.filter_by(comment_id=comment.id)
        for news in news_list:
            news.delete()

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
            return comment.serialize()
    else:
        raise CommentNotFoundException


def remove_task(task_id, force=False):
    """
    Remove given task. Force deletion if the task has some comments and files
    related. This will lead to the deletion of all of them.
    """
    from zou.app.services import tasks_service

    task = Task.get(task_id)
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
            news_list = News.query.filter_by(comment_id=comment.id)
            for news in news_list:
                news.delete()
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

        news_list = News.query.filter_by(task_id=task.id)
        for news in news_list:
            news.delete()

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


def remove_preview_file_by_id(preview_file_id, force=False):
    preview_file = PreviewFile.get(preview_file_id)
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

    if config.REMOVE_FILES or force:
        if preview_file.extension == "png":
            clear_picture_files(preview_file.id)
        elif preview_file.extension == "mp4":
            clear_movie_files(preview_file.id)
        else:
            clear_generic_files(preview_file.id)

    preview_file.comments = []
    preview_file.save()
    preview_file.delete()

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
    if config.REMOVE_FILES:
        file_store.remove_file("attachments", str(attachment_file.id))
    attachment_dict = attachment_file.serialize()
    attachment_file.delete()
    return attachment_dict


def clear_preview_background_files(preview_background_id, force=False):
    """
    Remove all files related to given preview background file.
    """
    if config.REMOVE_FILES or force:
        for image_type in [
            "thumbnails",
            "preview-backgrounds",
        ]:
            try:
                file_store.remove_picture(image_type, preview_background_id)
            except BaseException:
                pass


def clear_picture_files(preview_file_id):
    """
    Remove all files related to given preview file, supposing the original file
    was a picture.
    """
    for image_type in [
        "original",
        "thumbnails",
        "thumbnails-square",
        "previews",
    ]:
        try:
            file_store.remove_picture(image_type, preview_file_id)
        except BaseException:
            pass


def clear_movie_files(preview_file_id):
    """
    Remove all files related to given preview file, supposing the original file
    was a movie.
    """
    try:
        file_store.remove_movie("previews", preview_file_id)
    except BaseException:
        pass
    for image_type in ["thumbnails", "thumbnails-square", "previews"]:
        try:
            file_store.remove_picture(image_type, preview_file_id)
        except BaseException:
            pass


def clear_generic_files(preview_file_id):
    """
    Remove all files related to given preview file, supposing the original file
    was a generic file.
    """
    try:
        file_store.remove_file("previews", preview_file_id)
    except BaseException:
        pass


def remove_tasks(project_id, task_ids):
    """
    Remove fully given tasks and related for given project. The project id
    filter is there to facilitate right management.
    """
    task_ids = [task_id for task_id in task_ids if fields.is_valid_id(task_id)]
    tasks = Task.query.filter(Project.id == project_id).filter(
        Task.id.in_(task_ids)
    )
    for task in tasks:
        remove_task(task.id, force=True)
    return task_ids


def remove_tasks_for_project_and_task_type(project_id, task_type_id):
    """
    Remove fully all tasks and related for given project and task type.
    """
    tasks = Task.query.filter_by(
        project_id=project_id, task_type_id=task_type_id
    )
    task_ids = []
    for task in tasks:
        remove_task(task.id, force=True)
        task_ids.append(str(task.id))
    return task_ids


def remove_project(project_id):
    from zou.app.services import playlists_service

    tasks = Task.query.filter_by(project_id=project_id)
    for task in tasks:
        remove_task(task.id, force=True)

    query = EntityLink.query.join(
        Entity, EntityLink.entity_in_id == Entity.id
    ).filter(Entity.project_id == project_id)
    for link in query:
        link.delete_no_commit()
    EntityLink.commit()

    query = EntityVersion.query.join(
        Entity, EntityVersion.entity_id == Entity.id
    ).filter(Entity.project_id == project_id)
    for version in query:
        version.delete_no_commit()
    EntityLink.commit()

    playlists = Playlist.query.filter_by(project_id=project_id)
    for playlist in playlists:
        playlists_service.remove_playlist(playlist.id)

    ApiEvent.delete_all_by(project_id=project_id)
    Entity.delete_all_by(project_id=project_id)

    descriptors = MetadataDescriptor.query.filter_by(project_id=project_id)
    for descriptor in descriptors:
        descriptor.departments = []
        descriptor.save()
    MetadataDescriptor.delete_all_by(project_id=project_id)
    Milestone.delete_all_by(project_id=project_id)
    ScheduleItem.delete_all_by(project_id=project_id)
    SearchFilterGroup.delete_all_by(project_id=project_id)
    SearchFilter.delete_all_by(project_id=project_id)

    for news in News.query.join(Task).filter_by(project_id=project_id).all():
        news.delete_no_commit()
    News.commit()
    project = Project.get(project_id)
    project.delete()
    events.emit("project:delete", {"project_id": project.id})
    return project_id


def remove_person(person_id, force=True):
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
        SearchFilterGroup.delete_all_by(person_id=person_id)
        SearchFilter.delete_all_by(person_id=person_id)
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
        for task in Task.query.filter(Task.assignees.contains(person)):
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
    limit_date = date_helpers.get_utc_now_datetime() - datetime.timedelta(
        days=days_old
    )
    ApiEvent.query.filter(ApiEvent.created_at < limit_date).delete()
    ApiEvent.commit()


def remove_old_login_logs(days_old=90):
    """
    Remove login logs older than *days_old*.
    """
    limit_date = date_helpers.get_utc_now_datetime() - datetime.timedelta(
        days=days_old
    )
    LoginLog.query.filter(LoginLog.created_at < limit_date).delete()
    LoginLog.commit()


def remove_old_notifications(days_old=90):
    """
    Remove notifications older than *days_old*.
    """
    limit_date = date_helpers.get_utc_now_datetime() - datetime.timedelta(
        days=days_old
    )
    Notification.query.filter(Notification.created_at < limit_date).delete()
    Notification.commit()


def remove_episode(episode_id, force=False):
    """
    Remove an episode and all related sequences and shots.
    """
    from zou.app.services import shots_service, assets_service, tasks_service

    episode = shots_service.get_episode_raw(episode_id)
    if force:
        for sequence in Entity.get_all_by(parent_id=episode_id):
            shots_service.remove_sequence(sequence.id, force=True)
        for asset in Entity.get_all_by(source_id=episode_id):
            assets_service.remove_asset(asset.id, force=True)
        tasks = Task.query.filter_by(entity_id=episode_id).all()
        for task in tasks:
            remove_task(task.id, force=True)
            tasks_service.clear_task_cache(str(task.id))
        Playlist.delete_all_by(episode_id=episode_id)
        ScheduleItem.delete_all_by(object_id=episode_id)
        EntityVersion.delete_all_by(entity_id=episode_id)
        Subscription.delete_all_by(entity_id=episode_id)
        EntityLink.delete_all_by(entity_in_id=episode_id)
        EntityLink.delete_all_by(entity_out_id=episode_id)
        EntityConceptLink.delete_all_by(entity_in_id=episode_id)
        EntityConceptLink.delete_all_by(entity_out_id=episode_id)
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
