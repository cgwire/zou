from flask.views import MethodView


def configure_api_from_blueprint(blueprint, route_tuples, decorators=None):
    """
    Register route tuples (path, resource class) on the given blueprint.
    Resources are Flask MethodView classes; JSON serialization of dict and
    list return values is handled natively by Flask through the app JSON
    provider (orjson).

    A resource class may appear in several tuples: extra paths are
    registered as aliases on the same view (used to keep deprecated
    routes working after a rename).
    """
    view_funcs = {}
    for path, resource in route_tuples:
        view_func = view_funcs.get(resource)
        if view_func is None:
            view_func = resource.as_view(resource.__name__)
            for decorator in decorators or []:
                view_func = decorator(view_func)
            view_funcs[resource] = view_func
        blueprint.add_url_rule(path, view_func=view_func)
    return blueprint
