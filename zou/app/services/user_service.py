from collections import defaultdict

from sqlalchemy.orm import aliased, selectinload
from sqlalchemy import func, and_
from sqlalchemy.exc import DataError

from zou.app.models.comment import Comment
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.models.playlist import Playlist
from zou.app.models.project import Project, ProjectPersonLink
from zou.app.models.project_status import ProjectStatus
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType

from zou.app.services import (
    custom_actions_service,
    permissions_service,
    persons_service,
    plugins_service,
    projects_service,
    status_automations_service,
    files_service,
    departments_service,
    entity_types_service,
    organisation_service,
    subscriptions_service,
    task_types_service,
    search_filters_service,
    entities_service,
)
from zou.app.exceptions import (
    NotificationNotFoundException,
    WrongParameterException,
    ProjectNotFoundException,
)
from zou.app.utils import cache, fields, permissions, events


def clear_open_projects_cache():
    """
    Drop the memoized open project list.
    """
    cache.cache.delete_memoized(get_open_projects)


def build_team_filter():
    """
    Query filter for task to retrieve only models from project for which the
    user is part of the team.
    """
    current_user = persons_service.get_current_user_raw()
    return Project.team.contains(current_user)


def build_related_projects_filter():
    """
    Query filter for project to retrieve open projects of which the user
    is part of the team.
    """
    projects = related_projects()
    project_ids = [project["id"] for project in projects]
    if len(project_ids) > 0:
        return Project.id.in_(project_ids)
    else:
        return Project.id.in_(["00000000-0000-0000-0000-000000000000"])


def related_projects():
    """
    Return all projects related to current user: open projects of which the user
    is part of the team as dicts.
    """
    projects = related_projects_raw()
    return Project.serialize_list(projects)


def related_projects_raw():
    """
    Return all projects related to current user: open projects of which the user
    is part of the team as models.
    """
    current_user = persons_service.get_current_user()
    projects = (
        Project.query.join(
            ProjectStatus, Project.project_status_id == ProjectStatus.id
        )
        .join(ProjectPersonLink, Project.id == ProjectPersonLink.project_id)
        .filter(ProjectPersonLink.person_id == current_user["id"])
        .filter(projects_service.build_open_project_filter())
        .distinct()
        .all()
    )
    return projects


def get_tasks_for_entity(entity_id):
    """
    Get all tasks assigned to current user and related to given entity.
    """
    query = (
        Task.query.join(Project)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .filter(Task.entity_id == entity_id)
        .filter(persons_service.build_assignee_filter())
        .filter(projects_service.build_open_project_filter())
    )

    return fields.serialize_value(query.all())


def get_task_types_for_entity(entity_id):
    """
    Get all task types of tasks assigned to current user and related to given
    entity.
    """
    query = (
        TaskType.query.join(Task)
        .join(Project)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .filter(Task.entity_id == entity_id)
        .filter(persons_service.build_assignee_filter())
        .filter(projects_service.build_open_project_filter())
    )

    return fields.serialize_value(query.all())


def get_assets_for_asset_type(project_id, asset_type_id):
    """
    Get all assets for given asset type anp project and for which user has
    a task related.
    """
    query = (
        Entity.query.join(EntityType)
        .join(Project)
        .join(Task, Task.entity_id == Entity.id)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .filter(EntityType.id == asset_type_id)
        .filter(Project.id == project_id)
        .filter(persons_service.build_assignee_filter())
        .filter(projects_service.build_open_project_filter())
    )

    return Entity.serialize_list(query.all(), obj_type="Asset")


def get_asset_types_for_project(project_id):
    """
    Get all asset types for which there is an asset for which current user has a
    task assigned. Assets are listed in given project.
    """
    query = (
        EntityType.query.join(Entity, Entity.entity_type_id == EntityType.id)
        .join(Task, Task.entity_id == Entity.id)
        .join(Project)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .filter(Project.id == project_id)
        .filter(persons_service.build_assignee_filter())
        .filter(projects_service.build_open_project_filter())
        .filter(entity_types_service.build_asset_type_filter())
    )

    return EntityType.serialize_list(query.all(), obj_type="AssetType")


