def configure_api_from_blueprint(blueprint, route_tuples, decorators=None):
    """
    Register the route tuples (path, resource class) on the given
    blueprint. The resources are Flask MethodView classes. Flask serializes
    the dict and list return values to JSON natively, through the JSON
    provider of the app (orjson).

    A resource class can be in more than one tuple: the other paths become
    aliases on the same view. Zou uses this to keep the deprecated routes
    available after a rename.
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
