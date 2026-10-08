from sqlalchemy.exc import IntegrityError, StatementError

from zou.app.models.project import Project
from zou.app.models.entity import Entity
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task
from zou.app.services import (
    persons_service,
    entity_types_service,
)
from zou.app.utils import fields, cache


def _get_subscription_raw(**criterions):
    """
    Return the subscription matching given criterions as an active record,
    or None when one of the given ids is malformed.
    """
    try:
        return Subscription.get_by(**criterions)
    except StatementError:
        return None


@cache.memoize_function(120)
def is_person_subscribed(person_id, task_id):
    """
    Returns true if the user subscribed to given task notifications.
    """
    subscription = Subscription.get_by(task_id=task_id, person_id=person_id)
    return subscription is not None


def get_task_subscriptions(task):
    """
    Return all notification subscriptions related to given task.
    """
    return Subscription.get_all_by(task_id=task["id"])


def get_sequence_subscriptions_for_task(task):
    """
    Return all sequence subscriptions for given task. It returns something only
    if the task is related to a shot of which the sequence has a subscription.
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
    Return subscription matching given person and task.
    """
    return _get_subscription_raw(person_id=person_id, task_id=task_id)


def has_task_subscription(person_id, task_id):
    """
    Return true if a subscription exists for this person and this task.
    """
    subscription = get_task_subscription_raw(person_id, task_id)
    return subscription is not None


def subscribe_to_task(person_id, task_id):
    """
    Add a subscription entry for given person and task.
    """
    subscription = get_task_subscription_raw(person_id, task_id)
    if subscription is None:
        try:
            subscription = Subscription.create(
                person_id=person_id, task_id=task_id
            )
        except IntegrityError:
            # A concurrent request subscribed the same person between the
            # read above and this insert: subscription_task_uc rejects the
            # loser, which returns the winning row.
            subscription = get_task_subscription_raw(person_id, task_id)
            if subscription is None:
                raise
    cache.cache.delete_memoized(is_person_subscribed, person_id, task_id)
    return subscription.serialize()


def unsubscribe_from_task(person_id, task_id):
    """
    Remove subscription entry for given person and task.
    """
    subscription = get_task_subscription_raw(person_id, task_id)
    if subscription is None:
        return {}
    subscription.delete()
    cache.cache.delete_memoized(is_person_subscribed, person_id, task_id)
    return subscription.serialize()


def get_sequence_subscription_raw(person_id, sequence_id, task_type_id):
    """
    Return subscription matching given person, sequence and task type.
    """
    return _get_subscription_raw(
        person_id=person_id,
        entity_id=sequence_id,
        task_type_id=task_type_id,
    )


def has_sequence_subscription(person_id, sequence_id, task_type_id):
    """
    Return true if a subscription exists for this person, sequence and task
    type.
    """
    subscription = get_sequence_subscription_raw(
        person_id, sequence_id, task_type_id
    )
    return subscription is not None


def subscribe_to_sequence(person_id, sequence_id, task_type_id):
    """
    Add a subscription entry for given person, sequence and task type.
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
    Remove subscription entry for given person, sequence and task type.
    """
    subscription = get_sequence_subscription_raw(
        person_id, sequence_id, task_type_id
    )
    if subscription is None:
        return {}
    subscription.delete()
    return subscription.serialize()


def get_all_sequence_subscriptions(person_id, project_id, task_type_id):
    """
    Return list of sequence ids for which given person has subscribed for
    given project and task type.
    """
    subscriptions = (
        Subscription.query.join(Entity)
        .join(Project)
        .filter(Project.id == project_id)
        .filter(Subscription.task_type_id == task_type_id)
        .filter(Subscription.person_id == person_id)
        .all()
    )

    return fields.serialize_value(
        [subscription.entity_id for subscription in subscriptions]
    )


def get_subscriptions_for_project(project_id):
    """
    Return all subscriptions for given project.
    """
    subscriptions = Subscription.query.join(Task).filter(
        Task.project_id == project_id
    )
    return fields.serialize_list(subscriptions)


def get_subscriptions_for_user(project_id, entity_type_id=None):
    """
    Return a map of the task ids the current user subscribed to in given
    project. Scoped to the caller, so it must never be memoized.
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
        # Without an explicit type, keep the asset types the caller may see.
        query = query.filter(entity_types_service.build_asset_type_filter())

    return {str(subscription.task_id): True for subscription in query.all()}
