import uuid

from flask import current_app
from sqlalchemy import func

from zou.app.exceptions import (
    StatusAutomationNotFoundException,
    WrongParameterException,
)
from zou.app.models.entity_type import EntityType
from zou.app.models.project import ProjectStatusAutomationLink
from zou.app.models.project_template import (
    ProjectTemplateStatusAutomationLink,
)
from zou.app.models.status_automation import (
    CHANGE_TYPES,
    StatusAutomation,
    build_simple_trigger,
)
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType
from zou.app.services import base_service, entity_types_service
from zou.app.utils import cache, fields

TRIGGER_OPERATORS = ("and", "or")
MAX_TRIGGER_CONDITIONS = 10
GROUP_FIELDS = {"operator", "conditions"}
CONDITION_FIELDS = {"task_type_id", "task_status_ids"}
LEGACY_TRIGGER_FIELDS = ("in_task_type_id", "in_task_status_id")
GUARD_FIELD = "out_only_if_task_status_ids"
OUT_FIELD_TYPES = [out_field_type for out_field_type, _ in CHANGE_TYPES]


def clear_status_automation_cache():
    """
    Remove the memoized list of status automations.
    """
    cache.cache.delete_memoized(get_status_automations)


@cache.memoize_function(120)
def get_status_automations():
    """
    Return all status automations.
    """
    return fields.serialize_models(StatusAutomation.get_all())


def get_status_automation_raw(status_automation_id):
    """
    Return the status automation that has the given ID, as an active record.
    """
    return base_service.get_instance(
        StatusAutomation,
        status_automation_id,
        StatusAutomationNotFoundException,
    )


def guard_status_automation_deletion(status_automation_id):
    """
    Refuse the deletion of a status automation that a project or a project
    template uses. The two link tables have no delete rule. Thus the foreign
    key refuses the deletion with a raw database error.
    """
    if ProjectStatusAutomationLink.query.filter_by(
        status_automation_id=status_automation_id
    ).count():
        raise WrongParameterException("This automation is used in a project.")
    if ProjectTemplateStatusAutomationLink.query.filter_by(
        status_automation_id=status_automation_id
    ).count():
        raise WrongParameterException(
            "This automation is used in a project template."
        )


def get_trigger(automation):
    """
    Return the trigger of the given automation (a dict): its ``in_conditions``.
    If it has none, return the group of its legacy ``in_task_type_id`` and
    ``in_task_status_id``. If these values give no trigger, or if the stored
    trigger is malformed, log a warning and return None.
    """
    group = automation.get("in_conditions")
    if group is None:
        group = build_simple_trigger(
            automation.get("in_task_type_id"),
            automation.get("in_task_status_id"),
        )
        if group is None:
            current_app.logger.warning(
                f"Status automation {automation.get('id')} has no trigger."
            )
        return group
    if _is_well_formed_group(group):
        return group
    current_app.logger.warning(
        f"Status automation {automation.get('id')} has a malformed trigger: "
        f"{group}"
    )
    return None


def is_simple_trigger(group):
    """
    Return True if the given trigger is one condition with one status. This is
    the only trigger that the legacy ``in_task_type_id`` and
    ``in_task_status_id`` can store.
    """
    return (
        len(group["conditions"]) == 1
        and len(group["conditions"][0]["task_status_ids"]) == 1
    )


def normalize_trigger(data, instance=None):
    """
    Complete the payload of a status automation write. On an update,
    ``instance`` is the stored automation (a dict).

    If the payload changes ``in_conditions``, the trigger comes from it.
    Otherwise, it comes from the legacy ``in_task_type_id`` and
    ``in_task_status_id``. On an update, the stored values complete them. If
    both are null next to ``in_conditions``, they are removed. The ids are
    stored in one form. The legacy columns mirror a simple trigger, and are
    null for other triggers. An empty entity type is stored as "asset": the
    runner never fires an automation with an empty entity type. If the write
    changes the trigger, the entity type or the output, it is validated. The
    clients send the full form, and a stored row must stay editable. If the
    write is not valid, raise WrongParameterException.
    """
    if not isinstance(data, dict):
        raise WrongParameterException("A JSON object is expected.")
    _drop_null_legacy_pair(data)
    stored = instance or {}
    _check_out_field_type(data, stored)
    if "entity_type" in data:
        data["entity_type"] = data["entity_type"] or "asset"
    stored_group = None
    if instance is not None:
        stored_group = _normalize_stored_group(get_trigger(instance))
    group, is_group_changed = _get_written_group(data, stored, stored_group)
    if instance is None and group is None:
        raise WrongParameterException(
            "A trigger needs at least one condition."
        )

    stored_guard = _normalize_stored_ids(stored.get(GUARD_FIELD))
    guard = stored_guard
    if GUARD_FIELD in data:
        guard = _normalize_ids(data[GUARD_FIELD] or [], "Task status")

    is_output_changed = (
        _is_field_changed(data, stored, "entity_type", _to_entity_type)
        or _is_field_changed(data, stored, "out_field_type", _to_text)
        or _is_field_changed(data, stored, "out_task_type_id", _to_id)
        or set(guard) != set(stored_guard)
    )
    if instance is None or is_group_changed or is_output_changed:
        _validate_automation(
            group,
            _to_entity_type(
                data.get("entity_type", stored.get("entity_type")) or "asset"
            ),
            data.get("out_field_type", stored.get("out_field_type"))
            or "status",
            data.get("out_task_type_id", stored.get("out_task_type_id")),
            guard,
        )

    if group is not None:
        data["in_conditions"] = group
        data["in_task_type_id"] = None
        data["in_task_status_id"] = None
        if is_simple_trigger(group):
            condition = group["conditions"][0]
            data["in_task_type_id"] = condition["task_type_id"]
            data["in_task_status_id"] = condition["task_status_ids"][0]
    if GUARD_FIELD in data:
        data[GUARD_FIELD] = guard or None
    return data