def get_sequences_for_project(project_id):
    """
    Return all sequences for given project and for which current user has
    a task assigned to a shot.
    """
    shot_type = entity_types_service.get_shot_type()
    sequence_type = entity_types_service.get_sequence_type()

    Shot = aliased(Entity, name="shot")
    query = (
        Entity.query.join(Shot, Shot.parent_id == Entity.id)
        .join(Task, Task.entity_id == Shot.id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .join(Project, Project.id == Entity.project_id)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .filter(Shot.entity_type_id == shot_type["id"])
        .filter(Entity.entity_type_id == sequence_type["id"])
        .filter(Project.id == project_id)
        .filter(persons_service.build_assignee_filter())
        .filter(projects_service.build_open_project_filter())
    )

    return Entity.serialize_list(query.all(), obj_type="Sequence")


def get_project_episodes(project_id):
    """
    Return all episodes for given project and for which current user has
    a task assigned to a shot.
    """
    shot_type = entity_types_service.get_shot_type()
    sequence_type = entity_types_service.get_sequence_type()
    episode_type = entity_types_service.get_episode_type()

    Shot = aliased(Entity, name="shot")
    Sequence = aliased(Entity, name="sequence")
    query = (
        Entity.query.join(Sequence, Sequence.parent_id == Entity.id)
        .join(Shot, Shot.parent_id == Sequence.id)
        .join(Task, Task.entity_id == Shot.id)
        .join(Project, Project.id == Entity.project_id)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .filter(Shot.entity_type_id == shot_type["id"])
        .filter(Sequence.entity_type_id == sequence_type["id"])
        .filter(Entity.entity_type_id == episode_type["id"])
        .filter(Project.id == project_id)
        .filter(persons_service.build_assignee_filter())
        .filter(projects_service.build_open_project_filter())
    )

    return Entity.serialize_list(query.all(), obj_type="Episode")


def get_shots_for_sequence(sequence_id):
    """
    Get all shots for given sequence and for which the user has a task assigned.
    """
    shot_type = entity_types_service.get_shot_type()
    query = (
        Entity.query.join(Task)
        .join(Project)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .join(EntityType)
        .filter(Entity.entity_type_id == shot_type["id"])
        .filter(Entity.parent_id == sequence_id)
        .filter(persons_service.build_assignee_filter())
        .filter(projects_service.build_open_project_filter())
    )

    return Entity.serialize_list(query.all(), obj_type="Shot")


def get_scenes_for_sequence(sequence_id):
    """
    Get all layout scenes for given sequence and for which the user has a task
    assigned.
    """
    scene_type = entity_types_service.get_scene_type()
    query = (
        Entity.query.join(Task)
        .join(Project)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .join(EntityType)
        .filter(Entity.entity_type_id == scene_type["id"])
        .filter(Entity.parent_id == sequence_id)
        .filter(persons_service.build_assignee_filter())
        .filter(projects_service.build_open_project_filter())
    )

    return Entity.serialize_list(query.all(), obj_type="Scene")


def get_open_projects(name=None):
    """
    Get all open projects for which current user is part of the team, the
    metadata descriptors of each narrowed on the role held on it.
    """
    query = Project.query.join(
        ProjectStatus, Project.project_status_id == ProjectStatus.id
    ).filter(projects_service.build_open_project_filter())

    if name is not None:
        query = query.filter(Project.name == name)

    if not permissions.has_admin_permissions():
        current_user = persons_service.get_current_user()
        query = query.join(
            ProjectPersonLink, Project.id == ProjectPersonLink.project_id
        )
        query = query.filter(ProjectPersonLink.person_id == current_user["id"])

    projects = query.all()
    return projects_service.serialize_projects_with_extra_data(
        projects,
        get_descriptor_visibilities([project.id for project in projects]),
    )


def get_descriptor_visibilities(project_ids):
    """
    Return the (project_ids, for_client, vendor_departments) triples
    narrowing the metadata descriptors of given projects for the current
    user, grouped on the role held on each. A listing resolves no project,
    so a role check would read the global role for every project listed:
    the role set on each team link is read instead. An admin keeps the
    global role, as in the project access check.
    """
    current_user = persons_service.get_current_user()
    project_roles = {}
    if not permissions.has_admin_permissions():
        project_roles = get_project_roles()

    project_ids_by_role = defaultdict(list)
    for project_id in project_ids:
        role = project_roles.get(str(project_id))
        if role in (None, "admin"):
            # An admin slot is invalid data, which the role checks read as
            # the global role too.
            role = current_user["role"]
        project_ids_by_role[role].append(project_id)
    descriptor_visibilities = []
    for role, role_project_ids in project_ids_by_role.items():
        for_client, vendor_departments = (
            permissions_service.get_descriptor_visibility(role)
        )
        descriptor_visibilities.append(
            (role_project_ids, for_client, vendor_departments)
        )
    return descriptor_visibilities


def get_open_project_ids():
    """
    Get all open project ids for which current user is part of the team.
    """
    return [project["id"] for project in get_open_projects()]


def get_projects(name=None):
    """
    Get all projects for which current user is part of the team.
    """
    current_user = persons_service.get_current_user()
    query = (
        Project.query.join(
            ProjectStatus, Project.project_status_id == ProjectStatus.id
        )
        .join(ProjectPersonLink, Project.id == ProjectPersonLink.project_id)
        .filter(ProjectPersonLink.person_id == current_user["id"])
    )

    if name is not None:
        query = query.filter(func.lower(Project.name) == name.lower())

    return fields.serialize_value(query.all())


def get_project_by_name(project_name):
    """
    Get the project of given name among those the current user belongs to,
    case insensitive. Raises an exception if none matches.
    """
    projects = get_projects(name=project_name)
    if not projects:
        raise ProjectNotFoundException()
    return projects[0]


def get_notification(notification_id):
    """
    Return notification matching given ID as a dictionnary.
    """
    notifications = get_last_notifications(notification_id)

    if len(notifications) == 0:
        raise NotificationNotFoundException

    return notifications[0]


def update_notification(notification_id, read):
    """
    Update read status of given notification.
    """
    current_user = persons_service.get_current_user()
    notification = Notification.get_by(
        id=notification_id, person_id=current_user["id"]
    )
    if notification is None:
        raise NotificationNotFoundException
    notification.update({"read": read})
    if read:
        events.emit(
            "notification:read",
            {
                "person_id": current_user["id"],
                "notification_id": notification_id,
            },
        )
    else:
        events.emit(
            "notification:unread",
            {
                "person_id": current_user["id"],
                "notification_id": notification_id,
            },
        )
    return notification.serialize()


def get_unread_notifications_count(notification_id=None):
    """
    Return the number of unread notifications.
    """
    current_user = persons_service.get_current_user()
    return Notification.query.filter_by(
        person_id=current_user["id"], read=False
    ).count()


def get_last_notifications(
    notification_id=None,
    after=None,
    before=None,
    task_type_id=None,
    task_status_id=None,
    notification_type=None,
    read=None,
    watching=None,
):
    """
    Return last 100 user notifications.
    """
    # These reach the query as raw values, so the driver is the one that
    # rejects them: a malformed id raises a StatementError while binding,
    # a malformed date a DataError on execution. Both surfaced as a 500.
    for id_field, value in (
        ("notification_id", notification_id),
        ("task_type_id", task_type_id),
        ("task_status_id", task_status_id),
    ):
        if value is not None and not fields.is_valid_id(value):
            raise WrongParameterException(
                f"Invalid UUID format for {id_field}: {value}"
            )

    current_user = persons_service.get_current_user()
    Author = aliased(Person, name="author")
    is_current_user_artist = current_user["role"] == "user"
    result = []
    query = (
        Notification.query.filter_by(person_id=current_user["id"])
        .order_by(Notification.created_at.desc())
        .join(Author, Author.id == Notification.author_id)
        .outerjoin(Task, Task.id == Notification.task_id)
        .outerjoin(Project, Project.id == Task.project_id)
        .outerjoin(
            Subscription,
            and_(
                Subscription.task_id == Task.id,
                Subscription.person_id == current_user["id"],
            ),
        )
        .outerjoin(Comment, Comment.id == Notification.comment_id)
        .add_columns(
            Project.id,
            Project.name,
            Task.task_type_id,
            Comment.id,
            Comment.task_status_id,
            Comment.text,
            Comment.replies,
            Task.entity_id,
            Subscription.id,
            Author.role,
        )
    )

    query = _filter_notifications(
        query,
        notification_id,
        after,
        before,
        task_type_id,
        task_status_id,
        notification_type,
        read,
        watching,
    )

    try:
        # The query is lazy: a date the driver refuses raises here, not
        # while the filters are being stacked above.
        notifications = query.limit(100).all()
    except DataError:
        raise WrongParameterException("Wrong date format for after or before.")

    context = _load_notification_context(notifications)
    for row in notifications:
        result.append(
            _serialize_notification(row, is_current_user_artist, context)
        )

    return result


def _load_notification_context(notifications):
    """
    Load in a fixed number of queries what the notification rows point at:
    the comments with their previews and mentions, the playlists with their
    project, the full names of the entities. Reading them per row cost up
    to five queries per notification on a listing the clients poll.
    """
    comment_ids = set()
    playlist_ids = set()
    entity_ids = set()
    for row in notifications:
        notification = row[0]
        comment_id = row[4]
        task_entity_id = row[8]
        if comment_id is not None:
            comment_ids.add(comment_id)
        if notification.playlist_id is not None:
            playlist_ids.add(notification.playlist_id)
        elif task_entity_id is not None:
            entity_ids.add(task_entity_id)

    comments = {}
    if comment_ids:
        comments = {
            str(comment.id): comment
            for comment in Comment.query.options(
                selectinload(Comment.previews),
                selectinload(Comment.mentions),
                selectinload(Comment.department_mentions),
            ).filter(Comment.id.in_(list(comment_ids)))
        }

    playlists = {}
    if playlist_ids:
        for playlist, project_name in (
            Playlist.query.join(Project, Project.id == Playlist.project_id)
            .filter(Playlist.id.in_(list(playlist_ids)))
            .with_entities(Playlist, Project.name)
            .all()
        ):
            playlists[str(playlist.id)] = (playlist, project_name)

    return {
        "comments": comments,
        "playlists": playlists,
        "entity_names": entities_service.get_full_entity_names(
            [str(entity_id) for entity_id in entity_ids]
        ),
    }


def _filter_notifications(
    query,
    notification_id,
    after,
    before,
    task_type_id,
    task_status_id,
    notification_type,
    read,
    watching,
):
    """
    Narrow the notification listing to the criteria the caller gave.
    """
    if notification_id is not None:
        query = query.filter(Notification.id == notification_id)

    if after is not None:
        query = query.filter(
            Notification.created_at
            > func.cast(after, Notification.created_at.type)
        )

    if before is not None:
        query = query.filter(
            Notification.created_at
            < func.cast(before, Notification.created_at.type)
        )

    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)

    if task_status_id is not None:
        query = query.filter(Task.task_status_id == task_status_id)

    if notification_type is not None:
        query = query.filter(Notification.type == notification_type)

    if read is not None:
        query = query.filter(Notification.read == read)

    if watching is not None:
        if watching:
            query = query.filter(Subscription.id != None)
        else:
            query = query.filter(Subscription.id == None)
    return query


