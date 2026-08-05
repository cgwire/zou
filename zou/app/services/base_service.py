from sqlalchemy.exc import StatementError
from zou.app.utils import events


def get_instance(model, instance_id, exception):
    """
    Get instance of any model from its ID and raise given exception if not
    found. An ID that is not a valid UUID raises the same exception: the
    driver rejects it with a StatementError, which callers must not have to
    tell apart from a missing row.
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


def get_or_create_instance_by_name(model, **kwargs):
    """
    Get instance of any model by name. If it doesn't exist it creates a new
    instance of this model from positional arguments dict.
    """
    instance = model.get_by(name=kwargs["name"])
    if instance is None:
        instance = model.create(**kwargs)
        project_id = getattr(instance, "project_id", None)
        events.emit(
            f"{model.__tablename__}:new",
            {f"{model.__tablename__}_id": instance.id},
            project_id=str(project_id),
        )
    return instance.serialize()


def get_model_map_from_array(models):
    """
    Return a map matching based on given model list. The map keys are the model
    IDs and the values are the models. It's convenient to find a model by its
    ID.
    """
    return {model["id"]: model for model in models}
