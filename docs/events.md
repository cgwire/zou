# Events

Events are a mechanism to allow other programs to react to the change happening
into the API data. 

## Define a location for your event handlers


Create the events folder:

```
mkdir /opt/zou/event_handlers
```

Then set `EVENT_HANDLERS_FOLDER` environment variable with the folder that will contain the event handler module: `/opt/zou/event_handlers`.


## Write an event handler

Your event definition should be located at the root of your event handlers
folder.

Your handler should only implement one function named `handle_event`. It takes
data sent with the event as parameter.

```python
from flask import current_app

def handle_event(data):
    current_app.logger.info("Event occured!")
```


## Register an event handler

To register an event you must fill the `event_map` dict located in the
`__init__.py` file of your event handlers folder.

The key of the dict is the event name that will trigger an event handler, the
value is the event handler itself.

Let's see an example:

```python
from . import shotgun_wip, shotgun_pending_review

event_map = {
    "task:start": shotgun_wip,
    "task:to-review": shogun_pending_review
}
```

This is how your folder should look like:

```
ls /opt/zou/event_handlers
__init__.py
shotgun_wip.py
shotgun_pending_review.py
```

## Listen to events through websocket

You can list to events externally. For that, please read the 
[events documentation](https://gazu.cg-wire.com/events.html) of the Python client.
