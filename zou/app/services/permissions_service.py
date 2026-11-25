"""
Access control for stored objects: can the current user read or write
this project, entity, task, comment or playlist.

The role of the request is in ``zou.app.utils.permissions``. That module
uses only ``flask.g`` and the token. Each rule here must load a row to
decide. Thus this module is a service and not a util.

The order is important. A role can be set for each project, and
``permissions`` reads it from ``flask.g``. Only ``check_belong_to_project``,
``check_project_access`` and ``resolve_project_role`` write it there. If a
``has_*``/``check_*`` role helper runs before one of these, it reads the
global role without a warning.

The location of each rule:

- ``zou.app.utils.permissions``: the role of the request (admin, manager,
  supervisor, user, client, vendor) and the ``require_*`` decorators.
- this module: all rules that need a row (project membership, task and
  entity access, playlist and comment ownership, filter sharing).
- ``user_service``: no rule of its own. It limits listings to the
  projects of the caller with the helpers above.
"""

from flask import g
from sqlalchemy import or_

from zou.app.exceptions import CommentNotFoundException
from zou.app.models.comment import (
    Comment,
    department_mentions_table,
    mentions_table,
)
from zou.app.models.entity import AssetInstanceLink, EntityLink
from zou.app.models.person import DepartmentLink, Person
from zou.app.models.project import Project, ProjectPersonLink
from zou.app.models.task import Task
from zou.app.services import (
    base_service,
    entities_service,
    entity_types_service,
    metadata_descriptors_service,
    persons_service,
    playlists_service,
    projects_service,
    task_types_service,
    tasks_service,
)
from zou.app.utils import permissions


def check_working_on_entity(entity_id):
    """
    Return True if the user has an assigned task on the given entity. If
    not, raise PermissionDenied.
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
    Return True if the given task is assigned to the user. If not, raise
    PermissionDenied.
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
    Return True if the user is an admin or has the given person ID. If
    not, raise PermissionDenied.
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
    Return the effective role of the given person on the given project. If
    the team link has a project role, return it. If not, return the global
    role of the person. An admin role on the link is invalid data: return
    the global role, as in permissions._effective_role.
    """
    role = projects_service.get_team_roles(str(project_id)).get(str(person_id))
    if role not in (None, "admin"):
        return role
    return persons_service.get_person(person_id)["role"]


def check_belong_to_project(project_id):
    """
    Return True if the current user is part of the project team. As a side
    effect, write the effective role of the member for this project into
    flask.g. Thus the role checks that follow apply the project role. An
    admin keeps the global role: the slot is cleared. A failed check
    clears the slot. Thus a role resolved for another project earlier in
    the request never applies to this project. This function does not
    raise.
    """
    if project_id is None:
        g.project_role = None
        return False

    team = projects_service.get_team_person_ids(str(project_id))
    current_user = persons_service.get_current_user()
    if current_user["id"] not in team:
        g.project_role = None
        return False

    # There is one slot only. If a request uses two projects, it keeps the
    # role of the last access check. That check always comes before the
    # role checks that it protects. An admin keeps the global role, thus
    # the slot is cleared, and the role resolved before does not stay.
    if current_user["role"] == "admin":
        g.project_role = None
    else:
        g.project_role = get_project_role(current_user["id"], project_id)
    return True


def resolve_project_role(project_id):
    """
    Write the effective role of the current user for the given project
    into flask.g. Thus the role checks that follow apply the project role.
    This is the side effect variant of check_belong_to_project, for call
    sites that check the access later. It does not raise, and its return
    value does not guarantee access.
    """
    return check_belong_to_project(project_id)


def has_project_access(project_id):
    """
    Return True if the current user is an admin or is part of the project
    team. For an admin, clear the project role slot. For all other users,
    resolve the project role as a side effect (see
    check_belong_to_project).
    """
    if permissions.has_admin_permissions():
        # An admin keeps the global role. Clear the slot, so that a role
        # resolved before does not apply.
        g.project_role = None
        return True
    return check_belong_to_project(project_id)