def _serialize_notification(row, is_current_user_artist, context):
    """
    Build the notification dict of one row of the listing query, with the
    entity or playlist it points at and the text of the comment or reply
    that raised it, read from the context _load_notification_context
    built. A client comment is blanked for an artist.
    """
    (
        notification,
        project_id,
        project_name,
        task_type_id,
        comment_id,
        task_status_id,
        comment_text,
        comment_replies,
        task_entity_id,
        subscription_id,
        role,
    ) = row

    full_entity_name, episode_id, entity_preview_file_id = "", None, None
    playlist_id = notification.playlist_id
    playlist_name = ""
    playlist_for_entity = ""
    playlist_is_for_all = False
    if notification.playlist_id is None:
        full_entity_name, episode_id, entity_preview_file_id = context[
            "entity_names"
        ].get(str(task_entity_id), ("", None, None))
    else:
        playlist, project_name = context["playlists"][
            str(notification.playlist_id)
        ]
        episode_id = playlist.episode_id
        project_id = playlist.project_id
        playlist_name = playlist.name
        playlist_for_entity = playlist.for_entity
        playlist_is_for_all = playlist.is_for_all

    preview_file_id = None
    mentions = []
    department_mentions = []
    reply_mentions = []
    reply_department_mentions = []
    comment = context["comments"].get(str(comment_id))
    if comment is not None:
        if len(comment.previews) > 0:
            preview_file_id = comment.previews[0].id
        mentions = comment.mentions or []
        department_mentions = comment.department_mentions or []

    reply_text = ""
    if notification.type in ["reply", "reply-mention"]:
        reply = next(
            (
                reply
                for reply in comment_replies
                if reply["id"] == str(notification.reply_id)
            ),
            None,
        )
        if reply is not None:
            reply_text = reply["text"]
            reply_mentions = reply.get("mentions", []) or []
            reply_department_mentions = (
                reply.get("department_mentions", []) or []
            )
        else:
            reply_mentions = []
            reply_department_mentions = []

    if role == "client" and is_current_user_artist:
        comment_text = ""
        reply_text = ""

    return fields.serialize_dict(
        {
            "id": notification.id,
            "type": "Notification",
            "notification_type": notification.type,
            "author_id": notification.author_id,
            "comment_id": notification.comment_id,
            "task_id": notification.task_id,
            "task_type_id": task_type_id,
            "task_status_id": task_status_id,
            "mentions": mentions,
            "department_mentions": department_mentions,
            "reply_mentions": reply_mentions,
            "reply_department_mentions": reply_department_mentions,
            "preview_file_id": preview_file_id,
            "project_id": project_id,
            "project_name": project_name,
            "comment_text": comment_text,
            "reply_text": reply_text,
            "created_at": notification.created_at,
            "read": notification.read,
            "change": notification.change,
            "full_entity_name": full_entity_name,
            "episode_id": episode_id,
            "entity_preview_file_id": entity_preview_file_id,
            "subscription_id": subscription_id,
            "playlist_id": playlist_id,
            "playlist_name": playlist_name,
            "playlist_for_entity": playlist_for_entity,
            "playlist_is_for_all": playlist_is_for_all,
        }
    )


