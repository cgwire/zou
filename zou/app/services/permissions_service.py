"""
Access control for stored objects: may the current user read or write this
project, entity, task, comment or playlist.

The role carried by the request itself lives in ``zou.app.utils.permissions``,
which touches nothing but ``flask.g`` and the token. Everything here has to
load a row to decide, which is why it is a service and not a util.

Order matters. A role can be set per project, and ``permissions`` resolves it
from ``flask.g``, which only ``check_belong_to_project``, ``check_project_access``
and ``resolve_project_role`` populate. Any ``has_*``/``check_*`` role helper
called before one of those silently reads the global role.
"""

from flask import g
from sqlalchemy import or_

from zou.app.models.comment import (
    Comment,
    department_mentions_table,
    mentions_table,
)
from zou.app.models.project import Project, ProjectPersonLink
from zou.app.models.task import Task

from zou.app.services import (
    assets_service,
    edits_service,
    entities_service,
    persons_service,
    projects_service,
    shots_service,
    tasks_service,
    user_service,
)
from zou.app.utils import permissions


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
    if (
        permissions.has_admin_permissions()
        or persons_service.get_current_user()["id"] == person_id
    ):
        return True
    else:
        raise permissions.PermissionDenied


def get_project_role(person_id, project_id):
    """
    Return the effective role of given person on given project: the
    project-specific role when one is set on the team link, the person's
    global role otherwise.
    """
    link = ProjectPersonLink.query.filter_by(
        project_id=str(project_id), person_id=str(person_id)
    ).first()
    if link is not None and link.role is not None:
        return getattr(link.role, "code", link.role)
    return persons_service.get_person(person_id)["role"]


def check_belong_to_project(project_id):
    """
    Return true if current user is assigned to a task of the given project or
    if current_user is part of the project team. As a side effect, resolve
    the member's effective role for this project into flask.g so that
    subsequent role checks apply the project role. A failed check clears the
    slot so a role resolved for another project earlier in the request never
    leaks into this one.
    """
    if project_id is None:
        g.project_role = None
        return False

    project = projects_service.get_project(str(project_id), relations=True)
    current_user = persons_service.get_current_user()
    if current_user["id"] not in project["team"]:
        g.project_role = None
        return False

    if current_user["role"] != "admin":
        # Single slot: a request touching two projects keeps the role of the
        # last access check performed, which always precedes the role checks
        # it guards.
        g.project_role = get_project_role(current_user["id"], project_id)
    return True


def resolve_project_role(project_id):
    """
    Resolve the current user's effective role for given project into
    flask.g so that subsequent role checks apply the project role. Side
    effect variant of check_belong_to_project for call sites where access
    is enforced later: it never raises and its return value carries no
    access guarantee.
    """
    return check_belong_to_project(project_id)


def has_project_access(project_id):
    """
    Return true if current user is an admin or has a task assigned for this
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


def scope_criterions_to_vendor(criterions):
    """
    Narrow a listing to what a vendor is allowed to see, in place. Anyone
    else is left untouched.

    A vendor only ever lists what they are assigned to, and the departments
    travel with the assignee so that the query can keep the tasks of their
    own departments on the entities they reach.
    """
    if permissions.has_vendor_permissions():
        criterions["assigned_to"] = persons_service.get_current_user()["id"]
        criterions["vendor_departments"] = get_vendor_departments()
    return criterions


def get_vendor_departments():
    """
    Return the departments the current user belongs to, or None when they are
    not a vendor and nothing has to be narrowed down.
    """
    if not permissions.has_vendor_permissions():
        return None
    return [
        str(department.id)
        for department in persons_service.get_current_user_raw().departments
    ]


def mask_metadata_for_vendor(entity_type, entities, project_id=None):
    """
    Hide from a listing the metadata a vendor may not see, in place. Anyone
    else is left untouched.

    The listings built from criterions carry the departments along in them.
    These take no criterions, so the scope is read here, in the layer that
    still knows who is asking.
    """
    return entities_service.remove_not_allowed_metadata_for_vendor(
        entity_type, get_vendor_departments(), entities, project_id
    )


def check_entity_access(entity_id):
    """
    Return true if current user is not a vendor or has a task assigned for this
    project.
    """
    is_allowed = not permissions.has_vendor_permissions()
    if not is_allowed:
        nb_tasks = (
            Task.query.filter(Task.entity_id == entity_id)
            .filter(user_service.build_assignee_filter())
            .count()
        )
        if nb_tasks == 0:
            raise permissions.PermissionDenied
        is_allowed = True
    return is_allowed


def keep_entities_a_vendor_reaches(entities):
    """
    Drop from a listing the entities a vendor holds no task on. Anyone else
    keeps all of them.

    This is check_entity_access applied to a whole answer at once, for the
    paths that do not walk their rows one by one. A page can come back
    shorter than it was asked for, which beats handing over a production a
    vendor was never meant to read.
    """
    if not entities or not permissions.has_vendor_permissions():
        return entities
    assigned = {
        str(entity_id)
        for (entity_id,) in Task.query.with_entities(Task.entity_id)
        .filter(Task.entity_id.in_([entity["id"] for entity in entities]))
        .filter(user_service.build_assignee_filter())
        .all()
    }
    return [entity for entity in entities if entity["id"] in assigned]


def check_task_status_access(task_status_id):
    """
    Return true if current user can use this task status.

    is_artist_allowed and is_client_allowed are read off the role the caller
    holds on the production, so the caller resolves it first. Without a
    resolved role the restriction does not apply at all: it lets everything
    through rather than raise.
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