def get_automations_using_task_type(task_type_id):
    """
    Return the status automations, archived ones included, that read or write
    the given task type. Read from the table, not from the memoized list,
    because the answer guards a deletion.
    """
    task_type_id = str(task_type_id)
    return [
        automation.serialize()
        for automation in StatusAutomation.query.all()
        if task_type_id in _get_used_task_type_ids(automation)
    ]


def get_automations_using_task_status(task_status_id):
    """
    Return the status automations, archived ones included, that read or write
    the given task status.
    """
    task_status_id = str(task_status_id)
    return [
        automation.serialize()
        for automation in StatusAutomation.query.all()
        if task_status_id in _get_used_task_status_ids(automation)
    ]


def guard_task_type_deletion(task_type):
    """
    Refuse the deletion of a task type that a status automation uses. A removal
    of the task type from the automation changes when the automation fires.
    Thus the admin must do it.
    """
    automations = get_automations_using_task_type(task_type["id"])
    if automations:
        raise WrongParameterException(
            _build_usage_message(f"Task type {task_type['name']}", automations)
        )


def guard_task_status_deletion(task_status):
    """
    Refuse the deletion of a task status that a status automation uses.
    """
    automations = get_automations_using_task_status(task_status["id"])
    if automations:
        raise WrongParameterException(
            _build_usage_message(
                f"Task status {task_status['name']}", automations
            )
        )


def _check_out_field_type(data, stored):
    """
    Refuse an output type that is not in the choices of the column. If the
    value is the same as the stored value, accept it: older releases stored an
    empty value.
    """
    out_field_type = data.get("out_field_type", "status")
    if out_field_type not in OUT_FIELD_TYPES and out_field_type != stored.get(
        "out_field_type", "status"
    ):
        raise WrongParameterException(
            "out_field_type must be 'status' or 'ready_for'."
        )


def _drop_null_legacy_pair(data):
    """
    Remove the legacy pair that a client sends as null next to
    ``in_conditions``, which gives the trigger. Thus the pair does not change
    the trigger and does not clear the mirror. A single null stays a legacy
    value. It is not read next to a new trigger. If it changes the stored pair,
    it is refused.
    """
    if data.get("in_conditions") is not None and all(
        field in data and data[field] is None
        for field in LEGACY_TRIGGER_FIELDS
    ):
        for field in LEGACY_TRIGGER_FIELDS:
            del data[field]


def _get_written_group(data, stored, stored_group):
    """
    Return the trigger that the write leaves on the automation, and whether the
    write changes it. If the write changes the trigger, use ``in_conditions``.
    Else, if the write changes the mirror, use the legacy pair. A trigger that
    is the same as the stored trigger changes nothing, even if it is malformed.
    """
    written_group = data.get("in_conditions")
    if written_group is not None and written_group != stored.get(
        "in_conditions"
    ):
        group = _normalize_group(written_group)
        if _get_group_key(group) != _get_group_key(stored_group):
            return group, True

    legacy_pair = _get_written_legacy_pair(data, stored)
    if legacy_pair is None:
        return stored_group, False
    if stored_group is not None and not is_simple_trigger(stored_group):
        raise WrongParameterException(
            "This automation has several trigger conditions: update it "
            "through in_conditions."
        )
    if all(value is None for value in legacy_pair):
        raise WrongParameterException(
            "A trigger needs at least one condition."
        )
    if any(value is None for value in legacy_pair):
        raise WrongParameterException(
            "in_task_type_id and in_task_status_id go together."
        )
    return _normalize_group(build_simple_trigger(*legacy_pair)), True