def mark_notifications_as_read():
    """
    Mark all recent notifications for current_user as read. It is useful
    to mark a list of notifications as read after an user retrieved them.
    """
    from sqlalchemy import update
    from zou.app import db

    current_user = persons_service.get_current_user()
    update_stmt = (
        update(Notification)
        .where(Notification.person_id == current_user["id"])
        .where(Notification.read == False)
        .values(read=True)
    )

    db.session.execute(update_stmt)
    db.session.commit()
    events.emit("notification:all-read", {"person_id": current_user["id"]})
    return True


def has_task_subscription(task_id):
    """
    Returns true if a subscription entry exists for current user and given
    task.
    """
    current_user = persons_service.get_current_user()
    return subscriptions_service.has_task_subscription(
        current_user["id"], task_id
    )


def subscribe_to_task(task_id):
    """
    Create a subscription entry for current user and given task
    """
    current_user = persons_service.get_current_user()
    return subscriptions_service.subscribe_to_task(current_user["id"], task_id)


def unsubscribe_from_task(task_id):
    """
    Remove subscription entry for current user and given task
    """
    current_user = persons_service.get_current_user()
    return subscriptions_service.unsubscribe_from_task(
        current_user["id"], task_id
    )


def has_sequence_subscription(sequence_id, task_type_id):
    """
    Returns true if a subscription entry exists for current user and given
    sequence.
    """
    current_user = persons_service.get_current_user()
    return subscriptions_service.has_sequence_subscription(
        current_user["id"], sequence_id, task_type_id
    )