def check_task_access(task_id):
    """
    Return true if current user can have access to a task.
    """
    task = tasks_service.get_task(task_id)
    check_project_access(task["project_id"])
    check_entity_access(task["entity_id"])
    return True


def check_task_action_access(task_id):
    """
    Return true if current user can have access to a task action.
    """
    task = tasks_service.get_task(task_id, relations=True)
    is_allowed = False
    if permissions.has_admin_permissions():
        is_allowed = True
    elif check_belong_to_project(task["project_id"]):
        if (
            permissions.has_manager_permissions()
            or permissions.has_client_permissions()
        ):
            is_allowed = True
        else:
            user = persons_service.get_current_user(relations=True)
            is_allowed = user["id"] in task["assignees"]
            if not is_allowed and permissions.has_supervisor_permissions():
                is_allowed = (
                    user["departments"] == []
                    or tasks_service.get_task_type(task["task_type_id"])[
                        "department_id"
                    ]
                    in user["departments"]
                )
            if not is_allowed:
                # The entity creator keeps task action access (e.g. an artist's concept).
                entity = entities_service.get_entity(task["entity_id"])
                is_allowed = entity["created_by"] == user["id"]

    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def is_person_mentioned_on_task(person_id, task_id):
    """
    Return true if given person was mentioned anywhere in the conversation
    of given task, either by name or through one of the departments they
    belong to.

    Comments and replies store their mentions differently: a comment links
    them through comment_mentions and comment_department_mentions, while a
    reply keeps them inside the replies JSONB. Both count: someone named
    in a reply was pulled into the conversation just the same.
    """
    person = persons_service.get_person(person_id, relations=True)
    department_ids = person.get("departments") or []

    query = Comment.query.filter(Comment.object_id == task_id).outerjoin(
        mentions_table, mentions_table.c.comment == Comment.id
    )
    conditions = [
        mentions_table.c.person == person_id,
        # Containment on a JSONB array is subset semantics, so this matches
        # any reply whose mentions include the person.
        Comment.replies.contains([{"mentions": [str(person_id)]}]),
    ]
    if department_ids:
        query = query.outerjoin(
            department_mentions_table,
            department_mentions_table.c.comment == Comment.id,
        )
        conditions.append(
            department_mentions_table.c.department.in_(department_ids)
        )
        conditions.extend(
            Comment.replies.contains(
                [{"department_mentions": [str(department_id)]}]
            )
            for department_id in department_ids
        )
    return query.filter(or_(*conditions)).first() is not None


def check_task_mention_access(task_id):
    """
    Return true if current user was mentioned in a comment of given task.

    A mention pulls someone into a conversation, so it grants the right to
    answer in it and nothing else. Callers must keep every other task
    action behind check_task_action_access: this check knows nothing about
    statuses, previews or assignments.
    """
    task = tasks_service.get_task(task_id)
    # Team membership first: it resolves the project role, so the vendor
    # test below reads the role for this production and not the global one.
    if not check_belong_to_project(task["project_id"]):
        raise permissions.PermissionDenied
    if permissions.has_vendor_permissions():
        raise permissions.PermissionDenied
    person_id = persons_service.get_current_user()["id"]
    if not is_person_mentioned_on_task(person_id, task_id):
        raise permissions.PermissionDenied
    return True


def check_supervisor_project_task_type_access(project_id, task_type_id):
    """
    Return true if current user can have access to a task type.
    """
    is_allowed = False
    if permissions.has_admin_permissions() or (
        check_belong_to_project(project_id)
        and permissions.has_manager_permissions()
    ):
        is_allowed = True
    elif (
        check_belong_to_project(project_id)
        and permissions.has_supervisor_permissions()
    ):
        user = persons_service.get_current_user(relations=True)
        is_allowed = (
            user["departments"] == []
            or tasks_service.get_task_type(task_type_id)["department_id"]
            in user["departments"]
        )

    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_comment_access(comment_id, comment=None):
    """
    Return true if current user can have access to a comment. The comment
    dict can be passed in to spare a reload when the caller already holds
    it.
    """
    if permissions.has_admin_permissions():
        return True
    else:
        if comment is None:
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
                if comment["person_id"] != current_user[
                    "id"
                ] and not comment.get("for_client", False):
                    raise permissions.PermissionDenied
            if get_project_role(
                person_id, task["project_id"]
            ) == "client" or comment.get("for_client", False):
                return True
            else:
                raise permissions.PermissionDenied
        elif get_project_role(person_id, task["project_id"]) == "client":
            raise permissions.PermissionDenied

        return True


