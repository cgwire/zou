from zou.app.models.status_automation import StatusAutomation
from zou.app.utils import cache, fields


def clear_status_automation_cache():
    cache.cache.delete_memoized(get_status_automations)


@cache.memoize_function(120)
def get_status_automations():
    return fields.serialize_models(StatusAutomation.get_all())
