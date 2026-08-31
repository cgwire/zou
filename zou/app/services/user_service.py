from sqlalchemy.orm import aliased
from sqlalchemy import func, or_, and_
from sqlalchemy.exc import DataError

from zou.app.models.comment import Comment
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.models.project import Project, ProjectPersonLink
from zou.app.models.project_status import ProjectStatus
from zou.app.models.subscription import Subscription
from zou.app.models.search_filter import SearchFilter
from zou.app.models.search_filter_group import SearchFilterGroup
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType

from zou.app.services import (
    assets_service,
    custom_actions_service,
    notifications_service,
    names_service,
    permissions_service,
    persons_service,
    playlists_service,
    plugins_service,
    projects_service,
    shots_service,
    status_automations_service,
    tasks_service,
    files_service,
)
from zou.app.services.exception import (
    SearchFilterNotFoundException,
    SearchFilterGroupNotFoundException,
    NotificationNotFoundException,
    WrongParameterException,
)
from zou.app.utils import cache, fields, permissions, events


def _clear_user_scoped_cache(getter, user_id):
    """
    Drop the memoized result of given per-user getter, for one user or for
    all of them when no user is given.
    """
    if user_id is None:
        cache.cache.delete_memoized(getter)
    else:
        cache.cache.delete_memoized(getter, user_id)


def clear_filter_cache(user_id=None):
    """
    Drop the memoized filter list of given user, or of every user.
    """
    _clear_user_scoped_cache(get_user_filters, user_id)


def clear_filter_group_cache(user_id=None):
    """
    Drop the memoized filter group list of given user, or of every user.
    """
    _clear_user_scoped_cache(get_user_filter_groups, user_id)


def clear_project_cache():
    """
    Drop the memoized open project list.
    """
    cache.cache.delete_memoized(get_open_projects)


def _clear_cache_after_sharing_change(clear_cache, is_shared, user_id):
    """
    A shared filter is visible to the whole team, so its cache must be
    dropped for everyone; a private one only for its owner.
    """
    if is_shared:
        clear_cache()
    else:
        clear_cache(user_id)


def _deny_sharing_without_manager_access(data, instance):
    """
    Silently turn off a sharing request the caller is not allowed to make:
    sharing is a per project manager privilege, and a filter without a
    project cannot be shared at all. Mutates data in place.
    """
    if (
        data.get("is_shared", None) is not None
        and instance.is_shared != data["is_shared"]
        and (
            data.get("project_id", None) is None
            or (
                data["project_id"] is not None
                and not permissions_service.has_manager_project_access(
                    data["project_id"]
                )
            )
        )
    ):
        data["is_shared"] = False


def _get_own_or_as_admin(model, instance_id, current_user):
    """
    Return the row of given model belonging to the current user, falling
    back to the row whoever owns it when they are an admin. Returns None
    when nothing matches, the caller raises.
    """
    instance = model.get_by(id=instance_id, person_id=current_user["id"])
    if instance is None and current_user["role"] == "admin":
        instance = model.get_by(id=instance_id)
    return instance


def build_assignee_filter():
    """
    Query filter for task to retrieve only tasks assigned to current user.
    """
    current_user = persons_service.get_current_user_raw()
    return Task.assignees.contains(current_user)


def build_team_filter():
    """
    Query filter for task to retrieve only models from project for which the
    user is part of the team.
    """
    current_user = persons_service.get_current_user_raw()
    return Project.team.contains(current_user)


def build_team_exists_filter(project_id):
    """
    Query filter to keep only rows whose project the user is part of the
    team of. Expressed as an EXISTS so it never multiplies result rows.
    """
    current_user = persons_service.get_current_user()
    return (
        ProjectPersonLink.query.filter(
            ProjectPersonLink.project_id == project_id
        )
        .filter(ProjectPersonLink.person_id == current_user["id"])
        .exists()
    )


def build_open_project_filter():
    """
    Query filter for project to retrieve only open projects.
    """
    open_status = projects_service.get_open_status()
    return Project.project_status_id == open_status["id"]


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
        .filter(build_open_project_filter())
        .distinct()
        .all()
    )
    return projects