def subscribe_to_sequence(sequence_id, task_type_id):
    """
    Create a subscription entry for current user and given sequence
    """
    current_user = persons_service.get_current_user()
    return subscriptions_service.subscribe_to_sequence(
        current_user["id"], sequence_id, task_type_id
    )


def unsubscribe_from_sequence(sequence_id, task_type_id):
    """
    Remove subscription entry for current user and given sequence
    """
    current_user = persons_service.get_current_user()
    return subscriptions_service.unsubscribe_from_sequence(
        current_user["id"], sequence_id, task_type_id
    )


def get_sequence_subscriptions(project_id, task_type_id):
    """
    Return list of sequence ids for which the current user has subscriptions
    for given project and task type.
    """
    current_user = persons_service.get_current_user()
    return subscriptions_service.get_all_sequence_subscriptions(
        current_user["id"], project_id, task_type_id
    )


def get_project_roles():
    """
    Return a dict mapping project ids to the explicit role the current user
    holds on them. Projects where the user inherits their global role are
    absent from the dict.
    """
    current_user = persons_service.get_current_user()
    return {
        str(link.project_id): getattr(link.role, "code", link.role)
        for link in ProjectPersonLink.query.filter(
            ProjectPersonLink.person_id == current_user["id"],
            ProjectPersonLink.role.isnot(None),
        )
    }


