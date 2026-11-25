from sqlalchemy.exc import IntegrityError, StatementError

from zou.app.models.entity import Entity
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task
from zou.app.services import (
    entity_types_service,
    persons_service,
)
from zou.app.utils import cache, fields


def _get_subscription_raw(**criterions):
    """
    Return the subscription that matches the given criterions as an active
    record. If one of the given IDs is not valid, return None.
    """
    try:
        return Subscription.get_by(**criterions)
    except StatementError:
        return None


@cache.memoize_function(120)
def is_person_subscribed(person_id, task_id):
    """
    Return True if the user subscribed to the notifications of the given
    task.
    """
    subscription = Subscription.get_by(task_id=task_id, person_id=person_id)
    return subscription is not None


def get_task_subscriptions(task):
    """
    Return all the notification subscriptions of the given task, as active
    records.
    """
    return Subscription.get_all_by(task_id=task["id"])


def get_sequence_subscriptions_for_task(task):
    """
    Return all the sequence subscriptions for the given task, as active
    records. The list is empty unless the task is for a shot whose sequence
    has a subscription.
    """
    sequence_subscriptions = []
    entity = Entity.get(task["entity_id"])
    if entity is not None and entity.parent_id is not None:
        sequence_subscriptions = Subscription.get_all_by(
            task_type_id=task["task_type_id"], entity_id=entity.parent_id
        )
    return sequence_subscriptions


def get_task_subscription_raw(person_id, task_id):
    """
    Return the subscription that matches the given person and task.
    """
    return _get_subscription_raw(person_id=person_id, task_id=task_id)


def has_task_subscription(person_id, task_id):
    """
    Return True if a subscription exists for this person and this task.
    """
    subscription = get_task_subscription_raw(person_id, task_id)
    return subscription is not None


def subscribe_to_task(person_id, task_id):
    """
    Add a subscription entry for the given person and task.
    """
    subscription = get_task_subscription_raw(person_id, task_id)
    if subscription is None:
        try:
            subscription = Subscription.create(
                person_id=person_id, task_id=task_id
            )
        except IntegrityError:
            # A concurrent request subscribed the same person between the read
            # above and this insert. subscription_task_uc rejects this insert.
            # This request then returns the row of the other request.
            subscription = get_task_subscription_raw(person_id, task_id)
            if subscription is None:
                raise
    cache.cache.delete_memoized(is_person_subscribed, person_id, task_id)
    return subscription.serialize()


def unsubscribe_from_task(person_id, task_id):
    """
    Remove the subscription entry for the given person and task.
    """
    subscription = get_task_subscription_raw(person_id, task_id)
    if subscription is None:
        return {}
    subscription.delete()
    cache.cache.delete_memoized(is_person_subscribed, person_id, task_id)
    return subscription.serialize()


def get_sequence_subscription_raw(person_id, sequence_id, task_type_id):
    """
    Return the subscription that matches the given person, sequence and task
    type.
    """
    return _get_subscription_raw(
        person_id=person_id,
        entity_id=sequence_id,
        task_type_id=task_type_id,
    )


def has_sequence_subscription(person_id, sequence_id, task_type_id):
    """
    Return True if a subscription exists for this person, sequence and task
    type.
    """
    subscription = get_sequence_subscription_raw(
        person_id, sequence_id, task_type_id
    )
    return subscription is not None


def subscribe_to_sequence(person_id, sequence_id, task_type_id):
    """
    Add a subscription entry for the given person, sequence and task type.
    """
    subscription = get_sequence_subscription_raw(
        person_id, sequence_id, task_type_id
    )
    if subscription is None:
        subscription = Subscription.create(
            person_id=person_id,
            entity_id=sequence_id,
            task_type_id=task_type_id,
        )
    return subscription.serialize()


def unsubscribe_from_sequence(person_id, sequence_id, task_type_id):
    """
    Remove the subscription entry for the given person, sequence and task
    type.
    """
    subscription = get_sequence_subscription_raw(
        person_id, sequence_id, task_type_id
    )
    if subscription is None:
        return {}
    subscription.delete()
    return subscription.serialize()


def get_subscriptions_for_project(project_id):
    """
    Return all the subscriptions for the given project.
    """
    subscriptions = Subscription.query.join(Task).filter(
        Task.project_id == project_id
    )
    return fields.serialize_list(subscriptions)


def get_subscriptions_for_user(project_id, entity_type_id=None):
    """
    Return a map of the task IDs the current user subscribed to in the given
    project. Do not memoize this function. The result depends on the caller.
    """
    if project_id is None:
        return {}

    user_id = persons_service.get_current_user()["id"]
    query = (
        Subscription.query.join(Task)
        .join(Entity, Task.entity_id == Entity.id)
        .filter(Subscription.person_id == user_id)
        .filter(Task.project_id == project_id)
    )
    if entity_type_id is not None:
        query = query.filter(Entity.entity_type_id == entity_type_id)
    else:
        # If no type is given, keep the asset types that the caller can see.
        query = query.filter(entity_types_service.build_asset_type_filter())

    return {str(subscription.task_id): True for subscription in query.all()}