def check_project_access(project_id):
    """
    Return True if the current user is an admin or is part of the project
    team. If not, raise a PermissionDenied exception. Resolve the project
    role as a side effect, see has_project_access.
    """
    is_allowed = has_project_access(project_id)
    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_project_edition_access(project_id):
    """
    Check the project access of the members who edit its structure, for
    example the shots of a scene or the asset instances. A client or a
    vendor does not get this access: raise a PermissionDenied exception.
    Resolve the project role first, as a side effect of
    check_project_access.
    """
    check_project_access(project_id)
    block_access_to_client()
    return block_access_to_vendor()


def block_access_to_vendor():
    """
    If the current user has a vendor role, raise PermissionDenied.
    """
    if permissions.has_vendor_permissions():
        raise permissions.PermissionDenied
    return True


def block_access_to_client():
    """
    If the current user has a client role, raise PermissionDenied. Call it
    after the project access check, which resolves the role on the
    project.
    """
    if permissions.has_client_permissions():
        raise permissions.PermissionDenied
    return True


def scope_criterions_to_vendor(criterions):
    """
    Limit a listing, in place, to the data that a vendor can see. For all
    other users, do not change the listing.

    A vendor lists only the items assigned to them. The departments go
    with the assignee. Thus the query can keep the tasks of their own
    departments on the entities that they can access.
    """
    if permissions.has_vendor_permissions():
        criterions["assigned_to"] = persons_service.get_current_user()["id"]
        criterions["vendor_departments"] = get_vendor_departments()
    return criterions


def get_vendor_departments():
    """
    Return the departments of the current user. If the user is not a
    vendor, there is nothing to limit: return None.
    """
    if not permissions.has_vendor_permissions():
        return None
    return [
        str(department.id)
        for department in persons_service.get_current_user_raw().departments
    ]


def mask_metadata_for_vendor(entity_type, entities, project_id=None):
    """
    Hide, in place, the metadata that a vendor must not see in a listing
    or in a page of a listing. For all other users, do not change it.

    The listings built from criterions contain the departments. These
    listings take no criterions. Thus read the scope here, in the layer
    that still knows the caller.
    """
    rows = entities["data"] if isinstance(entities, dict) else entities
    metadata_descriptors_service.remove_not_allowed_metadata_for_vendor(
        entity_type, get_vendor_departments(), rows, project_id
    )
    return entities


def check_entity_access(entity_id):
    """
    Return True if the current user is not a vendor, or has an assigned
    task on the given entity. If not, raise PermissionDenied. This check
    filters vendors only and does not check the project. Call
    check_project_access first.
    """
    is_allowed = not permissions.has_vendor_permissions()
    if not is_allowed:
        nb_tasks = (
            Task.query.filter(Task.entity_id == entity_id)
            .filter(persons_service.build_assignee_filter())
            .count()
        )
        if nb_tasks == 0:
            raise permissions.PermissionDenied
        is_allowed = True
    return is_allowed


def check_vendor_asset_instance_access(asset_instance, temporal_entity_id):
    """
    Return True if one of these conditions is true:
    - the current user is not a vendor
    - the user has an assigned task on the asset of the given instance
    - the user has an assigned task on the given temporal entity, and the
      instance is in it: its scene, its target asset, or a shot where it
      is cast.
    Like check_entity_access, this check filters vendors only. Resolve the
    project first.
    """
    if not permissions.has_vendor_permissions():
        return True
    entity_ids = [asset_instance["asset_id"]]
    is_placed = temporal_entity_id in (
        asset_instance["scene_id"],
        asset_instance["target_asset_id"],
    ) or (
        AssetInstanceLink.query.filter_by(
            entity_id=temporal_entity_id,
            asset_instance_id=asset_instance["id"],
        ).count()
        > 0
    )
    if is_placed:
        entity_ids.append(temporal_entity_id)
    nb_tasks = (
        Task.query.filter(Task.entity_id.in_(entity_ids))
        .filter(persons_service.build_assignee_filter())
        .count()
    )
    if nb_tasks == 0:
        raise permissions.PermissionDenied
    return True


def check_assigned_or_cast_entity_access(entity_id):
    """
    Check the access to an entity. An administrator, a manager or a
    supervisor can access all the entities of the resolved project. All
    other users, usually vendors, can access the entities where they have
    a task. They can also access the assets cast in these entities, to
    build the scene of a shot. Resolve the project first.
    """
    if (
        permissions.has_admin_permissions()
        or permissions.has_at_least_supervisor_permissions()
    ):
        return True
    assigned_tasks = Task.query.filter(persons_service.build_assignee_filter())
    if assigned_tasks.filter(Task.entity_id == entity_id).count():
        return True
    if (
        assigned_tasks.join(
            EntityLink, EntityLink.entity_in_id == Task.entity_id
        )
        .filter(EntityLink.entity_out_id == entity_id)
        .count()
    ):
        return True
    raise permissions.PermissionDenied


