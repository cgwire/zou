from . import routes
from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint


def init_plugin(app, manifest):
    """
    Init the plugin.
    """
    app.logger.info("Loading plugin...")
    routes_tuples = [(f"/hello-world", routes.HelloWorld)]

    blueprint = Blueprint(manifest["id"], manifest["id"])
    configure_api_from_blueprint(blueprint, routes_tuples)
    app.register_blueprint(blueprint, url_prefix=f"/{manifest['id']}")


def pre_install(manifest):
    """
    Pre install the plugin.
    """


def post_install(manifest):
    """
    Post install the plugin.
    """


def pre_uninstall(manifest):
    """
    Pre uninstall the plugin.
    """


def post_uninstall(manifest):
    """
    Post uninstall the plugin.
    """
