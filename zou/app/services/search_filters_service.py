from sqlalchemy import or_

from zou.app.models.project import Project
from zou.app.models.search_filter import SearchFilter
from zou.app.models.search_filter_group import SearchFilterGroup
from zou.app.utils import cache, permissions
from zou.app.services import (
    permissions_service,
    persons_service,
    projects_service,
    departments_service,
)
from zou.app.exceptions import (
    SearchFilterNotFoundException,
    SearchFilterGroupNotFoundException,
    WrongParameterException,
)
from zou.app.models.project_status import ProjectStatus


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
    if not permissions_service.can_share_filter(project_id):
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
        department = departments_service.get_department(department_id)
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
        department = departments_service.get_department(department_id)
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


def clear_filter_group_cache(user_id=None):
    """
    Drop the memoized filter group list of given user, or of every user.
    """
    persons_service.clear_user_scoped_cache(get_user_filter_groups, user_id)


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
    if not permissions_service.can_share_filter(project_id):
        is_shared = False

    if department_id is not None:
        department = departments_service.get_department(department_id)
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


def clear_filter_cache(user_id=None):
    """
    Drop the memoized filter list of given user, or of every user.
    """
    persons_service.clear_user_scoped_cache(get_user_filters, user_id)


def _deny_sharing_without_manager_access(data, instance):
    """
    Silently turn off a sharing request the caller is not allowed to make:
    sharing is a per project manager privilege, and a filter without a
    project cannot be shared at all. Mutates data in place.
    """
    if (
        data.get("is_shared", None) is not None
        and instance.is_shared != data["is_shared"]
        and not permissions_service.can_share_filter(
            data.get("project_id", None)
        )
    ):
        data["is_shared"] = False


def _clear_cache_after_sharing_change(clear_cache, is_shared, user_id):
    """
    A shared filter is visible to the whole team, so its cache must be
    dropped for everyone; a private one only for its owner.
    """
    if is_shared:
        clear_cache()
    else:
        clear_cache(user_id)


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
