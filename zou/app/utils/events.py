import logging
from collections import OrderedDict

from flask import current_app
from flask_jwt_extended import current_user

from zou.app.models.event import ApiEvent
from zou.app.stores import publisher_store
from zou.app.utils import fields

logger = logging.getLogger(__name__)


handlers = {}

# The hooks get the event name after the module stores the event. Thus,
# a service reacts to the write path, and this module does not import the
# services: events_service registers here the invalidation of its name
# list.
save_hooks = []

publisher_store.init()


def add_save_hook(hook):
    """
    Run the given callable, with the event name, each time that the module
    stores an event.
    """
    if hook not in save_hooks:
        save_hooks.append(hook)


def register(event, name, handler, app=None):
    """
    Register a listener: link an event name to a handler module. The
    handler module has a function named `handle_event`, which runs when
    the linked event occurs.
    """
    if event not in handlers:
        handlers[event] = OrderedDict()

    if app is None:
        logger.info(f"Handler [{event} -> {name} registered]")
    else:
        app.logger.info(f"Handler [{event} -> {name} registered]")
    handlers[event][name] = handler


def register_all(event_map, app=None):
    """
    Register all the listeners of the event map. The key is the event
    name, and the value is the module to load when the event occurs.
    """
    for event_name, handler_module in event_map.items():
        module_name = handler_module.__name__.split(".")[-1]
        register(event_name, module_name, handler_module, app)


def unregister(event, name):
    """
    Remove the handler with the given name from the list of registered
    listeners. After this, the handler does not run when the event occurs.
    """
    if event in handlers:
        handlers[event].pop(name, None)


def unregister_all():
    """
    Remove all the event handlers. After this, nothing runs when an event
    occurs.
    """
    global handlers
    handlers = {}


def emit(event, data=None, persist=True, project_id=None):
    """
    Emit an event, which runs all the event handlers registered for that
    event name (as queued jobs if ENABLE_JOB_QUEUE is set). It also
    publishes the event to other services (such as the realtime event
    daemon). If persist is True, it stores the event in the database. It
    adds the given project_id to the data dict of the caller.
    """
    if data is None:
        data = {}
    event = event.lower()
    event_handlers = handlers.get(event, {})
    if project_id is not None:
        data["project_id"] = project_id
    data = fields.serialize_dict(data)
    publisher_store.publish(event, data)
    if persist:
        # Create a DB entry that saves the data of the event, and put its ID
        # in the data, so that the handlers can read it.
        api_event = save_event(event, data, project_id=project_id)
        data["id"] = str(api_event.id)

    from zou.app.config import ENABLE_JOB_QUEUE

    for func in event_handlers.values():
        if ENABLE_JOB_QUEUE:
            from zou.app.stores.queue_store import job_queue

            job_queue.enqueue(func.handle_event, data)
        else:
            try:
                func.handle_event(data)
            except Exception:
                current_app.logger.error(
                    f"Error handling event {event} "
                    f"with {type(func).__name__}",
                    exc_info=1,
                )


def save_event(event, data, project_id=None):
    """
    Store the event information in the database, then run the save hooks.
    Return the ApiEvent active record.
    """
    try:
        # The identity that the JWT callback loads. Outside a request, or
        # without a token, the proxy raises an error and the event has no
        # author.
        person_id = current_user.id
    except Exception:
        person_id = None

    if project_id == "None":
        project_id = None

    api_event = ApiEvent.create(
        name=event, data=data, user_id=person_id, project_id=project_id
    )

    for hook in save_hooks:
        try:
            hook(event)
        except Exception:
            # A hook must never break the write path. If the cache is not
            # available, the log filters only stay stale until the entry
            # expires.
            current_app.logger.warning(
                f"Event save hook {hook.__name__} failed.", exc_info=1
            )
    return api_event
