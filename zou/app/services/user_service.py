from sqlalchemy.orm import aliased
from sqlalchemy import func, or_

from zou.app import config
from zou.app.models.comment import Comment
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.models.search_filter import SearchFilter
from zou.app.models.search_filter_group import SearchFilterGroup
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType

from zou.app.services import (
    assets_service,
    custom_actions_service,
    edits_service,
    entities_service,
    notifications_service,
    names_service,
    persons_service,
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
from zou.app.utils import cache, fields, permissions


def clear_filter_cache(user_id=None):
    if user_id is None:
        cache.cache.delete_memoized(get_user_filters)
    else:
        cache.cache.delete_memoized(get_user_filters, user_id)


def clear_filter_group_cache(user_id=None):
    if user_id is None:
        cache.cache.delete_memoized(get_user_filter_groups)
    else:
        cache.cache.delete_memoized(get_user_filter_groups, user_id)


def clear_project_cache():
    cache.cache.delete_memoized(get_open_projects)


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


def build_open_project_filter():
    """
    Query filter for project to retrieve only open projects.
    """
    return ProjectStatus.name.in_(("Active", "open", "Open"))


def build_related_projects_filter():
    """
    Query filter for project to retrieve open projects of which the user
    is part of the team.
    """
    projects = (
        Project.query.join(ProjectStatus)
        .filter(build_team_filter())
        .filter(build_open_project_filter())
        .all()
    )
    project_ids = [project.id for project in projects]
    if len(project_ids) > 0:
        return Project.id.in_(project_ids)
    else:
        return Project.id.in_(["00000000-0000-0000-0000-000000000000"])


def related_projects():
    """
    Return all projects related to current user: open projects of which the user
    is part of the team.
    """
    projects = (
        Project.query.join(Task)
        .join(ProjectStatus)
        .filter(build_team_filter())
        .filter(build_open_project_filter())
        .all()
    )
    return Project.serialize_list(projects)


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


def get_tasks_to_check():
    """
    Get all tasks waiting for feedback in the user department.
    """
    departments_ids = None
    if permissions.has_admin_permissions():
        project_ids = None
    elif permissions.has_manager_permissions():
        project_ids = [project["id"] for project in related_projects()]
    elif permissions.has_supervisor_permissions():
        current_user = persons_service.get_current_user(relations=True)
        departments_ids = current_user["departments"]
        project_ids = [project["id"] for project in related_projects()]
    else:
        return []

    return tasks_service.get_person_tasks_to_check(
        project_ids, departments_ids
    )


def get_tasks_for_entity(entity_id):
    """
    Get all tasks assigned to current user and related to given entity.
    """
    query = (
        Task.query.join(Project)
        .join(ProjectStatus)
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
        .join(ProjectStatus)
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
        .join(ProjectStatus)
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
        .join(ProjectStatus)
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
        .join(ProjectStatus)
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
        .join(ProjectStatus)
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
        .join(ProjectStatus)
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
        .join(ProjectStatus)
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
    query = Project.query.join(ProjectStatus).filter(
        build_open_project_filter()
    )

    if name is not None:
        query = query.filter(Project.name == name)

    if not permissions.has_admin_permissions():
        query = query.filter(build_team_filter())

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
    Get all projects for which current user has a task assigned.
    """
    query = Project.query.join(ProjectStatus).filter(build_team_filter())

    if name is not None:
        query = query.filter(Project.name == name)

    return fields.serialize_value(query.all())


def check_working_on_entity(entity_id):
    """
    Return True if user has task assigned which is related to given entity.
    """
    current_user = persons_service.get_current_user_raw()
    query = Task.query.filter(Task.assignees.contains(current_user)).filter(
        Task.entity_id == entity_id
    )

    if query.first() is None:
        raise permissions.PermissionDenied

    return True


def check_working_on_task(task_id):
    """
    Return True if user has task assigned.
    """
    current_user = persons_service.get_current_user_raw()
    query = Task.query.filter(Task.assignees.contains(current_user)).filter(
        Task.id == task_id
    )

    if query.first() is None:
        raise permissions.PermissionDenied

    return True


def check_person_access(person_id):
    """
    Return True if user is an admin or is matching given person id.
    """
    current_user = persons_service.get_current_user()
    if permissions.has_admin_permissions() or current_user["id"] == person_id:
        return True
    else:
        raise permissions.PermissionDenied


def check_belong_to_project(project_id):
    """
    Return true if current user is assigned to a task of the given project or
    if current_user is part of the project team.
    """
    if project_id is None:
        return False

    project = projects_service.get_project_with_relations(str(project_id))
    current_user = persons_service.get_current_user()
    return current_user["id"] in project["team"]


def has_project_access(project_id):
    """
    Return true if current user is a manager or has a task assigned for this
    project.
    """
    return permissions.has_admin_permissions() or check_belong_to_project(
        project_id
    )


def check_project_access(project_id):
    """
    Return true if current user is a manager or has a task assigned for this
    project. Raise a PermissionDenied exception if not.
    """
    is_allowed = has_project_access(project_id)
    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def block_access_to_vendor():
    """
    Raise PermissionDenied if current user has a vendor role.
    """
    if permissions.has_vendor_permissions():
        raise permissions.PermissionDenied
    return True


def check_entity_access(entity_id):
    """
    Return true if current user is not a vendor or has a task assigned for this
    project.
    """
    is_allowed = not permissions.has_vendor_permissions()
    if not is_allowed:
        nb_tasks = (
            Task.query.filter(Task.entity_id == entity_id)
            .filter(build_assignee_filter())
            .count()
        )
        if nb_tasks == 0:
            raise permissions.PermissionDenied
        is_allowed = True
    return is_allowed


def check_task_status_access(task_status_id):
    """
    Return true if current user can use this task status.
    """
    is_artist = permissions.has_artist_permissions()
    is_client = permissions.has_client_permissions()
    if is_artist or is_client:
        task_status = tasks_service.get_task_status(task_status_id)
        if is_artist and not task_status["is_artist_allowed"]:
            raise permissions.PermissionDenied
        if is_client and not task_status["is_client_allowed"]:
            raise permissions.PermissionDenied
    return True


def check_comment_access(comment_id):
    """
    Return true if current user can have access to a comment.
    """
    if permissions.has_admin_permissions():
        return True
    else:
        comment = tasks_service.get_comment(comment_id)
        person_id = comment["person_id"]
        task_id = comment["object_id"]
        task = tasks_service.get_task(task_id)
        if task is None:
            tasks_service.clear_task_cache(task_id)
            task = tasks_service.get_task(task_id)
        check_project_access(task["project_id"])
        check_entity_access(task["entity_id"])

        if (
            permissions.has_supervisor_permissions()
            or permissions.has_manager_permissions()
        ):
            return True
        elif permissions.has_client_permissions():
            current_user = persons_service.get_current_user()
            project = projects_service.get_project(task["project_id"])
            if project.get("is_clients_isolated", False):
                if not comment["person_id"] == current_user["id"]:
                    raise permissions.PermissionDenied
            if persons_service.get_person(person_id)["role"] == "client":
                return True
            else:
                raise permissions.PermissionDenied
        elif persons_service.get_person(person_id)["role"] == "client":
            raise permissions.PermissionDenied

        return True


def has_manager_project_access(project_id):
    """
    Return true if current user is a manager and has a task assigned for this
    project.
    """
    return permissions.has_admin_permissions() or (
        permissions.has_manager_permissions()
        and check_belong_to_project(project_id)
    )


def check_manager_project_access(project_id):
    """
    Return true if current user is a manager and has a task assigned for this
    project. Raise a PermissionDenied exception if not.
    """
    is_allowed = has_manager_project_access(project_id)
    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_time_spent_access(task_id, person_id):
    """
    Return true if current user is an admin or is a manager or is assigned to
    the task.
    """
    task = tasks_service.get_task(task_id, relations=True)
    is_allowed = person_id in task["assignees"] and (
        persons_service.get_current_user()["id"] == person_id
        or (
            permissions.has_admin_permissions()
            or (
                permissions.has_manager_permissions()
                and check_belong_to_project(task["project_id"])
            )
        )
    )

    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_supervisor_project_access(project_id):
    """
    Return true if current user is a manager or a supervisor and has a task
    assigned for this project.
    """
    is_allowed = permissions.has_admin_permissions() or (
        (
            permissions.has_manager_permissions()
            or permissions.has_supervisor_permissions()
        )
        and check_belong_to_project(project_id)
    )
    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_supervisor_task_access(task, new_data={}):
    """
    Return true if current user is a manager and has a task assigned related
    to the project of this task or is a supervisor and can modify data accorded
    to his departments
    """
    is_allowed = False
    if permissions.has_admin_permissions() or (
        permissions.has_manager_permissions()
        and check_belong_to_project(task["project_id"])
    ):
        is_allowed = True
    elif permissions.has_supervisor_permissions() and check_belong_to_project(
        task["project_id"]
    ):
        # checks that the supervisor only modifies columns
        # for which he is authorized
        allowed_columns = set(
            ["priority", "start_date", "due_date", "estimation"]
        )
        if len(set(new_data.keys()) - allowed_columns) == 0:
            user_departments = persons_service.get_current_user(
                relations=True
            )["departments"]
            if (
                user_departments == []
                or tasks_service.get_task_type(task["task_type_id"])[
                    "department_id"
                ]
                in user_departments
            ):
                is_allowed = True

    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_supervisor_schedule_item_access(schedule_item, new_data={}):
    """
    Return true if current user is a manager and has a task assigned related
    to the project of this task or is a supervisor and can modify data accorded
    to his departments
    """
    is_allowed = False
    if permissions.has_admin_permissions() or (
        permissions.has_manager_permissions()
        and check_belong_to_project(schedule_item["project_id"])
    ):
        is_allowed = True
    elif permissions.has_supervisor_permissions() and check_belong_to_project(
        schedule_item["project_id"]
    ):
        user_departments = persons_service.get_current_user(relations=True)[
            "departments"
        ]
        if (
            user_departments == []
            or tasks_service.get_task_type(schedule_item["task_type_id"])[
                "department_id"
            ]
            in user_departments
        ):
            is_allowed = True

    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_metadata_department_access(entity, new_data={}):
    """
    Return true if current user is a manager and has a task assigned for this
    project or is a supervisor and is allowed to modify data accorded to
    his departments
    """
    is_allowed = False
    if permissions.has_admin_permissions() or (
        (
            permissions.has_manager_permissions()
            or entity["created_by"] == persons_service.get_current_user()["id"]
        )
        and check_belong_to_project(entity["project_id"])
    ):
        is_allowed = True
    elif permissions.has_supervisor_permissions() and check_belong_to_project(
        entity["project_id"]
    ):
        # checks that the supervisor only modifies columns
        # for which he is authorized
        allowed_columns = set(["data"])
        if len(set(new_data.keys()) - allowed_columns) == 0:
            user_departments = persons_service.get_current_user(
                relations=True
            )["departments"]
            if user_departments == []:
                is_allowed = True
            else:
                entity_type = None
                if shots_service.is_shot(entity):
                    entity_type = "Shot"
                elif assets_service.is_asset(
                    entities_service.get_entity_raw(entity["id"])
                ):
                    entity_type = "Asset"
                elif edits_service.is_edit(entity):
                    entity_type = "Edit"
                if entity_type:
                    descriptors = [
                        descriptor
                        for descriptor in projects_service.get_metadata_descriptors(
                            entity["project_id"]
                        )
                        if descriptor["entity_type"] == entity_type
                    ]
                    found_and_in_departments = False
                    for descriptor_name in new_data["data"].keys():
                        found_and_in_departments = False
                        for descriptor in descriptors:
                            if descriptor["field_name"] == descriptor_name:
                                found_and_in_departments = (
                                    len(
                                        set(descriptor["departments"])
                                        & set(user_departments)
                                    )
                                    > 0
                                )
                                break
                        if not found_and_in_departments:
                            break
                    if found_and_in_departments:
                        is_allowed = True

    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_task_department_access(task_id, person_id):
    """
    Return true if current user is an admin or is a manager and is in team
    or is a supervisor in the department of the task or is an artist assigning
    himself in the department of the task.
    """
    user = persons_service.get_current_user(relations=True)
    task = tasks_service.get_task(task_id)
    task_type = tasks_service.get_task_type(task["task_type_id"])
    is_allowed = permissions.has_admin_permissions() or (
        check_belong_to_project(task["project_id"])
        and (
            permissions.has_manager_permissions()
            or (
                permissions.has_supervisor_permissions()
                and (
                    user["departments"] == []
                    or (
                        task_type["department_id"] in user["departments"]
                        and len(
                            set(
                                persons_service.get_person(person_id)[
                                    "departments"
                                ]
                            )
                            & set(user["departments"])
                        )
                        > 0
                    )
                )
            )
            or (
                task_type["department_id"] in user["departments"]
                and person_id == user["id"]
            )
        )
    )
    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_person_is_not_bot(person_id):
    """
    Return true if person is not a bot else raise PermissionDenied
    """
    if persons_service.get_person(person_id)["is_bot"]:
        raise permissions.PermissionDenied
    else:
        return True


def check_task_department_access_for_unassign(task_id, person_id=None):
    """
    Return true if current user is an admin or is a manager and is in team
    or is a supervisor in the department of the task or is an artist assigning
    himself in the department of the task.
    """
    user = persons_service.get_current_user(relations=True)
    task = tasks_service.get_task(task_id)
    task_type = tasks_service.get_task_type(task["task_type_id"])
    is_allowed = permissions.has_admin_permissions() or (
        check_belong_to_project(task["project_id"])
        and (
            permissions.has_manager_permissions()
            or (
                permissions.has_supervisor_permissions()
                and (
                    user["departments"] == []
                    or task_type["department_id"] in user["departments"]
                )
            )
            or (
                user["id"] in task.get("assignees", [])
                and person_id == user["id"]
            )
        )
    )
    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_all_departments_access(project_id, departments=[]):
    """
    Return true if current user is admin or is manager and is in team or is
    supervisor and is in team and have access to all departments.
    """
    if not isinstance(departments, list):
        departments = [departments]
    is_allowed = False
    if permissions.has_admin_permissions() or (
        permissions.has_manager_permissions()
        and check_belong_to_project(project_id)
    ):
        is_allowed = True
    elif permissions.has_supervisor_permissions() and check_belong_to_project(
        project_id
    ):
        user_departments = persons_service.get_current_user(relations=True)[
            "departments"
        ]
        is_allowed = departments and (
            user_departments == []
            or all(
                department in departments for department in user_departments
            )
        )
    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_playlist_access(playlist, supervisor_access=False):
    check_project_access(playlist["project_id"])
    is_manager = permissions.has_manager_permissions()
    is_client = permissions.has_client_permissions()
    has_supervisor_access = (
        supervisor_access and permissions.has_supervisor_permissions()
    )
    has_client_access = is_client and playlist["for_client"]
    is_allowed = is_manager or has_client_access or has_supervisor_access
    if not is_allowed:
        raise permissions.PermissionDenied
    return True


def check_day_off_access(day_off):
    """
    Return true if current user is admin or day_off is for itself
    """
    user = persons_service.get_current_user()
    is_admin = permissions.has_admin_permissions()
    is_same_person = user["id"] == day_off["person_id"]
    if not (is_admin or is_same_person):
        raise permissions.PermissionDenied
    return True


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

    for search_filter in filters:
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
):
    """
    Add a new search filter to the database.
    """
    current_user = persons_service.get_current_user()

    if project_id is None or (
        project_id is not None and not has_manager_project_access(project_id)
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

    search_filter = SearchFilter.create(
        list_type=list_type,
        name=name,
        search_query=query,
        project_id=project_id,
        person_id=current_user["id"],
        entity_type=entity_type,
        is_shared=is_shared,
        search_filter_group_id=search_filter_group_id,
    )
    search_filter.serialize()
    if search_filter.is_shared:
        clear_filter_cache()
    else:
        clear_filter_cache(current_user["id"])
    return search_filter.serialize()


def update_filter(search_filter_id, data):
    """
    Update given filter from database.
    """
    current_user = persons_service.get_current_user()
    search_filter = SearchFilter.get_by(
        id=search_filter_id, person_id=current_user["id"]
    )
    if search_filter is None:
        raise SearchFilterNotFoundException

    if data.get("project_id", None) is None or (
        data["project_id"] is not None
        and not has_manager_project_access(data["project_id"])
    ):
        data["is_shared"] = False

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
    if search_filter.is_shared:
        clear_filter_cache()
    else:
        clear_filter_cache(current_user["id"])
    return search_filter.serialize()


def remove_filter(search_filter_id):
    """
    Remove given filter from database.
    """
    current_user = persons_service.get_current_user()
    search_filter = SearchFilter.get_by(
        id=search_filter_id, person_id=current_user["id"]
    )
    if search_filter is None:
        raise SearchFilterNotFoundException
    search_filter.delete()
    if search_filter.is_shared:
        clear_filter_cache()
    else:
        clear_filter_cache(current_user["id"])
    return search_filter.serialize()


def get_filter_groups():
    """
    Retrieve search filter groups used by current user. It groups them by
    list type and project_id. If the filter group is not related to a project,
    the project_id is all.
    """
    current_user = persons_service.get_current_user()
    return get_user_filter_groups(current_user["id"])


@cache.memoize_function(120)
def get_user_filter_groups(current_user_id):
    """
    Retrieve search filter groups used for given user. It groups them by
    list type and project_id. If the filter group is not related to a project,
    the project_id is all.
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
        .all()
    )

    for search_filter_group in filter_groups:
        if search_filter_group.list_type not in result:
            result[search_filter_group.list_type] = {}
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
    list_type, name, color, project_id=None, entity_type=None, is_shared=False
):
    """
    Add a new search filter group to the database.
    """
    current_user = persons_service.get_current_user()
    if project_id is None or (
        project_id is not None and not has_manager_project_access(project_id)
    ):
        is_shared = False
    search_filter_group = SearchFilterGroup.create(
        list_type=list_type,
        name=name,
        color=color,
        project_id=project_id,
        person_id=current_user["id"],
        entity_type=entity_type,
        is_shared=is_shared,
    )
    search_filter_group.serialize()
    if search_filter_group.is_shared:
        clear_filter_group_cache()
    else:
        clear_filter_group_cache(current_user["id"])
    return search_filter_group.serialize()


