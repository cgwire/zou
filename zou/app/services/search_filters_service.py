from sqlalchemy import and_, or_, true

from zou.app.exceptions import (
    SearchFilterGroupNotFoundException,
    SearchFilterNotFoundException,
    WrongParameterException,
)
from zou.app.models.project import Project, ProjectPersonLink
from zou.app.models.project_status import ProjectStatus
from zou.app.models.search_filter import SearchFilter
from zou.app.models.search_filter_group import SearchFilterGroup
from zou.app.services import (
    departments_service,
    permissions_service,
    persons_service,
    projects_service,
)
from zou.app.utils import cache, permissions


def get_filters():
    """
    Return the search filters of the current user, grouped by list type and
    project_id. If a filter is not related to a project, its project_id is
    all.
    """
    current_user = persons_service.get_current_user()
    return get_user_filters(current_user["id"])


@cache.memoize_function(120)
def get_user_filters(current_user_id):
    """
    Return the search filters of the given user, grouped by list type and
    project_id. If a filter is not related to a project, its project_id is
    all.

    Call this function only with the id of the current user. The cache keys
    on current_user_id alone, but get_current_user() and
    has_manager_permissions() give the values of the caller, not of the id.

    If a project access check found a per project role before in the
    request, has_manager_permissions() reads that role. The only route that
    calls this function finds no project role. Thus, the global role
    applies and the result stays the same for each user. Do not add a
    project scoped variant: the cache would give the result of the first
    caller to the other callers for the full TTL. If you need a project
    scope, give it as an argument.
    """
    result = {}

    filters = (
        SearchFilter.query.outerjoin(Project)
        .outerjoin(ProjectStatus)
        .filter(
            or_(
                SearchFilter.person_id == current_user_id,
                and_(
                    SearchFilter.is_shared == True,
                    _reaches_team_filter(
                        SearchFilter.project_id, current_user_id
                    ),
                ),
            )
        )
        .filter(
            or_(
                projects_service.build_open_project_filter(),
                SearchFilter.project_id == None,
            )
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
        # The department tells which other users see a row. The owner always
        # sees it, whatever the department.
        is_own = str(search_filter.person_id) == str(current_user_id)

        if is_own or department_id is None or is_manager or is_in_departments:
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
    Add a search filter to the database.
    """
    current_user = persons_service.get_current_user()
    _check_project_and_department_exist(project_id, department_id)
    if not permissions_service.can_share_filter(project_id):
        is_shared = False

    if search_filter_group_id is not None:
        search_filter_group = SearchFilterGroup.get_by(
            id=search_filter_group_id
        )
        if search_filter_group is None:
            raise SearchFilterGroupNotFoundException
        _check_group_is_in_project(search_filter_group, project_id)
        if is_shared != search_filter_group.is_shared:
            raise WrongParameterException(
                "A search filter should have the same value for is_shared than its search filter group."
            )
        if department_id is None:
            department_id = search_filter_group.department_id

    _check_name_is_free(
        SearchFilter,
        name,
        list_type=list_type,
        entity_type=entity_type,
        project_id=project_id,
        person_id=current_user["id"],
        search_filter_group_id=search_filter_group_id,
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
    clear_filter_cache()
    return search_filter.serialize()


def update_filter(search_filter_id, data):
    """
    Update the given filter in the database.
    """
    current_user = persons_service.get_current_user()
    search_filter = _get_own_or_as_admin(
        SearchFilter, search_filter_id, current_user
    )
    if search_filter is None:
        raise SearchFilterNotFoundException

    data.pop("project_id", None)
    search_filter_group = None
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
        # A row that keeps its group passes the check. Thus, the rows saved
        # before this rule stay editable.
        if str(search_filter_group_id) != str(
            search_filter.search_filter_group_id
        ):
            _check_group_is_in_project(
                search_filter_group, search_filter.project_id
            )
            # Kitsu sends the old department again with the new group. Thus, an
            # unchanged department means the department of the group. If the
            # group has no department, or if the user selected a department in
            # the same save, do not change the body.
            if search_filter_group.department_id is not None and str(
                data.get("department_id", search_filter.department_id)
            ) == str(search_filter.department_id):
                data["department_id"] = search_filter_group.department_id

    _check_project_and_department_exist(
        department_id=data.get("department_id")
    )
    _deny_sharing_without_manager_access(data, search_filter)

    if search_filter_group is not None:
        if (
            data.get("is_shared", search_filter.is_shared)
            != search_filter_group.is_shared
        ):
            raise WrongParameterException(
                "A search filter should have the same value for is_shared than its search filter group."
            )

    _check_new_name_is_free(
        search_filter, data, search_filter_group_id=search_filter_group_id
    )

    search_filter.update(data)
    clear_filter_cache()
    return search_filter.serialize()


def remove_filter(search_filter_id):
    """
    Remove the given filter from the database.
    """
    current_user = persons_service.get_current_user()
    search_filter = _get_own_or_as_admin(
        SearchFilter, search_filter_id, current_user
    )
    if search_filter is None:
        raise SearchFilterNotFoundException
    search_filter.delete()
    clear_filter_cache()
    return search_filter.serialize()


def clear_filter_group_cache():
    """
    Remove the memoized filter group list of all the users from the cache.
    """
    cache.cache.delete_memoized(get_user_filter_groups)


def get_filter_groups():
    """
    Return the search filter groups of the current user, grouped by list
    type and project_id. If a filter group is not related to a project, its
    project_id is all.
    """
    current_user = persons_service.get_current_user()
    return get_user_filter_groups(current_user["id"])


@cache.memoize_function(10)
def get_user_filter_groups(current_user_id):
    """
    Return the search filter groups of the given user, grouped by list type
    and project_id. If a filter group is not related to a project, its
    project_id is all.

    The warning of get_user_filters applies. The cache keys on
    current_user_id alone, but the body gives the values of the caller.
    Call this function only with the id of the current user. Call it only
    from a route that finds no project role.
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
                and_(
                    SearchFilterGroup.is_shared == True,
                    _reaches_team_filter(
                        SearchFilterGroup.project_id, current_user_id
                    ),
                ),
            )
        )
        .filter(
            or_(
                projects_service.build_open_project_filter(),
                Project.id == None,
            )
        )
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
        is_own = str(search_filter_group.person_id) == str(current_user_id)
        if is_own or department_id is None or is_manager or is_in_departments:
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
    Add a search filter group to the database.
    """
    current_user = persons_service.get_current_user()
    _check_project_and_department_exist(project_id, department_id)
    if not permissions_service.can_share_filter(project_id):
        is_shared = False

    _check_name_is_free(
        SearchFilterGroup,
        name,
        list_type=list_type,
        entity_type=entity_type,
        project_id=project_id,
        person_id=current_user["id"],
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
    clear_filter_group_cache()

    return search_filter_group.serialize()


def get_filter_group(search_filter_group_id):
    """
    Return the given filter group from the database.
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
    Update the given filter group in the database. The filters of the group
    get its new department and its is_shared value.
    """
    current_user = persons_service.get_current_user()
    search_filter_group = _get_own_or_as_admin(
        SearchFilterGroup, search_filter_group_id, current_user
    )

    if search_filter_group is None:
        raise SearchFilterGroupNotFoundException

    data.pop("project_id", None)
    _check_project_and_department_exist(
        department_id=data.get("department_id")
    )
    _deny_sharing_without_manager_access(data, search_filter_group)
    _check_new_name_is_free(search_filter_group, data)

    former_department_id = search_filter_group.department_id
    search_filter_group.update(data)

    if str(search_filter_group.department_id) != str(former_department_id):
        # The filters on the department of the group move with it. Else, the
        # group is empty for the users of the new department. A filter on a
        # different department stays on it.
        if (
            SearchFilter.query.filter_by(
                search_filter_group_id=search_filter_group_id,
                department_id=former_department_id,
            ).update({"department_id": search_filter_group.department_id})
            > 0
        ):
            SearchFilter.query.session.commit()
            clear_filter_cache()

    if data.get("is_shared", None) is not None:
        # The group now has the permitted value, because
        # _deny_sharing_without_manager_access refused the values that the
        # caller cannot ask for. Thus, the filters get the value of the
        # group, not of the body. update_filter refuses all changes to a
        # filter whose is_shared is not the same as its group. If the
        # values are different, the filters stay locked permanently.
        if (
            SearchFilter.query.filter_by(
                search_filter_group_id=search_filter_group_id
            ).update({"is_shared": search_filter_group.is_shared})
            > 0
        ):
            SearchFilter.query.session.commit()
            clear_filter_cache()

    clear_filter_group_cache()
    return search_filter_group.serialize()


def remove_filter_group(search_filter_group_id):
    """
    Remove the given filter group from the database, with the filters that
    its owner put in it. The filters of the other members stay, out of the
    group.
    """
    current_user = persons_service.get_current_user()
    search_filter_group = _get_own_or_as_admin(
        SearchFilterGroup, search_filter_group_id, current_user
    )
    if search_filter_group is None:
        raise SearchFilterGroupNotFoundException
    # In a shared group, the filters of the other members stay with
    # their owners, out of the group.
    group_filters = SearchFilter.query.filter_by(
        search_filter_group_id=search_filter_group_id
    )
    changed = group_filters.filter(
        SearchFilter.person_id != search_filter_group.person_id
    ).update({"search_filter_group_id": None})
    changed += group_filters.filter_by(
        person_id=search_filter_group.person_id
    ).delete()
    if changed > 0:
        SearchFilter.query.session.commit()
        clear_filter_cache()
    search_filter_group.delete()
    clear_filter_group_cache()
    return search_filter_group.serialize()


def _reaches_team_filter(project_id_column, current_user_id):
    """
    Return the query filter that keeps a shared filter or group for the
    teams of its project. If it has no project, it is for all the users.
    An admin sees all the productions.
    """
    if permissions.has_admin_permissions():
        return true()
    team_project_ids = ProjectPersonLink.query.with_entities(
        ProjectPersonLink.project_id
    ).filter(ProjectPersonLink.person_id == current_user_id)
    return or_(
        project_id_column == None,
        project_id_column.in_(team_project_ids),
    )


def clear_filter_cache():
    """
    Remove the memoized filter list of all the users from the cache. A row
    shows in the list of its owner. If the row is shared now, or was shared
    before this change, it also shows in the lists of its team. Writes are
    rare and a list is fast to build again. Thus, a selective removal gives
    no benefit.
    """
    cache.cache.delete_memoized(get_user_filters)


def _deny_sharing_without_manager_access(data, instance):
    """
    Silently cancel a sharing request that the caller has no permission to
    make. Only a manager of the project of the row can share it. A filter
    without a project cannot be shared. The department of a shared row
    tells who sees it. Thus, a change of this department needs the same
    permission. Change data in place.
    """
    if permissions_service.can_share_filter(instance.project_id):
        return
    if (
        data.get("is_shared", None) is not None
        and instance.is_shared != data["is_shared"]
    ):
        data["is_shared"] = False
    if (
        "department_id" in data
        and instance.is_shared
        and data.get("is_shared", True)
    ):
        del data["department_id"]


def _check_project_and_department_exist(project_id=None, department_id=None):
    """
    If the project or the department does not exist, raise a not found
    exception. Else, the foreign key causes an internal error.
    """
    if project_id is not None:
        projects_service.get_project_raw(project_id)
    if department_id is not None:
        departments_service.get_department(department_id)


def _check_group_is_in_project(search_filter_group, project_id):
    """
    If the given group is not in the given project, raise
    WrongParameterException. Only a manager of its project can share a
    group, and its filters move with it. A filter of a different project
    would go to a team outside the permission of this manager.
    """
    if str(search_filter_group.project_id) != str(project_id):
        raise WrongParameterException(
            "A search filter should be in the same project as its search filter group."
        )


def _check_name_is_free(model, name, **list_scope):
    """
    Refuse a name that a row of the same list already has. The scope has one
    owner. The caller possibly cannot see a shared row of a different user,
    and thus cannot know which row has the same name.
    """
    if model.get_by(name=name, **list_scope) is not None:
        raise WrongParameterException(
            "This name is already used in this list."
        )


def _check_new_name_is_free(instance, data, **group_scope):
    """
    Do the same check for an update, which can change the name of the row.
    A row that keeps its name passes, also when it changes group. Thus, the
    rows saved before this rule stay editable.
    """
    name = data.get("name", instance.name)
    if name != instance.name:
        _check_name_is_free(
            type(instance),
            name,
            list_type=instance.list_type,
            entity_type=instance.entity_type,
            project_id=instance.project_id,
            person_id=instance.person_id,
            **group_scope,
        )


def _get_own_or_as_admin(model, instance_id, current_user):
    """
    Return the row of the given model that the current user owns. If the
    current user is an admin, return the row whatever its owner. If no row
    matches, return None: the caller raises the exception.
    """
    instance = model.get_by(id=instance_id, person_id=current_user["id"])
    if instance is None and permissions.has_admin_permissions():
        instance = model.get_by(id=instance_id)
    return instance


def remove_search_filters(**kw):
    """
    Delete the search filters and search filter groups that match the given
    column values. When you delete a group, also delete all its filters,
    whatever their owner. remove_filter_group is different: it keeps the
    filters of the other members. Delete the filters first, because they
    reference their group. A shared filter shows in the list of all the
    users. Thus, remove the memoized lists of all the users from the cache.
    """

    group_ids = SearchFilterGroup.query.with_entities(
        SearchFilterGroup.id
    ).filter_by(**kw)
    SearchFilter.delete_all_by(
        SearchFilter.search_filter_group_id.in_(group_ids)
    )
    SearchFilter.delete_all_by(**kw)
    SearchFilterGroup.delete_all_by(**kw)
    clear_filter_cache()
    clear_filter_group_cache()