def has_manager_project_access(project_id):
    """
    Return true if current user is a manager and has a task assigned for this
    project.
    """
    return permissions.has_admin_permissions() or (
        check_belong_to_project(project_id)
        and permissions.has_manager_permissions()
    )


def check_entities_belong_to_project(entity_ids, project_id):
    """
    Return given entities, or raise a PermissionDenied exception if one of
    them is not part of given project. Meant to run before a route touches
    anything, so a mixed request changes nothing.
    """
    entities = [
        entities_service.get_entity(str(entity_id)) for entity_id in entity_ids
    ]
    if any(entity["project_id"] != project_id for entity in entities):
        raise permissions.PermissionDenied
    return entities


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
        or permissions.has_admin_permissions()
        or (
            check_belong_to_project(task["project_id"])
            and permissions.has_manager_permissions()
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
        check_belong_to_project(project_id)
        and (
            permissions.has_manager_permissions()
            or permissions.has_supervisor_permissions()
        )
    )
    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_supervisor_task_access(task, new_data=None):
    """
    Return true if current user is a manager and has a task assigned related
    to the project of this task or is a supervisor and can modify data accorded
    to his departments
    """
    if new_data is None:
        new_data = {}
    is_allowed = False
    if permissions.has_admin_permissions() or (
        check_belong_to_project(task["project_id"])
        and permissions.has_manager_permissions()
    ):
        is_allowed = True
    elif (
        check_belong_to_project(task["project_id"])
        and permissions.has_supervisor_permissions()
    ):
        # checks that the supervisor only modifies columns
        # for which he is authorized
        allowed_columns = {
            "priority",
            "start_date",
            "due_date",
            "estimation",
            "difficulty",
            "data",
        }
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


def check_metadata_department_access(entity, new_data=None):
    """
    Return true if current user is a manager and has a task assigned for this
    project or is a supervisor and is allowed to modify data accorded to
    his departments
    """
    if new_data is None:
        new_data = {}
    is_allowed = False
    belongs = check_belong_to_project(entity["project_id"])
    if permissions.has_admin_permissions() or (
        belongs
        and (
            permissions.has_manager_permissions()
            or entity["created_by"] == persons_service.get_current_user()["id"]
        )
    ):
        is_allowed = True
    elif belongs and permissions.has_supervisor_permissions():
        # checks that the supervisor only modifies columns
        # for which he is authorized
        allowed_columns = {"data"}
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
    if not task or not user:
        raise permissions.PermissionDenied
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


def check_person_is_not_bot(person_id, project_id=None):
    """
    Return true if person is not a bot else raise PermissionDenied.

    Bots are allowed when project_id is given and that project has bot
    collaboration enabled (used for AI-agent task assignment and time logs).
    """
    if persons_service.get_person(person_id)["is_bot"]:
        if project_id is not None:
            project = Project.get(project_id)
            if project is not None and project.is_bot_collaboration_enabled:
                return True
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
    # The last branch reads the assignees, which only the related
    # serialization carries.
    task = tasks_service.get_task(task_id, relations=True)
    if not task or not user:
        raise permissions.PermissionDenied
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
            or (user["id"] in task["assignees"] and person_id == user["id"])
        )
    )
    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_all_departments_access(project_id, departments=None):
    """
    Return true if current user is admin or is manager and is in team or is
    supervisor and is in team and have access to all departments.
    """
    if departments is None:
        departments = []
    if not isinstance(departments, list):
        departments = [departments]
    is_allowed = False
    belongs = check_belong_to_project(project_id)
    if permissions.has_admin_permissions() or (
        belongs and permissions.has_manager_permissions()
    ):
        is_allowed = True
    elif belongs and permissions.has_supervisor_permissions():
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
    """
    Managers see every playlist of a project they belong to. Clients see
    only the ones flagged for them. Supervisors see them when the caller
    opts in with supervisor_access.

    The project access check comes first on purpose: it is what resolves
    the per project role the has_*_permissions calls below read.
    """
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


def check_playlist_update_access(playlist):
    """
    Allow manager with project access, or supervisor of the project who
    created the playlist (or playlist with no creator).

    The supervisor branch checks team membership on its own: a failed
    has_manager_project_access clears the project role slot, so
    has_supervisor_permissions would otherwise fall back to the global
    role and let a supervisor of another production through.
    """
    is_manager = has_manager_project_access(playlist["project_id"])
    is_creator_supervisor = (
        check_belong_to_project(playlist["project_id"])
        and permissions.has_supervisor_permissions()
        and playlist["created_by"]
        in [None, persons_service.get_current_user()["id"]]
    )
    is_allowed = is_manager or is_creator_supervisor
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