def _get_written_legacy_pair(data, stored):
    """
    Return the legacy task type and status that a write sets. On an update, the
    stored values complete them. If the write does not change them, return
    None.
    """
    if not any(field in data for field in LEGACY_TRIGGER_FIELDS):
        return None
    pair = tuple(
        data.get(field, stored.get(field)) for field in LEGACY_TRIGGER_FIELDS
    )
    is_unchanged = all(
        _to_id(value) == _to_id(stored.get(field))
        for value, field in zip(pair, LEGACY_TRIGGER_FIELDS)
    )
    if stored and is_unchanged:
        return None
    return pair


def _normalize_group(group):
    """
    Check the shape of a trigger. Return it with its ids in one form and its
    status sets without duplicates. For now, nested groups are refused.
    """
    if not isinstance(group, dict):
        raise WrongParameterException(
            "Trigger operator must be 'and' or 'or'."
        )
    _check_known_fields(group, GROUP_FIELDS, "a trigger")
    if group.get("operator") not in TRIGGER_OPERATORS:
        raise WrongParameterException(
            "Trigger operator must be 'and' or 'or'."
        )
    conditions = group.get("conditions")
    if not isinstance(conditions, list) or len(conditions) == 0:
        raise WrongParameterException(
            "A trigger needs at least one condition."
        )
    if len(conditions) > MAX_TRIGGER_CONDITIONS:
        raise WrongParameterException(
            f"A trigger accepts at most {MAX_TRIGGER_CONDITIONS} conditions."
        )
    return {
        "operator": group["operator"],
        "conditions": [
            _normalize_condition(condition) for condition in conditions
        ],
    }


def _normalize_condition(condition):
    if isinstance(condition, dict) and (
        "operator" in condition or "conditions" in condition
    ):
        raise WrongParameterException(
            "Condition groups are not supported yet."
        )
    if not isinstance(condition, dict):
        raise WrongParameterException(
            "A trigger condition needs a task type and statuses."
        )
    _check_known_fields(condition, CONDITION_FIELDS, "a trigger condition")
    task_status_ids = condition.get("task_status_ids")
    if not isinstance(task_status_ids, list) or len(task_status_ids) == 0:
        raise WrongParameterException("A condition needs at least one status.")
    return {
        "task_type_id": _normalize_id(
            condition.get("task_type_id"), "Task type"
        ),
        "task_status_ids": _normalize_ids(task_status_ids, "Task status"),
    }


def _check_known_fields(node, known_fields, place):
    unknown_fields = sorted(set(node) - known_fields)
    if unknown_fields:
        raise WrongParameterException(
            f"Unknown field '{unknown_fields[0]}' in {place}."
        )


def _normalize_ids(values, label):
    if not isinstance(values, list):
        raise WrongParameterException(f"{label} {values} does not exist.")
    ids = []
    for value in values:
        normalized_id = _normalize_id(value, label)
        if normalized_id not in ids:
            ids.append(normalized_id)
    return ids


def _normalize_id(value, label):
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        raise WrongParameterException(f"{label} {value} does not exist.")


def _normalize_stored_group(group):
    """
    Return the stored trigger in the form of a written trigger, so that the
    payload of a round trip compares equal. A value that does not normalize
    counts as no trigger. Only a sync or a direct write can store such a value.
    If a write does not send a new trigger, this value does not change.
    """
    if group is None:
        return None
    try:
        return _normalize_group(group)
    except WrongParameterException:
        return None


def _normalize_stored_ids(values):
    try:
        return _normalize_ids(values or [], "Task status")
    except WrongParameterException:
        return []


def _get_group_key(group):
    """
    Return the data that makes two triggers different:
    - the operator,
    - the order of the conditions (the first one gives the imported revision).

    The order of the statuses is not in this data.
    """
    if group is None:
        return None
    return (
        group["operator"],
        tuple(
            (
                condition["task_type_id"],
                frozenset(condition["task_status_ids"]),
            )
            for condition in group["conditions"]
        ),
    )


def _is_field_changed(data, stored, field, to_key):
    return field in data and to_key(data[field]) != to_key(stored.get(field))


def _to_text(value):
    return None if value is None else str(value)


def _to_id(value):
    """
    Return the given ID in its stored form, so that the comparison of ids
    ignores their case. If the value is not an id, return it as text.
    """
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        return _to_text(value)


def _to_entity_type(value):
    """
    Return the given entity type in lowercase: older clients wrote "Asset".
    """
    return None if value is None else str(value).lower()