def check_file_download_access(entity_id):
    """
    Check the download of the content of a working or an output file. A
    client of the project cannot download it. An artist of the project
    can access all its entities, as a manager or a supervisor can. For a
    vendor, check_assigned_or_cast_entity_access applies. Resolve the
    project first.
    """
    block_access_to_client()
    if permissions.has_artist_permissions():
        return True
    return check_assigned_or_cast_entity_access(entity_id)


def keep_entities_a_vendor_reaches(entities):
    """
    Remove from a listing the entities where a vendor has no task. For all
    other users, keep all the entities.

    This is check_entity_access applied to a full answer at the same time,
    for the paths that do not examine their rows one by one. A page can be
    shorter than the requested size. This is better than to give a vendor
    a production that they must not read.
    """
    if not entities or not permissions.has_vendor_permissions():
        return entities
    assigned = {
        str(entity_id)
        for (entity_id,) in Task.query.with_entities(Task.entity_id)
        .filter(Task.entity_id.in_([entity["id"] for entity in entities]))
        .filter(persons_service.build_assignee_filter())
        .all()
    }
    return [entity for entity in entities if entity["id"] in assigned]


def check_task_status_access(task_status_id, project_id):
    """
    Return True if the current user can use this task status.

    is_artist_allowed and is_client_allowed apply to the role of the
    caller on the production. Thus the caller resolves it first. If no
    role is resolved, the restriction does not apply: the check allows
    all statuses and does not raise. The project value of
    is_client_allowed has priority over the studio value.
    """
    is_artist = permissions.has_artist_permissions()
    is_client = permissions.has_client_permissions()
    if is_artist or is_client:
        task_status = task_types_service.get_task_status(task_status_id)
        if is_artist and not task_status["is_artist_allowed"]:
            raise permissions.PermissionDenied
        if is_client:
            if not projects_service.is_task_status_client_allowed(
                project_id, task_status
            ):
                raise permissions.PermissionDenied
    return True


def check_chat_access(entity_id):
    """
    Return True if the current user can use the chat of the given entity,
    or the files of its messages. The team of its project can use it. With
    the role on the project, the clients cannot use it, and the vendors
    without a task on the entity cannot use it. Resolve the project role
    as a side effect (see check_project_access). If the user cannot use
    the chat, raise PermissionDenied.
    """
    entity = entities_service.get_entity(entity_id)
    check_project_access(entity["project_id"])
    check_entity_access(entity_id)
    block_access_to_client()
    return True


def check_task_access(task_id):
    """
    Return True if the current user can access a task. The user must have
    project access. A vendor must also have a task on its entity. If not,
    raise PermissionDenied. Resolve the project role as a side effect (see
    check_project_access).
    """
    task = tasks_service.get_task(task_id)
    check_project_access(task["project_id"])
    check_entity_access(task["entity_id"])
    return True


def can_access_task(person_id, task):
    """
    Return True if the given person can access the given task. This is
    the rule of check_task_access for all persons, not only for the
    current user. An admin can access all tasks. All other persons must
    be in the team of the project. A vendor must also have a task on the
    entity.
    """
    if persons_service.get_person(person_id)["role"] == "admin":
        return True
    project_id = str(task["project_id"])
    if str(person_id) not in projects_service.get_team_person_ids(project_id):
        return False
    if get_project_role(person_id, project_id) != "vendor":
        return True
    return (
        Task.query.filter(Task.entity_id == task["entity_id"])
        .filter(Task.assignees.any(Person.id == person_id))
        .count()
        > 0
    )