def get_team_project_roles():
    """
    Return a dict mapping the id of every project of the current user's
    teams to the role they hold there: the role set on their team link,
    or their global role where the link sets none. A listing resolves no
    project, so a role check would read the global role for every row
    listed: the role held on the project of each row is read instead. An
    admin keeps the global role, as in the project access check, and gets
    an empty dict.
    """
    if permissions.has_admin_permissions():
        return {}
    current_user = persons_service.get_current_user()
    project_roles = {}
    for link in ProjectPersonLink.query.filter(
        ProjectPersonLink.person_id == current_user["id"]
    ):
        role = getattr(link.role, "code", link.role)
        if role in (None, "admin"):
            # An admin slot is invalid data, which the role checks read as
            # the global role too.
            role = current_user["role"]
        project_roles[str(link.project_id)] = role
    return project_roles


def get_context():
    """
    Build everything the client needs on login in one payload: projects,
    task types, statuses, departments, persons, custom actions and the
    user's own filters. Scoped to the current user throughout.
    """
    context = {
        "asset_types": entity_types_service.get_asset_types(),
        "custom_actions": custom_actions_service.get_custom_actions(),
        "status_automations": status_automations_service.get_status_automations(),
        "departments": departments_service.get_departments(),
        "studios": task_types_service.get_studios(),
        "notification_count": get_unread_notifications_count(),
        "persons": persons_service.get_persons(
            minimal=not permissions.has_manager_permissions()
        ),
        "project_status": projects_service.get_project_statuses(),
        "project_roles": get_project_roles(),
        "projects": get_open_projects(),
        "task_types": task_types_service.get_task_types(),
        "task_status": task_types_service.get_task_statuses(),
        "search_filters": search_filters_service.get_filters(),
        "search_filter_groups": search_filters_service.get_filter_groups(),
        "preview_background_files": files_service.get_preview_background_files(),
        "plugins": plugins_service.get_plugins(),
    }

    if permissions.has_admin_permissions():
        context["user_limit"] = organisation_service.get_user_limit()
    return context