def get_todos():
    """
    Get all unfinished tasks assigned to current user.
    """
    current_user = persons_service.get_current_user()
    projects = related_projects()
    return tasks_service.get_person_tasks(current_user["id"], projects)


def get_done_tasks():
    """
    Get all finished tasks assigned to current user for open projects.
    """
    current_user = persons_service.get_current_user()
    projects = related_projects()
    return tasks_service.get_person_done_tasks(current_user["id"], projects)


def _get_tasks_to_check_scope():
    """
    Return (allowed, project_ids, department_ids) used to scope the
    tasks-to-check queries depending on the current user role.
    """
    if permissions.has_admin_permissions():
        return True, None, None
    if permissions.has_manager_permissions():
        return True, [project["id"] for project in related_projects()], None
    if permissions.has_supervisor_permissions():
        current_user = persons_service.get_current_user(relations=True)
        return (
            True,
            [project["id"] for project in related_projects()],
            current_user["departments"],
        )
    return False, None, None


def get_tasks_to_check(
    project_id=None,
    task_type_id=None,
    task_status_id=None,
    person_id=None,
    episode_id=None,
    due_date_since=None,
    due_date_until=None,
    order_by=None,
    page=None,
    limit=100,
):
    """
    Get all tasks waiting for feedback in the user department. When a page
    number is given, return a pagination envelope instead of a bare list.
    """
    allowed, project_ids, departments_ids = _get_tasks_to_check_scope()
    if not allowed:
        # an empty project scope yields the same empty list or envelope
        # shape as the allowed path, clamping included
        project_ids, departments_ids = [], None

    return tasks_service.get_person_tasks_to_check(
        project_ids,
        departments_ids,
        project_id=project_id,
        task_type_id=task_type_id,
        task_status_id=task_status_id,
        person_id=person_id,
        episode_id=episode_id,
        due_date_since=due_date_since,
        due_date_until=due_date_until,
        order_by=order_by,
        page=page,
        limit=limit,
    )


def get_tasks_to_check_filter_values():
    """
    Return the distinct filter values available for the tasks waiting for
    feedback in the user department.
    """
    allowed, project_ids, departments_ids = _get_tasks_to_check_scope()
    if not allowed:
        return {
            "project_ids": [],
            "task_type_ids": [],
            "task_status_ids": [],
            "episode_ids": [],
            "person_ids": [],
        }
    return tasks_service.get_person_tasks_to_check_filter_values(
        project_ids, departments_ids
    )


def get_tasks_for_entity(entity_id):
    """
    Get all tasks assigned to current user and related to given entity.
    """
    query = (
        Task.query.join(Project)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .filter(Task.entity_id == entity_id)
        .filter(build_assignee_filter())
        .filter(build_open_project_filter())
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
        .filter(build_assignee_filter())
        .filter(build_open_project_filter())
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
        .filter(build_assignee_filter())
        .filter(build_open_project_filter())
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
        .filter(build_assignee_filter())
        .filter(build_open_project_filter())
        .filter(assets_service.build_asset_type_filter())
    )

    return EntityType.serialize_list(query.all(), obj_type="AssetType")


def get_sequences_for_project(project_id):
    """
    Return all sequences for given project and for which current user has
    a task assigned to a shot.
    """
    shot_type = shots_service.get_shot_type()
    sequence_type = shots_service.get_sequence_type()

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
        .filter(build_assignee_filter())
        .filter(build_open_project_filter())
    )

    return Entity.serialize_list(query.all(), obj_type="Sequence")


def get_project_episodes(project_id):
    """
    Return all episodes for given project and for which current user has
    a task assigned to a shot.
    """
    shot_type = shots_service.get_shot_type()
    sequence_type = shots_service.get_sequence_type()
    episode_type = shots_service.get_episode_type()

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
        .filter(build_assignee_filter())
        .filter(build_open_project_filter())
    )

    return Entity.serialize_list(query.all(), obj_type="Episode")