def get_filter_group(search_filter_group_id):
    """
    Get given filter group from the database.
    """
    current_user = persons_service.get_current_user()
    search_filter_group = SearchFilterGroup.get_by(
        id=search_filter_group_id, person_id=current_user["id"]
    )
    if search_filter_group is None:
        raise SearchFilterGroupNotFoundException
    return search_filter_group.serialize()


def update_filter_group(search_filter_group_id, data):
    """
    Update given filter group from database.
    """
    current_user = persons_service.get_current_user()
    search_filter_group = SearchFilterGroup.get_by(
        id=search_filter_group_id, person_id=current_user["id"]
    )
    if search_filter_group is None:
        raise SearchFilterGroupNotFoundException
    if data.get("project_id", None) is None or (
        data["project_id"] is not None
        and not has_manager_project_access(data["project_id"])
    ):
        data["is_shared"] = False
    search_filter_group.update(data)

    if data.get("is_shared", None) is not None:
        if (
            SearchFilter.query.filter_by(
                search_filter_group_id=search_filter_group_id
            ).update({"is_shared": data["is_shared"]})
            > 0
        ):
            SearchFilter.query.session.commit()
            clear_filter_cache()

    if search_filter_group.is_shared:
        clear_filter_group_cache()
    else:
        clear_filter_group_cache(current_user["id"])
    return search_filter_group.serialize()