def check_task_action_access(task_id):
    """
    Return True if the current user can access a task action. This applies
    to an admin, or to a member of the project team who is one of these:
    - a manager
    - a client
    - an assignee of the task
    - a supervisor of its department
    - the creator of its entity.
    If not, raise PermissionDenied. Resolve the project role as a side
    effect (see check_belong_to_project).
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
                    or task_types_service.get_task_type(task["task_type_id"])[
                        "department_id"
                    ]
                    in user["departments"]
                )
            if not is_allowed:
                # The entity creator keeps task action access (for
                # example, the concept of an artist).
                entity = entities_service.get_entity(task["entity_id"])
                is_allowed = entity["created_by"] == user["id"]

    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_task_work_access(task_id):
    """
    Check the task action access for the work itself: previews and working
    files. A client can comment on a task, but cannot add deliverables.
    The action check resolves the project role first.
    """
    check_task_action_access(task_id)
    return block_access_to_client()


def is_person_mentioned_on_task(person_id, task_id):
    """
    Return True if the conversation of the given task mentions the given
    person. The mention can use the name of the person or one of their
    departments.

    Comments and replies store their mentions differently. A comment links
    them with comment_mentions and comment_department_mentions. A reply
    keeps them in the replies JSONB. Both count: a person named in a reply
    is also part of the conversation.
    """
    person = persons_service.get_person(person_id, relations=True)
    department_ids = person.get("departments") or []

    query = Comment.query.filter(Comment.object_id == task_id).outerjoin(
        mentions_table, mentions_table.c.comment == Comment.id
    )
    conditions = [
        mentions_table.c.person == person_id,
        # Containment on a JSONB array is a subset test. Thus this matches
        # all replies whose mentions include the person.
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
    Return True if a comment of the given task mentions the current user.

    A mention adds a person to a conversation. Thus it gives the right to
    answer in it, and nothing more. Callers must keep all other task
    actions behind check_task_action_access. This check does not know
    about statuses, previews or assignments.
    """
    task = tasks_service.get_task(task_id)
    # Check the team membership first. It resolves the project role, thus
    # the vendor test below reads the role for this production, not the
    # global role.
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
    Return True if the current user can access a task type. This applies
    to these users:
    - an admin
    - a manager of the project team
    - a supervisor of the project team in the department of the task type
      (or in no department).
    If not, raise PermissionDenied. Resolve the project role as a side
    effect (see check_belong_to_project).
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
            or task_types_service.get_task_type(task_type_id)["department_id"]
            in user["departments"]
        )

    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def can_read_comment(person_id, comment, project_id):
    """
    Return True if the role of the given person on the given project lets
    them read the given comment. This function does not check the access
    to the project and to the entity. You can give any person, not only
    the current user: the notifications use it for each recipient.
    """
    if persons_service.get_person(person_id)["role"] == "admin":
        return True
    role = get_project_role(person_id, project_id)
    if role in ("manager", "supervisor"):
        return True
    is_author_client = (
        get_project_role(comment["person_id"], project_id) == "client"
    )
    if role != "client":
        return not is_author_client
    if comment.get("for_client", False):
        return True
    project = projects_service.get_project(str(project_id))
    if project.get("is_clients_isolated", False):
        return comment["person_id"] == str(person_id)
    return is_author_client


def can_read_reply(person_id, comment, author_id, project_id):
    """
    Return True if the given person can read a reply of the given author
    under the given comment. A reply is read with its comment: a client
    who reads the comment reads all its replies. An artist and a vendor
    cannot see the text of a client, in a reply or in a comment.
    """
    # For the clients, the reply is a comment: only its author counts.
    reply = {"person_id": str(author_id), "for_client": True}
    return can_read_comment(
        person_id, comment, project_id
    ) and can_read_comment(person_id, reply, project_id)


def check_comment_access(comment_id, comment=None):
    """
    Return True if the current user can access a comment. If the caller
    already has the comment dict, it can give it, so that the function
    does not load it again. If not, raise PermissionDenied. For all users
    but an admin, resolve the project role as a side effect (see
    check_project_access).
    """
    if permissions.has_admin_permissions():
        return True
    else:
        if comment is None:
            comment = base_service.get_instance(
                Comment, comment_id, CommentNotFoundException
            ).serialize()
        task_id = comment["object_id"]
        task = tasks_service.get_task(task_id)
        check_project_access(task["project_id"])
        check_entity_access(task["entity_id"])

        current_user = persons_service.get_current_user()
        if not can_read_comment(
            current_user["id"], comment, task["project_id"]
        ):
            raise permissions.PermissionDenied
        return True


