from sqlalchemy.exc import StatementError

from zou.app.utils import events


def get_instance(model, instance_id, exception):
    """
    Return the instance of the given model that has the given ID. If it does
    not exist, raise the given exception. If the ID is not a valid UUID, raise
    the same exception: the driver rejects it with a StatementError, and
    callers must not have to tell it apart from a missing row.
    """
    if instance_id is None:
        raise exception()

    try:
        instance = model.get(instance_id)
    except StatementError:
        raise exception()

    if instance is None:
        raise exception()

    return instance


def get_typed_instance(model, instance_id, entity_type_id, exception):
    """
    Do the same as get_instance for a polymorphic model, where the ID alone
    does not tell what the row is. The type check makes sure that an ID of the
    wrong kind raises the given exception and does not give the wrong object.
    """
    try:
        instance = model.get_by(id=instance_id, entity_type_id=entity_type_id)
    except StatementError:
        raise exception()

    if instance is None:
        raise exception()

    return instance


def get_or_create_instance_by_name(model, **kwargs):
    """
    Return the instance of the given model that has the given name. If it does
    not exist, create an instance of this model from the given keyword
    arguments and emit a `<table>:new` event. Return the instance as a dict.
    """
    instance = model.get_by(name=kwargs["name"])
    if instance is None:
        instance = model.create(**kwargs)
        project_id = getattr(instance, "project_id", None)
        if project_id is not None:
            project_id = str(project_id)
        events.emit(
            f"{model.__tablename__}:new",
            {f"{model.__tablename__}_id": instance.id},
            project_id=project_id,
        )
    return instance.serialize()


def get_model_map_from_array(models):
    """
    Return a map made from the given list of models. The map keys are the
    model IDs and the values are the models. Use it to find a model from its
    ID.
    """
    return {model["id"]: model for model in models}