def remove_filter_group(search_filter_group_id):
    """
    Remove given filter group from database.
    """
    current_user = persons_service.get_current_user()
    search_filter_group = SearchFilterGroup.get_by(
        id=search_filter_group_id, person_id=current_user["id"]
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
    if search_filter_group.is_shared:
        clear_filter_group_cache()
    else:
        clear_filter_group_cache(current_user["id"])
    return search_filter_group.serialize()


def get_notification(notification_id):
    """
    Return notification matching given ID as a dictionnary.
    """
    notifications = get_last_notifications(notification_id)

    if len(notifications) == 0:
        raise NotificationNotFoundException

    return notifications[0]


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
):
    """
    Return last 100 user notifications.
    """
    current_user = persons_service.get_current_user()
    Author = aliased(Person, name="author")
    is_current_user_artist = current_user["role"] == "user"
    result = []
    query = (
        Notification.query.filter_by(person_id=current_user["id"])
        .order_by(Notification.created_at.desc())
        .join(Author, Author.id == Notification.author_id)
        .join(Task, Task.id == Notification.task_id)
        .join(Project, Project.id == Task.project_id)
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

    notifications = query.limit(100).all()

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
        role,
    ) in notifications:
        (full_entity_name, episode_id) = names_service.get_full_entity_name(
            task_entity_id
        )
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
            reply_mentions = reply.get("mentions", []) or []
            reply_department_mentions = (
                reply.get("departement_mentions", []) or []
            )
            if reply is not None:
                reply_text = reply["text"]

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
                }
            )
        )

    return result