def has_manager_project_access(project_id):
    """
    Return True if the current user is an admin, or a manager on the
    project team. Resolve the project role as a side effect (see
    check_belong_to_project).
    """
    return permissions.has_admin_permissions() or (
        check_belong_to_project(project_id)
        and permissions.has_manager_permissions()
    )


def can_share_filter(project_id):
    """
    Return True if the current user can share a search filter or a filter
    group on the given project. Only a manager of the project can share.
    A filter without a project cannot be shared.
    """
    return project_id is not None and has_manager_project_access(project_id)


def check_entities_belong_to_project(entity_ids, project_id):
    """
    Return the given entities. If one of them is not part of the given
    project, raise a PermissionDenied exception. Call it before the route
    changes data, so that a mixed request changes nothing.
    """
    entities = [
        entities_service.get_entity(str(entity_id)) for entity_id in entity_ids
    ]
    if any(entity["project_id"] != project_id for entity in entities):
        raise permissions.PermissionDenied
    return entities


def check_metadata_descriptor_access(descriptor):
    """
    If the current user cannot read the given metadata descriptor with
    their role on its project, raise a PermissionDenied exception. A
    client reads only the descriptors published to clients. A vendor
    reads only the descriptors of their departments or of no department.
    The descriptor listing of a production uses the same rule. This
    function resolves the project before it reads the role.
    """
    check_project_access(descriptor["project_id"])
    for_client, vendor_departments = get_descriptor_visibility(
        permissions.get_effective_role()
    )
    if not metadata_descriptors_service.is_metadata_descriptor_visible(
        descriptor["id"], for_client, vendor_departments
    ):
        raise permissions.PermissionDenied
    return True


def check_manager_project_access(project_id):
    """
    Return True if the current user is an admin, or a manager on the
    project team. If not, raise a PermissionDenied exception. Resolve the
    project role as a side effect (see check_belong_to_project).
    """
    is_allowed = has_manager_project_access(project_id)
    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_entity_delete_access(entity, force=False):
    """
    Check the deletion of an entity. A member of the project team can
    delete the entities they created. A manager of the project can delete
    all entities. Only a manager of the project can force a deletion,
    because it removes the work of other persons below the entity. If not,
    raise a PermissionDenied exception. Resolve the project role as a side
    effect (see check_belong_to_project).
    """
    if (
        not force
        and entity["created_by"] == persons_service.get_current_user()["id"]
    ):
        check_project_access(entity["project_id"])
    else:
        check_manager_project_access(entity["project_id"])
    return True


