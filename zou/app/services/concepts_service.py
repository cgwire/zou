from sqlalchemy.exc import StatementError

from zou.app.utils import (
    cache,
    events,
    fields,
    query as query_utils,
)

from zou.app.models.entity import (
    Entity,
    EntityLink,
    EntityVersion,
    EntityConceptLink,
)
from zou.app.models.project import Project
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task
from zou.app.models.task import assignees_table

from zou.app.services import (
    deletion_service,
    entities_service,
    notifications_service,
    user_service,
)
from zou.app.services.exception import (
    ConceptNotFoundException,
    WrongIdFormatException,
    EntityNotFoundException,
)


def clear_concept_cache(concept_id):
    cache.cache.delete_memoized(get_concept, concept_id)
    cache.cache.delete_memoized(get_concept_with_relations, concept_id)
    cache.cache.delete_memoized(get_full_concept, concept_id)


@cache.memoize_function(1200)
def get_concept_type():
    return entities_service.get_temporal_entity_type_by_name("Concept")


def get_concept_raw(concept_id):
    """
    Return given concept as an active record.
    """
    concept_type = get_concept_type()
    try:
        concept = Entity.get_by(
            entity_type_id=concept_type["id"], id=concept_id
        )
    except StatementError:
        raise ConceptNotFoundException

    if concept is None:
        raise ConceptNotFoundException

    return concept


@cache.memoize_function(120)
def get_concept_with_relations(concept_id):
    """
    Return given concept as a dictionary.
    """
    return get_concept_raw(concept_id).serialize(
        obj_type="Concept", relations=True
    )


@cache.memoize_function(120)
def get_concept(concept_id):
    """
    Return given concept as a dictionary.
    """
    return get_concept_raw(concept_id).serialize(obj_type="Concept")


@cache.memoize_function(120)
def get_full_concept(concept_id):
    """
    Return given concept as a dictionary with extra data like project.
    """
    concepts = get_concepts_and_tasks({"id": concept_id})
    if len(concepts) > 0:
        concept = concepts[0]
        concept.update(get_concept_with_relations(concept_id))
        return concept
    else:
        raise ConceptNotFoundException


def remove_concept(concept_id, force=False):
    """
    Remove given concept from database. If it has tasks linked to it, it marks
    the concept as canceled. Deletion can be forced.
    """
    concept = get_concept_raw(concept_id)
    is_tasks_related = Task.query.filter_by(entity_id=concept_id).count() > 0

    if is_tasks_related and not force:
        concept.update({"canceled": True})
        clear_concept_cache(concept_id)
        events.emit(
            "concept:update",
            {"concept_id": concept_id},
            project_id=str(concept.project_id),
        )
    else:
        from zou.app.services import tasks_service

        tasks = Task.query.filter_by(entity_id=concept_id).all()
        for task in tasks:
            deletion_service.remove_task(task.id, force=True)
            tasks_service.clear_task_cache(str(task.id))

        EntityVersion.delete_all_by(entity_id=concept_id)
        Subscription.delete_all_by(entity_id=concept_id)
        EntityLink.delete_all_by(entity_in_id=concept_id)
        EntityLink.delete_all_by(entity_out_id=concept_id)
        EntityConceptLink.delete_all_by(entity_in_id=concept_id)
        EntityConceptLink.delete_all_by(entity_out_id=concept_id)

        concept.delete()
        events.emit(
            "concept:delete",
            {"concept_id": concept_id},
            project_id=str(concept.project_id),
        )
        clear_concept_cache(concept_id)

    deleted_concept = concept.serialize(obj_type="Concept")
    return deleted_concept


def get_concepts(criterions={}):
    """
    Get all concepts for given criterions.
    """
    concept_type = get_concept_type()
    criterions["entity_type_id"] = concept_type["id"]
    is_only_assignation = "assigned_to" in criterions
    if is_only_assignation:
        del criterions["assigned_to"]

    query = Entity.query
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
    query = (
        query.join(Project, Project.id == Entity.project_id)
        .add_columns(Project.name)
        .order_by(Entity.name)
    )

    if is_only_assignation:
        query = query.outerjoin(Task, Task.entity_id == Entity.id)
        query = query.filter(user_service.build_assignee_filter())

    try:
        data = query.all()
    except StatementError:  # Occurs when an id is not properly formatted
        raise WrongIdFormatException

    concepts = []
    for concept_model, project_name in data:
        concept = concept_model.serialize(obj_type="Concept")
        concept["project_name"] = project_name
        concepts.append(concept)

    return concepts


