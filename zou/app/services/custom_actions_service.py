from zou.app.models.custom_action import CustomAction
from zou.app.utils import cache, fields


def clear_custom_action_cache():
    cache.cache.delete_memoized(get_custom_actions)


@cache.memoize_function(120)
def get_custom_actions():
    return fields.serialize_models(CustomAction.get_all())