def get_shots_for_sequence(sequence_id):
    """
    Get all shots for given sequence and for which the user has a task assigned.
    """
    shot_type = shots_service.get_shot_type()
    query = (
        Entity.query.join(Task)
        .join(Project)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .join(EntityType)
        .filter(Entity.entity_type_id == shot_type["id"])
        .filter(Entity.parent_id == sequence_id)
        .filter(build_assignee_filter())
        .filter(build_open_project_filter())
    )

    return Entity.serialize_list(query.all(), obj_type="Shot")


def get_scenes_for_sequence(sequence_id):
    """
    Get all layout scenes for given sequence and for which the user has a task
    assigned.
    """
    scene_type = shots_service.get_scene_type()
    query = (
        Entity.query.join(Task)
        .join(Project)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .join(EntityType)
        .filter(Entity.entity_type_id == scene_type["id"])
        .filter(Entity.parent_id == sequence_id)
        .filter(build_assignee_filter())
        .filter(build_open_project_filter())
    )

    return Entity.serialize_list(query.all(), obj_type="Scene")


def get_open_projects(name=None):
    """
    Get all open projects for which current user is part of the team.
    """
    query = Project.query.join(
        ProjectStatus, Project.project_status_id == ProjectStatus.id
    ).filter(build_open_project_filter())

    if name is not None:
        query = query.filter(Project.name == name)

    if not permissions.has_admin_permissions():
        current_user = persons_service.get_current_user()
        query = query.join(
            ProjectPersonLink, Project.id == ProjectPersonLink.project_id
        )
        query = query.filter(ProjectPersonLink.person_id == current_user["id"])

    for_client = False
    vendor_departments = None
    if permissions.has_client_permissions():
        for_client = True
    elif permissions.has_vendor_permissions():
        vendor_departments = persons_service.get_current_user(relations=True)[
            "departments"
        ]

    return projects_service.get_projects_with_extra_data(
        query, for_client, vendor_departments
    )


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
        query = query.filter(Project.name == name)

    return fields.serialize_value(query.all())


def get_filters():
    """
    Retrieve search filters used by current user. It groups them by
    list type and project_id. If the filter is not related to a project,
    the project_id is all.
    """
    current_user = persons_service.get_current_user()
    return get_user_filters(current_user["id"])


@cache.memoize_function(120)
def get_user_filters(current_user_id):
    """
    Retrieve search filters used for given user. It groups them by
    list type and project_id. If the filter is not related to a project,
    the project_id is all.

    Memoized on current_user_id alone, so it must only ever be called with
    the id of the current user: the body reads get_current_user() and
    has_manager_permissions(), which answer for the caller, not for the id.

    has_manager_permissions() also reads the per project role when a project
    access check has resolved one earlier in the request. The only route
    reaching this resolves none, so it answers with the global role and the
    result stays stable per user. Adding a project scoped variant would
    break that: the first caller's answer would be served to the others for
    the whole TTL. Pass the scoping in as an argument if that day comes.
    """
    result = {}

    filters = (
        SearchFilter.query.outerjoin(Project)
        .outerjoin(ProjectStatus)
        .filter(
            or_(
                SearchFilter.person_id == current_user_id,
                SearchFilter.is_shared == True,
            )
        )
        .filter(
            or_(build_open_project_filter(), SearchFilter.project_id == None)
        )
        .all()
    )

    current_user = persons_service.get_current_user(relations=True)
    is_manager = permissions.has_manager_permissions()

    for search_filter in filters:
        department_id = search_filter.department_id
        is_in_departments = (
            department_id is not None
            and str(department_id) in current_user["departments"]
        )

        if department_id is None or is_manager or is_in_departments:
            if search_filter.list_type not in result:
                result[search_filter.list_type] = {}
            subresult = result[search_filter.list_type]

            if search_filter.project_id is None:
                project_id = "all"
            else:
                project_id = str(search_filter.project_id)

            if project_id not in subresult:
                subresult[project_id] = []

            subresult[project_id].append(search_filter.serialize())

    return result


