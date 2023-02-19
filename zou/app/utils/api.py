from flask import Blueprint


def create_blueprint_for_api(blueprint_name, route_tuples):
    """
    Creates a Flask Blueprint object based on given informations.

    Each blueprint is described by its name. Each tuple is composed of a
    route and the related MethodView.
    """
    blueprint = Blueprint(blueprint_name, blueprint_name)
    for route_tuple in route_tuples:
        (path, method_view) = route_tuple
        view = method_view.as_view(method_view.__name__)
        blueprint.add_url_rule(path, view_func=view)

    return blueprint
