from zou.app.services import shots_service
from zou.app.utils import events


def add_shot_to_scene(scene, shot):
    """
    Link a shot to a scene. After this, the scene is the source of the shot.
    """
    shot = shots_service.update_shot(shot["id"], {"source_id": scene["id"]})
    events.emit(
        "shot:add-to-scene",
        {"scene_id": scene["id"], "shot_id": shot["id"]},
        project_id=shot["project_id"],
    )
    return shot


def remove_shot_from_scene(scene, shot):
    """
    Remove the link from a shot to a scene.
    """
    shot = shots_service.update_shot(shot["id"], {"source_id": None})
    events.emit(
        "shot:remove-from-scene",
        {"scene_id": scene["id"], "shot_id": shot["id"]},
        project_id=shot["project_id"],
    )
    return shot


def get_shots_by_scene(scene_id):
    """
    Return the shots linked to a scene: the shots that have the given scene
    as their source.
    """
    return shots_service.get_shots({"source_id": scene_id})