def get_concepts_and_tasks(criterions={}):
    """
    Get all concepts for given criterions with related tasks for each concept.
    """
    concept_type = get_concept_type()
    concept_map = {}
    task_map = {}
    subscription_map = notifications_service.get_subscriptions_for_user(
        criterions.get("project_id", None), get_concept_type()["id"]
    )

    query = (
        Entity.query.join(Project, Project.id == Entity.project_id)
        .outerjoin(Task, Task.entity_id == Entity.id)
        .outerjoin(assignees_table)
        .add_columns(
            Task.id,
            Task.task_type_id,
            Task.task_status_id,
            Task.priority,
            Task.estimation,
            Task.duration,
            Task.retake_count,
            Task.real_start_date,
            Task.end_date,
            Task.start_date,
            Task.due_date,
            Task.last_comment_date,
            Task.nb_assets_ready,
            assignees_table.columns.person,
            Project.id,
            Project.name,
        )
        .filter(Entity.entity_type_id == concept_type["id"])
    )
    if "id" in criterions:
        query = query.filter(Entity.id == criterions["id"])

    if "project_id" in criterions:
        query = query.filter(Entity.project_id == criterions["project_id"])

    if "assigned_to" in criterions:
        query = query.filter(user_service.build_assignee_filter())
        del criterions["assigned_to"]

    query_result = query.all()

    for (
        concept,
        task_id,
        task_type_id,
        task_status_id,
        task_priority,
        task_estimation,
        task_duration,
        task_retake_count,
        task_real_start_date,
        task_end_date,
        task_start_date,
        task_due_date,
        task_last_comment_date,
        task_nb_assets_ready,
        person_id,
        project_id,
        project_name,
    ) in query_result:
        concept_id = str(concept.id)

        if concept_id not in concept_map:
            data = fields.serialize_value(concept.data or {})

            concept_map[concept_id] = fields.serialize_dict(
                {
                    "canceled": concept.canceled,
                    "data": data,
                    "description": concept.description,
                    "entity_type_id": concept.entity_type_id,
                    "fps": data.get("fps", None),
                    "frame_in": data.get("frame_in", None),
                    "frame_out": data.get("frame_out", None),
                    "id": concept.id,
                    "name": concept.name,
                    "nb_frames": concept.nb_frames,
                    "parent_id": concept.parent_id,
                    "preview_file_id": concept.preview_file_id or None,
                    "project_id": project_id,
                    "project_name": project_name,
                    "source_id": concept.source_id,
                    "nb_entities_out": concept.nb_entities_out,
                    "is_casting_standby": concept.is_casting_standby,
                    "tasks": [],
                    "entity_concept_links": concept.entity_concept_links,
                    "type": "Concept",
                    "updated_at": concept.updated_at,
                    "created_at": concept.created_at,
                    "created_by": concept.created_by,
                }
            )

        if task_id is not None:
            task_id = str(task_id)
            if task_id not in task_map:
                task_dict = fields.serialize_dict(
                    {
                        "id": task_id,
                        "duration": task_duration,
                        "due_date": task_due_date,
                        "end_date": task_end_date,
                        "entity_id": concept_id,
                        "estimation": task_estimation,
                        "is_subscribed": subscription_map.get(task_id, False),
                        "last_comment_date": task_last_comment_date,
                        "nb_assets_ready": task_nb_assets_ready,
                        "priority": task_priority or 0,
                        "real_start_date": task_real_start_date,
                        "retake_count": task_retake_count,
                        "start_date": task_start_date,
                        "task_status_id": task_status_id,
                        "task_type_id": task_type_id,
                        "assignees": [],
                    }
                )
                task_map[task_id] = task_dict
                concept_dict = concept_map[concept_id]
                concept_dict["tasks"].append(task_dict)

            if person_id:
                task_map[task_id]["assignees"].append(str(person_id))

    return list(concept_map.values())


def get_concepts_for_project(project_id, only_assigned=False):
    """
    Retrieve all concepts related to given project.
    """
    return entities_service.get_entities_for_project(
        project_id,
        get_concept_type()["id"],
        "Concept",
        only_assigned=only_assigned,
    )


def create_concept(
    project_id,
    name,
    data={},
    description=None,
    entity_concept_links=[],
    created_by=None,
):
    """
    Create concept for given project.
    """
    concept_type = get_concept_type()

    concept = Entity.get_by(
        entity_type_id=concept_type["id"],
        project_id=project_id,
        name=name,
    )

    if concept is None:
        try:
            entity_concept_links = [
                entity_concept_link
                for entity_concept_link_id in entity_concept_links
                if (entity_concept_link := Entity.get(entity_concept_link_id))
                is not None
            ]
        except StatementError:
            raise EntityNotFoundException()
        concept = Entity.create(
            entity_type_id=concept_type["id"],
            project_id=project_id,
            name=name,
            data=data,
            description=description,
            entity_concept_links=entity_concept_links,
            created_by=created_by,
        )

        events.emit(
            "concept:new",
            {
                "concept_id": concept.id,
            },
            project_id=project_id,
        )

    return concept.serialize(obj_type="Concept")


def is_concept(entity):
    """
    Returns True if given entity has 'Concept' as entity type
    """
    concept_type = get_concept_type()
    return str(entity["entity_type_id"]) == concept_type["id"]