def create_filter(
    list_type,
    name,
    query,
    project_id=None,
    entity_type=None,
    is_shared=False,
    search_filter_group_id=None,
    department_id=None,
):
    """
    Add a new search filter to the database.
    """
    current_user = persons_service.get_current_user()

    if project_id is None or (
        project_id is not None
        and not permissions_service.has_manager_project_access(project_id)
    ):
        is_shared = False

    if search_filter_group_id is not None:
        search_filter_group = SearchFilterGroup.get_by(
            id=search_filter_group_id
        )
        if search_filter_group is None:
            raise SearchFilterGroupNotFoundException
        if is_shared != search_filter_group.is_shared:
            raise WrongParameterException(
                "A search filter should have the same value for is_shared than its search filter group."
            )

    if department_id is not None:
        department = tasks_service.get_department(department_id)
        if department is None:
            raise WrongParameterException(
                f"No department found with id: {department_id}"
            )

    search_filter = SearchFilter.create(
        list_type=list_type,
        name=name,
        search_query=query,
        project_id=project_id,
        person_id=current_user["id"],
        entity_type=entity_type,
        is_shared=is_shared,
        search_filter_group_id=search_filter_group_id,
        department_id=department_id,
    )
    _clear_cache_after_sharing_change(
        clear_filter_cache, search_filter.is_shared, current_user["id"]
    )
    return search_filter.serialize()


def update_filter(search_filter_id, data):
    """
    Update given filter from database.
    """
    current_user = persons_service.get_current_user()
    search_filter = _get_own_or_as_admin(
        SearchFilter, search_filter_id, current_user
    )
    if search_filter is None:
        raise SearchFilterNotFoundException

    department_id = data.get("department_id", None)
    if department_id is not None:
        department = tasks_service.get_department(department_id)
        if department is None:
            raise WrongParameterException(
                f"No department found with id: {department_id}"
            )

    _deny_sharing_without_manager_access(data, search_filter)

    if (
        search_filter_group_id := data.get(
            "search_filter_group_id", search_filter.search_filter_group_id
        )
    ) is not None:
        search_filter_group = SearchFilterGroup.get_by(
            id=search_filter_group_id
        )
        if search_filter_group is None:
            raise SearchFilterGroupNotFoundException
        if (
            data.get("is_shared", search_filter.is_shared)
            != search_filter_group.is_shared
        ):
            raise WrongParameterException(
                "A search filter should have the same value for is_shared than its search filter group."
            )

    search_filter.update(data)
    _clear_cache_after_sharing_change(
        clear_filter_cache, search_filter.is_shared, current_user["id"]
    )
    return search_filter.serialize()


def remove_filter(search_filter_id):
    """
    Remove given filter from database.
    """
    current_user = persons_service.get_current_user()
    search_filter = _get_own_or_as_admin(
        SearchFilter, search_filter_id, current_user
    )
    if search_filter is None:
        raise SearchFilterNotFoundException
    search_filter.delete()
    _clear_cache_after_sharing_change(
        clear_filter_cache, search_filter.is_shared, current_user["id"]
    )
    return search_filter.serialize()


def get_filter_groups():
    """
    Retrieve search filter groups used by current user. It groups them by
    list type and project_id. If the filter group is not related to a project,
    the project_id is all.
    """
    current_user = persons_service.get_current_user()
    return get_user_filter_groups(current_user["id"])


@cache.memoize_function(10)
def get_user_filter_groups(current_user_id):
    """
    Retrieve search filter groups used for given user. It groups them by
    list type and project_id. If the filter group is not related to a project,
    the project_id is all.

    Same caveat as get_user_filters: memoized on current_user_id alone while
    the body answers for the caller, so it must only be called with the
    current user's id and from a route that resolves no project role.
    """
    result = {}

    filter_groups = (
        SearchFilterGroup.query.outerjoin(
            Project, Project.id == SearchFilterGroup.project_id
        )
        .outerjoin(
            ProjectStatus, ProjectStatus.id == Project.project_status_id
        )
        .filter(
            or_(
                SearchFilterGroup.person_id == current_user_id,
                SearchFilterGroup.is_shared == True,
            )
        )
        .filter(or_(build_open_project_filter(), Project.id == None))
        .order_by(SearchFilterGroup.created_at.desc())
        .all()
    )

    current_user = persons_service.get_current_user(relations=True)
    is_manager = permissions.has_manager_permissions()

    for search_filter_group in filter_groups:
        if search_filter_group.list_type not in result:
            result[search_filter_group.list_type] = {}

        department_id = search_filter_group.department_id
        is_in_departments = (
            department_id is not None
            and str(department_id) in current_user["departments"]
        )
        if department_id is None or is_manager or is_in_departments:
            subresult = result[search_filter_group.list_type]

            if search_filter_group.project_id is None:
                project_id = "all"
            else:
                project_id = str(search_filter_group.project_id)

            if project_id not in subresult:
                subresult[project_id] = []
            subresult[project_id].append(search_filter_group.serialize())

    return result


