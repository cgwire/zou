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
        # The department tells whom else a row reaches: its owner lists it
        # whatever the department.
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
    Add a new search filter to the database.
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
    Update given filter from database.
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
        # A row keeping its group passes, so the ones saved before this rule
        # stay editable.
        if str(search_filter_group_id) != str(
            search_filter.search_filter_group_id
        ):
            _check_group_is_in_project(
                search_filter_group, search_filter.project_id
            )
            # A filter joining a group takes its department, whatever the
            # body says: Kitsu sends the former one back with the new group.
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
    Remove given filter from database.
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
    Drop the memoized filter group list of every user.
    """
    cache.cache.delete_memoized(get_user_filter_groups)


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
    Add a new search filter group to the database.
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

    data.pop("project_id", None)
    _check_project_and_department_exist(
        department_id=data.get("department_id")
    )
    _deny_sharing_without_manager_access(data, search_filter_group)
    _check_new_name_is_free(search_filter_group, data)

    former_department_id = search_filter_group.department_id
    search_filter_group.update(data)

    if str(search_filter_group.department_id) != str(former_department_id):
        # The filters on the department of the group follow it: left there,
        # they would leave the group empty for those it reaches now. A filter
        # set on another department stays on it.
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

    clear_filter_group_cache()
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
    # The filters of the other members in a shared group stay theirs, out
    # of the group.
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
    Query filter keeping a shared filter or group to the teams of its
    project, or to everyone when it names no project. An admin reaches
    every production.
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
    Drop the memoized filter list of every user. A row shows in the lists of
    its owner and, shared now or until this change, of its team: a write is
    rare and a list costs little to rebuild, so telling them apart saves
    nothing.
    """
    cache.cache.delete_memoized(get_user_filters)


def _deny_sharing_without_manager_access(data, instance):
    """
    Silently turn off a sharing request the caller is not allowed to make:
    sharing is a manager privilege on the project of the row, and a filter
    without a project cannot be shared at all. The department of a row that
    stays shared tells who it reaches, so changing it takes the same
    privilege. Mutates data in place.
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
    Raise a not found exception for a project or a department of no row, which
    would otherwise reach a foreign key and end in an internal error.
    """
    if project_id is not None:
        projects_service.get_project_raw(project_id)
    if department_id is not None:
        departments_service.get_department(department_id)


def _check_group_is_in_project(search_filter_group, project_id):
    """
    Sharing a group takes a manager of its project, and its filters follow it:
    a filter of another project would reach a team beyond that right.
    """
    if str(search_filter_group.project_id) != str(project_id):
        raise WrongParameterException(
            "A search filter should be in the same project as its search filter group."
        )


def _check_name_is_free(model, name, **list_scope):
    """
    Refuse a name already given to a row of the same list. The scope holds
    one owner: a shared row of someone else can be out of the sight of the
    caller, who could not tell what the name clashes with.
    """
    if model.get_by(name=name, **list_scope) is not None:
        raise WrongParameterException(
            "This name is already used in this list."
        )


def _check_new_name_is_free(instance, data, **group_scope):
    """
    Same check for an update, which can change the name of the row. A row
    keeping it passes, even when it changes group, so the ones saved before
    this rule stay editable.
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
    Return the row of given model belonging to the current user, falling
    back to the row whoever owns it when they are an admin. Returns None
    when nothing matches, the caller raises.
    """
    instance = model.get_by(id=instance_id, person_id=current_user["id"])
    if instance is None and permissions.has_admin_permissions():
        instance = model.get_by(id=instance_id)
    return instance


def remove_search_filters(**kw):
    """
    Delete the search filters and search filter groups matching given
    column values. A group takes the filters it holds with it, whoever
    owns them, as removing a single group does: they go first, since they
    reference their group. A shared filter shows in the listing of every
    user, so the memoized listings are dropped for all of them.
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
