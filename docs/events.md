# Events

Events are a mechanism to allow other programs to react to the change happening
into the API data. 

## Write an event handler

Your event definition should be located at the root of you event handlers
folder.

Your handler should only implement one function named `handle_event`. It takes
data sent with the event as parameter.

```python
def handle_event(data):
    print("Event occured!", data)
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

## Listen to events through http


You can listen to events by connecting to
`http://your.zouserver.domain/events`.

You can use the `sseclient-py` for that:

```python
    import requests
            
url = 'http://your.zou-domain.name/events'
response = requests.get(url, stream=True)
client = sseclient.SSEClient(response)
for event in client.events():
    data = json.loads(event.data)
    print(data)
```
