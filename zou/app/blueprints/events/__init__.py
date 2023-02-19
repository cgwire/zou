from zou.app.utils.api import create_blueprint_for_api

from .resources import EventsResource, LoginLogsResource

routes = [
    ("/data/events/last", EventsResource),
    ("/data/events/login-logs/last", LoginLogsResource),
]

blueprint = create_blueprint_for_api("events", routes)