def create_filter_group(
    list_type,
    name,
    color,
    project_id=None,
    entity_type=None,
    is_shared=False,
    department_id=None,
):
    """
    Add a new search filter group to the database.
    """
    current_user = persons_service.get_current_user()
    if project_id is None or (
        project_id is not None
        and not permissions_service.has_manager_project_access(project_id)
    ):
        is_shared = False

    if department_id is not None:
        department = tasks_service.get_department(department_id)
        if department is None:
            raise WrongParameterException(
                f"No department found with id: {department_id}"
            )

    search_filter_group = SearchFilterGroup.create(
        list_type=list_type,
        name=name,
        color=color,
        project_id=project_id,
        person_id=current_user["id"],
        entity_type=entity_type,
        is_shared=is_shared,
        department_id=department_id,
    )
    _clear_cache_after_sharing_change(
        clear_filter_group_cache,
        search_filter_group.is_shared,
        current_user["id"],
    )

    return search_filter_group.serialize()


def get_filter_group(search_filter_group_id):
    """
    Get given filter group from the database.
    """
    current_user = persons_service.get_current_user()
    search_filter_group = _get_own_or_as_admin(
        SearchFilterGroup, search_filter_group_id, current_user
    )
    if search_filter_group is None:
        raise SearchFilterGroupNotFoundException
    return search_filter_group.serialize()


def update_filter_group(search_filter_group_id, data):
    """
    Update given filter group from database.
    """
    current_user = persons_service.get_current_user()
    search_filter_group = _get_own_or_as_admin(
        SearchFilterGroup, search_filter_group_id, current_user
    )

    if search_filter_group is None:
        raise SearchFilterGroupNotFoundException

    _deny_sharing_without_manager_access(data, search_filter_group)

    search_filter_group.update(data)

    if data.get("is_shared", None) is not None:
        # The group carries the authorized value by now, since
        # _deny_sharing_without_manager_access turned down what the caller
        # could not ask for. The filters have to follow it rather than the
        # body: update_filter refuses any change to a filter whose is_shared
        # differs from its group, so a group left out of step with them
        # makes them unmodifiable for good.
        if (
            SearchFilter.query.filter_by(
                search_filter_group_id=search_filter_group_id
            ).update({"is_shared": search_filter_group.is_shared})
            > 0
        ):
            SearchFilter.query.session.commit()
            clear_filter_cache()

    _clear_cache_after_sharing_change(
        clear_filter_group_cache,
        search_filter_group.is_shared,
        current_user["id"],
    )
    return search_filter_group.serialize()