def mark_notifications_as_read():
    """
    Mark all recent notifications for current_user as read. It is useful
    to mark a list of notifications as read after an user retrieved them.
    """
    current_user = persons_service.get_current_user()
    notifications = (
        Notification.query.filter_by(person_id=current_user["id"], read=False)
        .order_by(Notification.created_at)
        .all()
    )

    for notification in notifications:
        notification.update({"read": True})

    return fields.serialize_list(notifications)


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
    try:
        timezone = persons_service.get_current_user()["timezone"]
    except Exception:
        timezone = config.DEFAULT_TIMEZONE
    return timezone or config.DEFAULT_TIMEZONE


def get_context():
    if permissions.has_admin_permissions():
        projects = projects_service.open_projects()
    else:
        projects = get_open_projects()

    asset_types = assets_service.get_asset_types()
    custom_actions = custom_actions_service.get_custom_actions()
    status_automations = status_automations_service.get_status_automations()
    persons = persons_service.get_persons(
        minimal=not permissions.has_manager_permissions()
    )
    notification_count = get_unread_notifications_count()
    project_status_list = projects_service.get_project_statuses()
    departments = tasks_service.get_departments()
    studios = tasks_service.get_studios()
    task_types = tasks_service.get_task_types()
    task_status_list = tasks_service.get_task_statuses()
    search_filters = get_filters()
    search_filter_groups = get_filter_groups()
    preview_background_files = files_service.get_preview_background_files()

    return {
        "asset_types": asset_types,
        "custom_actions": custom_actions,
        "status_automations": status_automations,
        "departments": departments,
        "studios": studios,
        "notification_count": notification_count,
        "persons": persons,
        "project_status": project_status_list,
        "projects": projects,
        "task_types": task_types,
        "task_status": task_status_list,
        "search_filters": search_filters,
        "search_filter_groups": search_filter_groups,
        "preview_background_files": preview_background_files,
    }