def check_time_spent_access(task_id, person_id):
    """
    Return True if the current user is an admin. Also return True if the
    task is assigned to the person, and the current user is that person or
    a manager of the project. If not, raise PermissionDenied. The manager
    branch resolves the project role as a side effect (see
    check_belong_to_project).
    """
    task = tasks_service.get_task(task_id, relations=True)
    is_allowed = permissions.has_admin_permissions() or (
        person_id in task["assignees"]
        and (
            persons_service.get_current_user()["id"] == person_id
            or (
                check_belong_to_project(task["project_id"])
                and permissions.has_manager_permissions()
            )
        )
    )

    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_supervisor_project_access(project_id):
    """
    Return True if the current user is an admin, or a manager or a
    supervisor on the project team. If not, raise PermissionDenied.
    Resolve the project role as a side effect (see
    check_belong_to_project).
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
    Return True if the current user is one of these:
    - an admin
    - a manager on the team of the project of this task
    - a supervisor on that team who changes only the planning fields
      (priority, dates, estimation, difficulty, data) of a task of their
      departments.
    If not, raise PermissionDenied. Resolve the project role as a side
    effect (see check_belong_to_project).
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
        # Make sure that the supervisor changes only the columns that
        # they are allowed to change.
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
                or task_types_service.get_task_type(task["task_type_id"])[
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
    Return True if the current user is one of these:
    - an admin
    - a manager or the creator of the entity on the project team
    - a supervisor on that team who changes only the metadata of the
      descriptors of their departments.
    If not, raise PermissionDenied. Resolve the project role as a side
    effect (see check_belong_to_project).
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
        # Make sure that the supervisor changes only the columns that
        # they are allowed to change.
        allowed_columns = {"data"}
        if len(set(new_data.keys()) - allowed_columns) == 0:
            user_departments = persons_service.get_current_user(
                relations=True
            )["departments"]
            if user_departments == []:
                is_allowed = True
            else:
                entity_type = None
                if entity_types_service.is_shot(entity):
                    entity_type = "Shot"
                elif entity_types_service.is_asset(
                    entities_service.get_entity_raw(entity["id"])
                ):
                    entity_type = "Asset"
                elif entity_types_service.is_edit(entity):
                    entity_type = "Edit"
                if entity_type:
                    descriptors = [
                        descriptor
                        for descriptor in metadata_descriptors_service.get_metadata_descriptors(
                            entity["project_id"]
                        )
                        if descriptor["entity_type"] == entity_type
                    ]
                    found_and_in_departments = False
                    for descriptor_name in (new_data.get("data") or {}).keys():
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
    Return True if the current user is one of these:
    - an admin
    - a manager in the team
    - a supervisor in the team, in the department of the task, who shares
      a department with the given person
    - a supervisor in the team with no department
    - a member of the team who assigns themselves to a task of their
      department.
    If not, raise PermissionDenied. Resolve the project role as a side
    effect (see check_belong_to_project).
    """
    user = persons_service.get_current_user(relations=True)
    task = tasks_service.get_task(task_id)
    if not task or not user:
        raise permissions.PermissionDenied
    task_type = task_types_service.get_task_type(task["task_type_id"])
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
    Return True if the person is not a bot. If not, raise
    PermissionDenied.

    Bots are allowed if project_id is given and bot collaboration is
    enabled on that project. AI-agent task assignment and time logs use
    this.
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
    Return True if the current user is one of these:
    - an admin
    - a manager in the team
    - a supervisor in the team, in the department of the task (or in no
      department)
    - an assignee of the task who unassigns themselves.
    If not, raise PermissionDenied. Resolve the project role as a side
    effect (see check_belong_to_project).
    """
    user = persons_service.get_current_user(relations=True)
    # The last branch reads the assignees. Only the related serialization
    # contains them.
    task = tasks_service.get_task(task_id, relations=True)
    if not task or not user:
        raise permissions.PermissionDenied
    task_type = task_types_service.get_task_type(task["task_type_id"])
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
    Return True if the current user is one of these:
    - an admin
    - a manager in the team
    - a supervisor in the team, with given departments that are all
      departments of the supervisor (or the supervisor has no department).
    If not, raise PermissionDenied. Resolve the project role as a side
    effect (see check_belong_to_project).
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
                department in user_departments for department in departments
            )
        )
    if not is_allowed:
        raise permissions.PermissionDenied
    return is_allowed


def check_playlist_access(playlist, supervisor_access=False):
    """
    Check the access to a playlist. Managers see all the playlists of
    their projects. Clients see only the playlists flagged for them.
    Supervisors see them if the caller sets supervisor_access.

    The project access check comes first intentionally. It resolves the
    project role that the has_*_permissions calls below read.
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


def check_playlist_read_access(playlist):
    """
    If the current user cannot read the given playlist with their role on
    its project, raise a PermissionDenied exception. All members of the
    production, but its vendors, can watch its playlists. A client can
    watch only the playlists shared with clients. The playlist listing of
    a production uses the same rule. A playlist without a for_client flag
    is internal, as in that listing. This check is intentionally wider
    than check_playlist_access, which prevents artists from the downloads
    and the build jobs. This function resolves the project before it
    reads the role.
    """
    check_project_access(playlist["project_id"])
    block_access_to_vendor()
    if permissions.has_client_permissions() and not playlist["for_client"]:
        raise permissions.PermissionDenied
    return True


def check_playlist_room_access(playlist_id):
    """
    If the current user cannot join the review room of the given playlist,
    raise a PermissionDenied exception. If the playlist does not exist,
    raise a PlaylistNotFoundException. The room shows the shot, the
    preview and the annotations of the review. Thus it uses the rules of
    the playlist routes:
    - all members of the production can join it
    - a client can join only if the playlist is shared with clients
    - a vendor cannot join.
    """
    playlist = playlists_service.get_playlist(playlist_id)
    return check_playlist_read_access(playlist)