def remove_filter_group(search_filter_group_id):
    """
    Remove given filter group from database.
    """
    current_user = persons_service.get_current_user()
    search_filter_group = _get_own_or_as_admin(
        SearchFilterGroup, search_filter_group_id, current_user
    )
    if search_filter_group is None:
        raise SearchFilterGroupNotFoundException
    if (
        SearchFilter.query.filter_by(
            search_filter_group_id=search_filter_group_id
        ).delete()
        > 0
    ):
        SearchFilter.query.session.commit()
        clear_filter_cache()
    search_filter_group.delete()
    _clear_cache_after_sharing_change(
        clear_filter_group_cache,
        search_filter_group.is_shared,
        current_user["id"],
    )
    return search_filter_group.serialize()


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

    try:
        # The query is lazy: a date the driver refuses raises here, not
        # while the filters are being stacked above.
        notifications = query.limit(100).all()
    except DataError:
        raise WrongParameterException("Wrong date format for after or before.")

    for (
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
    ) in notifications:
        full_entity_name, episode_id, entity_preview_file_id = "", None, None
        playlist_id = notification.playlist_id
        playlist_name = ""
        playlist_for_entity = ""
        playlist_is_for_all = False
        if notification.playlist_id is None:
            full_entity_name, episode_id, entity_preview_file_id = (
                names_service.get_full_entity_name(task_entity_id)
            )
        else:
            playlist = playlists_service.get_playlist(notification.playlist_id)
            episode_id = playlist.get("episode_id", None)
            project = projects_service.get_project(playlist["project_id"])
            project_id = project["id"]
            project_name = project["name"]
            playlist_name = playlist["name"]
            playlist_for_entity = playlist["for_entity"]
            playlist_is_for_all = playlist["is_for_all"]

        preview_file_id = None
        mentions = []
        department_mentions = []
        reply_mentions = []
        reply_department_mentions = []
        if comment_id is not None:
            comment = Comment.get(comment_id)
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

        result.append(
            fields.serialize_dict(
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
        )

    return result


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
    return notifications_service.has_task_subscription(
        current_user["id"], task_id
    )


def subscribe_to_task(task_id):
    """
    Create a subscription entry for current user and given task
    """
    current_user = persons_service.get_current_user()
    return notifications_service.subscribe_to_task(current_user["id"], task_id)


def unsubscribe_from_task(task_id):
    """
    Remove subscription entry for current user and given task
    """
    current_user = persons_service.get_current_user()
    return notifications_service.unsubscribe_from_task(
        current_user["id"], task_id
    )


def has_sequence_subscription(sequence_id, task_type_id):
    """
    Returns true if a subscription entry exists for current user and given
    sequence.
    """
    current_user = persons_service.get_current_user()
    return notifications_service.has_sequence_subscription(
        current_user["id"], sequence_id, task_type_id
    )


def subscribe_to_sequence(sequence_id, task_type_id):
    """
    Create a subscription entry for current user and given sequence
    """
    current_user = persons_service.get_current_user()
    return notifications_service.subscribe_to_sequence(
        current_user["id"], sequence_id, task_type_id
    )


def unsubscribe_from_sequence(sequence_id, task_type_id):
    """
    Remove subscription entry for current user and given sequence
    """
    current_user = persons_service.get_current_user()
    return notifications_service.unsubscribe_from_sequence(
        current_user["id"], sequence_id, task_type_id
    )


def get_sequence_subscriptions(project_id, task_type_id):
    """
    Return list of sequence ids for which the current user has subscriptions
    for given project and task type.
    """
    current_user = persons_service.get_current_user()
    return notifications_service.get_all_sequence_subscriptions(
        current_user["id"], project_id, task_type_id
    )


def get_timezone():
    """
    Return the timezone of the current user, the instance default when
    they set none.
    """
    try:
        timezone = persons_service.get_current_user()["timezone"]
    except Exception:
        timezone = persons_service.get_default_timezone()
    return timezone or persons_service.get_default_timezone()


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


def get_context():
    """
    Build everything the client needs on login in one payload: projects,
    task types, statuses, departments, persons, custom actions and the
    user's own filters. Scoped to the current user throughout.
    """
    context = {
        "asset_types": assets_service.get_asset_types(),
        "custom_actions": custom_actions_service.get_custom_actions(),
        "status_automations": status_automations_service.get_status_automations(),
        "departments": tasks_service.get_departments(),
        "studios": tasks_service.get_studios(),
        "notification_count": get_unread_notifications_count(),
        "persons": persons_service.get_persons(
            minimal=not permissions.has_manager_permissions()
        ),
        "project_status": projects_service.get_project_statuses(),
        "project_roles": get_project_roles(),
        "projects": get_open_projects(),
        "task_types": tasks_service.get_task_types(),
        "task_status": tasks_service.get_task_statuses(),
        "search_filters": get_filters(),
        "search_filter_groups": get_filter_groups(),
        "preview_background_files": files_service.get_preview_background_files(),
        "plugins": plugins_service.get_plugins(),
    }

    if permissions.has_admin_permissions():
        context["user_limit"] = persons_service.get_user_limit()
    return context