def _validate_automation(
    group, entity_type, out_field_type, out_task_type_id, guard
):
    for_entity = _get_for_entity(entity_type)
    if out_field_type == "ready_for" and for_entity != "Asset":
        raise WrongParameterException(
            "The ready for output applies to assets only."
        )
    if out_field_type == "ready_for" and guard:
        raise WrongParameterException(
            "The target status guard applies to status changes only."
        )
    if group is not None:
        _validate_conditions(
            group, for_entity, out_field_type, out_task_type_id
        )
    for task_status_id in guard:
        _check_task_status_exists(task_status_id)


def _get_for_entity(entity_type):
    """
    Return the for_entity of the task types that an automation on the given
    entity type uses. Old rows can name an asset type ("props") and not
    "asset". These rows use the asset task types.
    """
    if entity_type == "asset" or _is_asset_type_name(entity_type):
        return "Asset"
    return entity_type.capitalize()


def _is_asset_type_name(name):
    entity_type = EntityType.query.filter(
        func.lower(EntityType.name) == name
    ).first()
    return entity_type is not None and entity_types_service.is_asset_type(
        entity_type
    )


def _validate_conditions(group, for_entity, out_field_type, out_task_type_id):
    task_type_ids = set()
    for condition in group["conditions"]:
        task_type_id = condition["task_type_id"]
        task_type = TaskType.get(task_type_id)
        if task_type is None:
            raise WrongParameterException(
                f"Task type {task_type_id} does not exist."
            )
        # A task type older than for_entity has null in this column. Null means
        # "Asset", as get_project_task_types_raw reads it.
        if (task_type.for_entity or "Asset") != for_entity:
            raise WrongParameterException(
                f"Task type {task_type.name} is not a task type of "
                f"{for_entity.lower()}s."
            )
        if task_type_id in task_type_ids:
            raise WrongParameterException(
                f"Task type {task_type.name} appears in two conditions: "
                "merge their statuses into one."
            )
        task_type_ids.add(task_type_id)
        if out_field_type == "status" and task_type_id == _to_id(
            out_task_type_id
        ):
            raise WrongParameterException(
                f"The applied task type {task_type.name} cannot be a "
                "condition."
            )
        for task_status_id in condition["task_status_ids"]:
            _check_task_status_exists(task_status_id)


def _check_task_status_exists(task_status_id):
    if TaskStatus.get(task_status_id) is None:
        raise WrongParameterException(
            f"Task status {task_status_id} does not exist."
        )


def _is_well_formed_group(group):
    return (
        isinstance(group, dict)
        and group.get("operator") in TRIGGER_OPERATORS
        and isinstance(group.get("conditions"), list)
        and len(group["conditions"]) > 0
        and all(
            isinstance(condition, dict)
            and isinstance(condition.get("task_type_id"), str)
            and isinstance(condition.get("task_status_ids"), list)
            and all(
                isinstance(task_status_id, str)
                for task_status_id in condition["task_status_ids"]
            )
            for condition in group["conditions"]
        )
    )


def _get_conditions(group):
    """
    Return the conditions of a stored trigger. Read them leniently: the
    deletion guards must see all ids, also in a malformed trigger.
    """
    if not isinstance(group, dict) or not isinstance(
        group.get("conditions"), list
    ):
        return []
    return [
        condition
        for condition in group["conditions"]
        if isinstance(condition, dict)
    ]


def _get_used_task_type_ids(automation):
    task_type_ids = [
        automation.in_task_type_id,
        automation.out_task_type_id,
        *(
            condition.get("task_type_id")
            for condition in _get_conditions(automation.in_conditions)
        ),
    ]
    return {
        str(task_type_id)
        for task_type_id in task_type_ids
        if task_type_id is not None
    }


def _get_used_task_status_ids(automation):
    task_status_ids = [
        automation.in_task_status_id,
        automation.out_task_status_id,
    ]
    for condition in _get_conditions(automation.in_conditions):
        if isinstance(condition.get("task_status_ids"), list):
            task_status_ids.extend(condition["task_status_ids"])
    if isinstance(automation.out_only_if_task_status_ids, list):
        task_status_ids.extend(automation.out_only_if_task_status_ids)
    return {
        str(task_status_id)
        for task_status_id in task_status_ids
        if task_status_id is not None
    }


def _build_usage_message(label, automations):
    count = len(automations)
    archived = len([a for a in automations if a["archived"]])
    noun = "status automation" if count == 1 else "status automations"
    detail = f" ({archived} archived)" if archived else ""
    them = "that automation" if count == 1 else "them"
    return (
        f"{label} is used by {count} {noun}{detail}. "
        f"Remove it from {them} first."
    )