def check_playlist_update_access(playlist):
    """
    Allow a manager with project access, or a supervisor of the project who
    created the playlist (or a playlist without a creator).

    The supervisor branch checks the team membership itself. A failed
    has_manager_project_access clears the project role slot. Without this
    check, has_supervisor_permissions uses the global role, and a
    supervisor of another production gets access.
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
    Return True if the current user is an admin or if the day_off is for
    the current user. If not, raise PermissionDenied.
    """
    user = persons_service.get_current_user()
    is_admin = permissions.has_admin_permissions()
    is_same_person = user["id"] == day_off["person_id"]
    if not (is_admin or is_same_person):
        raise permissions.PermissionDenied
    return True


def _day_off_read_scopes(person):
    """
    Return a dict of the productions where the given person is in the
    team, with their role in each production. Keep only the productions
    where that role can read the leave of the team: manager or supervisor.
    The role on the team link has priority over the global role, as it
    does after the project is resolved.
    """
    scopes = {}
    for link in ProjectPersonLink.query.filter_by(person_id=person["id"]):
        role = getattr(link.role, "code", link.role) or person["role"]
        if role in ("manager", "supervisor"):
            scopes[str(link.project_id)] = role
    return scopes


def _supervised_person_ids(supervisor, person_ids):
    """
    Return only the given person IDs that the given supervisor supervises.
    A supervisor without a department supervises all persons. Other
    supervisors supervise the persons that share one or more of their
    departments.
    """
    person_ids = set(person_ids)
    if not supervisor["departments"] or not person_ids:
        return person_ids
    links = DepartmentLink.query.filter(
        DepartmentLink.person_id.in_(list(person_ids)),
        DepartmentLink.department_id.in_(supervisor["departments"]),
    )
    return {str(link.person_id) for link in links}


def check_day_off_read_access(person_id):
    """
    Return True if the current user reads the day offs of the given person
    with their description. This applies to an admin, to the person, or
    to a manager of a production of the person. Return False if the user
    reads only the dates. This applies to a supervisor of such a
    production who supervises the department of the person. If not, raise
    PermissionDenied. Only the person and the admins can write a day off,
    see check_day_off_access.
    """
    person_id = str(person_id)
    current_user = persons_service.get_current_user(relations=True)
    if permissions.has_admin_permissions() or current_user["id"] == person_id:
        return True

    scopes = _day_off_read_scopes(current_user)
    roles = set()
    if scopes:
        links = ProjectPersonLink.query.filter(
            ProjectPersonLink.project_id.in_(list(scopes.keys())),
            ProjectPersonLink.person_id == person_id,
        )
        roles = {scopes[str(link.project_id)] for link in links}
    if "manager" in roles:
        return True
    if "supervisor" in roles and _supervised_person_ids(
        current_user, [person_id]
    ):
        return False
    raise permissions.PermissionDenied


def get_day_off_readable_person_ids():
    """
    Return the persons whose day offs the current user can read, with the
    rule of check_day_off_read_access. The result is a dict: the key is
    the person ID. The value is True if the user reads the description,
    and False if the user reads the dates only. For the admins, return
    None: they read the day offs of all persons, with description.
    """
    if permissions.has_admin_permissions():
        return None
    current_user = persons_service.get_current_user(relations=True)
    readable = {current_user["id"]: True}
    scopes = _day_off_read_scopes(current_user)
    if not scopes:
        return readable

    supervised_ids = set()
    links = ProjectPersonLink.query.filter(
        ProjectPersonLink.project_id.in_(list(scopes.keys()))
    )
    for link in links:
        person_id = str(link.person_id)
        if scopes[str(link.project_id)] == "manager":
            readable[person_id] = True
        else:
            supervised_ids.add(person_id)
    for person_id in _supervised_person_ids(current_user, supervised_ids):
        readable.setdefault(person_id, False)
    return readable


def get_descriptor_visibility(role):
    """
    Return the (for_client, vendor_departments) pair that limits the
    metadata descriptors sent to the current user with the given role. A
    client gets only the descriptors published to clients. A vendor gets
    only the descriptors of their departments. A role can be set for each
    project: give the role on the served project.
    """
    if role == "client":
        return True, None
    if role == "vendor":
        departments = persons_service.get_current_user(relations=True)[
            "departments"
        ]
        return False, departments
    return False, None
