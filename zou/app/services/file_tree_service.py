import os
import re
from collections import OrderedDict

import orjson as json
from slugify import slugify

from zou.app.exceptions import (
    EpisodeNotFoundException,
    MalformedFileTreeException,
    SequenceNotFoundException,
    TaskNotFoundException,
    WrongFileTreeFileException,
    WrongPathFormatException,
)
from zou.app.models.asset_instance import AssetInstance
from zou.app.models.department import Department
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.output_type import OutputType
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.services import (
    departments_service,
    entities_service,
    entity_types_service,
    files_service,
    projects_service,
    shots_service,
    task_types_service,
    tasks_service,
)

ALLOWED_FIELDS = {"short_name", "name", "number", "id"}
UUID_PATTERN = re.compile(
    r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89aAbB][a-f0-9]{3}-[a-f0-9]{12}"
)


_FILE_TREE_NAME_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


def get_working_file_path(
    task,
    mode="working",
    software=None,
    output_type=None,
    name="",
    revision=1,
    sep=os.sep,
):
    """
    Return the working file path for the given parameters. The task is
    necessary to get the full context. The mode matches a template of the
    file tree file. Software, output type and name are necessary only if
    the template has them.
    """
    file_name = get_working_file_name(
        task,
        mode=mode,
        software=software,
        output_type=output_type,
        name=name,
        revision=revision,
    )
    folder = get_working_folder_path(
        task,
        mode,
        software=software,
        output_type=output_type,
        name=name,
        revision=revision,
        sep=sep,
    )
    return join_path(folder, file_name, sep)


def get_output_file_path(
    entity,
    mode="output",
    software=None,
    output_type=None,
    task_type=None,
    name="",
    revision=1,
    sep=os.sep,
):
    """
    Return the output file path for the given parameters. It starts from the
    entity, not from a task as the working variant does. An output file
    belongs to the entity and has a task type.
    """
    file_name = get_output_file_name(
        entity,
        mode=mode,
        software=software,
        output_type=output_type,
        task_type=task_type,
        name=name,
        revision=revision,
    )
    folder = get_output_folder_path(
        entity,
        mode,
        software=software,
        output_type=output_type,
        task_type=task_type,
        name=name,
        revision=revision,
        sep=sep,
    )
    return join_path(folder, file_name, sep)


def get_working_file_name(
    task, mode="working", software=None, output_type=None, name="", revision=1
):
    """
    Render the working file name of the given task with the file name
    template of its project. output_type is accepted to match the output
    variant. The working templates have no <OutputType> token.
    """
    entity = entities_service.get_entity(task["entity_id"])
    project = get_project_of_entity(entity)
    tree = get_tree_from_project(project)

    file_name = get_file_name_root(
        tree,
        mode,
        entity=entity,
        task=task,
        software=software,
        name=name,
        revision=revision,
    )

    return file_name


def get_output_file_name(
    entity,
    mode="output",
    software=None,
    output_type=None,
    task_type=None,
    name="",
    revision=1,
    nb_elements=1,
):
    """
    Render the output file name of the given entity with the file name
    template of its project. An output for many elements gets a _[1-N]
    suffix. The DCCs expand this range notation into one file per element.
    """
    project = get_project_of_entity(entity)
    tree = get_tree_from_project(project)

    file_name = get_file_name_root(
        tree,
        mode,
        entity=entity,
        task_type=task_type,
        software=software,
        output_type=output_type,
        name=name,
        revision=revision,
    )

    if nb_elements > 1:
        file_name += f"_[1-{nb_elements}]"

    return file_name


def get_instance_file_name(
    asset_instance,
    temporal_entity,
    output_type=None,
    task_type=None,
    mode="output",
    name="main",
    revision=1,
    nb_elements=1,
):
    """
    Render the output file name of an asset instance in the given temporal
    entity. The asset comes from the instance. The project comes from the
    entity that contains the instance.
    """
    asset = entities_service.get_entity(asset_instance["asset_id"])
    project = get_project_of_entity(temporal_entity)
    tree = get_tree_from_project(project)

    file_name = get_file_name_root(
        tree,
        mode,
        entity=temporal_entity,
        output_type=output_type,
        task_type=task_type,
        name=name,
        asset_instance=asset_instance,
        asset=asset,
        revision=revision,
    )

    if nb_elements > 1:
        file_name += f"_[1-{nb_elements}]"

    return file_name


def get_working_folder_path(
    task,
    mode="working",
    software=None,
    output_type=None,
    name="",
    revision=1,
    sep=os.sep,
):
    """
    Render the working folder of the given task. The result is:
    - the root path of the mode
    - then the folder template, with its tokens filled and its slashes
      changed into the separator of the target platform.
    """
    entity = entities_service.get_entity(task["entity_id"])
    project = get_project_of_entity(entity)
    tree = get_tree_from_project(project)
    root_path = get_root_path(tree, mode, sep)
    style = tree[mode]["folder_path"].get("style", "")

    folder_template = get_folder_path_template(tree, mode, entity)
    folder_path = update_variable(
        folder_template,
        entity=entity,
        task=task,
        software=software,
        name=name,
        revision=revision,
        style=style,
    )
    folder_path = change_folder_path_separators(folder_path, sep)

    return join_path(root_path, folder_path, "")


def get_output_folder_path(
    entity,
    mode="output",
    software=None,
    output_type=None,
    task_type=None,
    name="",
    representation="",
    revision=1,
    sep=os.sep,
):
    """
    Render the output folder of the given entity, as for the working folder.
    Use the output tokens: task type, output type and representation.
    """
    project = get_project_of_entity(entity)
    tree = get_tree_from_project(project)
    root_path = get_root_path(tree, mode, sep)
    style = tree[mode]["folder_path"].get("style", "")

    folder_template = get_folder_path_template(tree, mode, entity)
    folder_path = update_variable(
        folder_template,
        entity=entity,
        task_type=task_type,
        software=software,
        output_type=output_type,
        name=name,
        representation=representation,
        revision=revision,
        style=style,
    )
    folder_path = change_folder_path_separators(folder_path, sep)

    return join_path(root_path, folder_path, "")


def get_instance_folder_path(
    asset_instance,
    temporal_entity,
    output_type=None,
    task_type=None,
    name="name",
    mode="output",
    representation="",
    revision=1,
    sep=os.sep,
):
    """
    Render the output folder of an asset instance. Find the template from
    the instance, not from the temporal entity that contains it. Thus, a
    tree can give a different layout to instances.
    """
    asset = entities_service.get_entity(asset_instance["asset_id"])
    project = get_project_of_entity(temporal_entity)
    tree = get_tree_from_project(project)
    root_path = get_root_path(tree, mode, sep)
    style = tree[mode]["folder_path"].get("style", "")

    folder_template = get_folder_path_template(tree, mode, asset_instance)

    folder_path = update_variable(
        folder_template,
        entity=temporal_entity,
        software=None,
        output_type=output_type,
        name=name,
        style=style,
        asset_instance=asset_instance,
        task_type=task_type,
        revision=revision,
        representation=representation,
        asset=asset,
    )
    folder_path = change_folder_path_separators(folder_path, sep)

    return join_path(root_path, folder_path, "")


def get_project_of_entity(entity):
    """
    Return the project of the given entity.
    """
    return projects_service.get_project(entity["project_id"])


def get_tree_from_project(project):
    """
    Return the file tree of the given project.
    """
    return project["file_tree"]


_file_tree_cache = {}


def get_tree_from_file(tree_name):
    """
    Read a file tree that zou supplies in zou/app/file_trees. First, make
    sure that the name is a plain identifier. os.path.join does not
    normalize "..". If the second argument is absolute, it removes the
    prefix.
    """
    from zou.app import app

    if not _FILE_TREE_NAME_PATTERN.fullmatch(tree_name or ""):
        raise WrongFileTreeFileException(f"Wrong file tree name: {tree_name}.")
    if tree_name in _file_tree_cache:
        return _file_tree_cache[tree_name]
    try:
        tree_path = os.path.join(
            os.path.join(app.root_path, "file_trees"), f"{tree_name}.json"
        )
        tree_string = open(tree_path).read()
    except IOError:
        raise WrongFileTreeFileException(
            f"File Tree file not found: {tree_path}."
        )
    tree = json.loads(tree_string)
    _file_tree_cache[tree_name] = tree
    return tree


def _get_template(tree, mode, entity, section):
    """
    Return the template of the given section ("folder_path" or "file_name")
    for the kind of the given entity. A tree without the mode or the kind is
    malformed: change the KeyError into the domain exception.
    """
    # Read the tree in each branch, not before the branches. The entity
    # kind is found first. Thus, the error of a malformed tree still
    # occurs after the dispatch, not before it.
    try:
        if entity["type"] == "AssetInstance":
            if entity.get("target_asset_id", None) is not None:
                return tree[mode][section]["instance_asset"]
            return tree[mode][section]["instance"]
        elif entity_types_service.is_shot(entity):
            return tree[mode][section]["shot"]
        elif entity_types_service.is_sequence(entity):
            return tree[mode][section]["sequence"]
        elif entity_types_service.is_scene(entity):
            return tree[mode][section]["scene"]
        elif entity_types_service.is_episode(entity):
            return tree[mode][section]["episode"]
        else:
            return tree[mode][section]["asset"]
    except KeyError:
        raise MalformedFileTreeException


def get_folder_path_template(tree, mode, entity):
    """
    Return the folder path template for the kind of the given entity.
    """
    return _get_template(tree, mode, entity, "folder_path")


def get_file_name_template(tree, mode, entity):
    """
    Return the file name template for the kind of the given entity.
    """
    return _get_template(tree, mode, entity, "file_name")


def get_file_name_root(
    tree,
    mode,
    entity=None,
    task=None,
    task_type=None,
    software=None,
    output_type=None,
    name="main",
    asset_instance=None,
    asset=None,
    revision=1,
):
    """
    Render the file name template of the given tree. Slugify the result with
    the style of the mode. Keep the UUIDs before the slugify step and put
    them back after it. Slugify changes them to lowercase and cuts them, but
    an id must stay usable as an id.
    """
    if asset_instance is None:
        file_name_template = get_file_name_template(tree, mode, entity)
    else:
        file_name_template = get_file_name_template(tree, mode, asset_instance)

    file_name = update_variable(
        file_name_template,
        entity=entity,
        task=task,
        task_type=task_type,
        software=software,
        output_type=output_type,
        name=name,
        asset_instance=asset_instance,
        asset=asset,
        revision=revision,
    )
    style = tree[mode]["file_name"].get("style", "")
    uuids = UUID_PATTERN.findall(file_name)
    file_name = apply_style(slugify(file_name, separator="_"), style)
    for uuid in uuids:
        uuid_formatted = apply_style(slugify(uuid, separator="_"), style)
        file_name = file_name.replace(uuid_formatted, uuid)
    return file_name


def change_folder_path_separators(folder_path, sep):
    """
    Replace the slashes of a template with the separator of the target
    platform.
    """
    return folder_path.replace("/", sep)


def get_root_path(tree, mode, sep):
    """
    Build the absolute prefix of all the paths of the given mode: the
    mountpoint, then the root if it is set.
    """
    if tree is None:
        raise MalformedFileTreeException(
            "No tree can be found for given project."
        )

    if mode not in tree:
        raise MalformedFileTreeException(
            f"Mode {mode} cannot be found on given tree."
        )

    try:
        mountpoint = tree[mode]["mountpoint"]
        root = tree[mode]["root"]
    except KeyError:
        raise MalformedFileTreeException(
            f"Can't find given mode ({mode}) in given tree."
        )
    if root:
        return f"{mountpoint}{sep}{root}{sep}"
    else:
        return f"{mountpoint}{sep}"


def update_variable(
    template,
    entity=None,
    task=None,
    task_type=None,
    software=None,
    output_type=None,
    asset_instance=None,
    asset=None,
    name="",
    representation="",
    revision=1,
    style="lowercase",
):
    """
    Replace each <Token> of a template with its value. A token can give the
    field to read, as in <Shot.id>. If the field is unknown, use name.
    Slugify and style each value, but not an id. An id must stay as it is
    to stay usable.
    """
    variables = re.findall(r"<([\w\.]*)>", template)

    render = template
    for variable in variables:
        variable_infos = variable.split(".")
        data_type = variable_infos[0]
        is_field_given = len(variable_infos) > 1
        if is_field_given:
            field = variable_infos[1]
            if field not in ALLOWED_FIELDS:
                field = "name"
        else:
            field = "name"

        data = get_folder_from_datatype(
            data_type,
            entity=entity,
            task=task,
            task_type=task_type,
            software=software,
            output_type=output_type,
            name=name,
            asset_instance=asset_instance,
            asset=asset,
            representation=representation,
            revision=revision,
            field=field,
        )

        if data is not None:
            if field != "id":
                data = apply_style(slugify(data, separator="_"), style)
            render = render.replace(f"<{variable}>", data)
    return render


def get_folder_from_datatype(
    datatype,
    entity=None,
    task=None,
    task_type=None,
    software=None,
    output_type=None,
    name="",
    asset_instance=None,
    asset=None,
    representation="",
    revision=1,
    field="name",
):
    """
    Return the value of a template token. This is the dispatch of all the
    file tree rendering. All the <Token> values that the templates accept
    are found here. An unknown token makes the tree malformed.
    """
    if datatype == "Project":
        folder = get_folder_from_project(entity, field)
    elif datatype == "Task":
        folder = get_folder_from_task(task, field)
    elif datatype == "TaskType":
        folder = get_folder_from_task_type(task, task_type, field)
    elif datatype == "Department":
        folder = get_folder_from_department(task, task_type, field)
    elif datatype == "Shot":
        folder = get_folder_from_shot(entity, field)
    elif datatype == "TemporalEntity":
        folder = get_folder_from_temporal_entity(entity, field)
    elif datatype == "TemporalEntityType":
        folder = get_folder_from_temporal_entity_type(entity, field)
    elif datatype == "AssetType":
        if asset is None:
            folder = get_folder_from_asset_type(entity, field)
        else:
            folder = get_folder_from_asset_type(asset, field)
    elif datatype == "Sequence":
        folder = get_folder_from_sequence(entity, field)
    elif datatype == "Episode":
        folder = get_folder_from_episode(entity, field)
    elif datatype == "Asset":
        if asset is None:
            folder = get_folder_from_asset(entity, field)
        else:
            folder = get_folder_from_asset(asset, field)
    elif datatype == "Software":
        folder = get_folder_from_software(software, field)
    elif datatype == "OutputType":
        folder = get_folder_from_output_type(output_type, field)
    elif datatype == "Scene":
        folder = get_folder_from_scene(entity, field)
    elif datatype == "Instance":
        folder = get_folder_from_asset_instance(asset_instance, field)
    elif datatype == "Representation":
        folder = get_folder_from_representation(representation)
    elif datatype in ["Name", "OutputFile", "WorkingFile"]:
        folder = name
    elif datatype == "Version" or datatype == "Revision":
        folder = get_folder_from_revision(revision)
    else:
        raise MalformedFileTreeException(f"Unknown data type: {datatype}.")

    return folder


def get_folder_from_project(entity, field="name"):
    """
    Return the value of the <Project> token. Read it on the project of the
    given entity, not on the entity.
    """
    project = get_project_of_entity(entity)
    return project[field]


def get_folder_from_task(task, field="name"):
    """
    Return the value of the <Task> token.
    """
    return task[field]


def get_folder_from_shot(shot, field="name"):
    """
    Return the value of the <Shot> token.
    """
    return shot[field]


def get_folder_from_output_type(output_type, field="name"):
    """
    Return the value of the <OutputType> token, in lowercase. If a template
    needs an output type and none is given, use Geometry. If Geometry does
    not exist, create it.
    """
    if output_type is None:
        output_type = files_service.get_or_create_output_type("Geometry")

    return output_type[field].lower()


def get_folder_from_department(task, task_type, field="name"):
    """
    Return the value of the <Department> token. If a task type is given, get
    it from the task type. Else, get it from the task. If neither is given,
    return an empty value. Thus, a template stays usable on a path without a
    task.
    """
    folder = ""
    if task_type is None and task is not None:
        department = tasks_service.get_department_from_task(task["id"])
        folder = department[field]
    elif task_type is not None:
        department = departments_service.get_department_from_task_type(
            task_type["id"]
        )
        folder = department[field]
    return folder


def get_folder_from_task_type(task, task_type, field="name"):
    """
    Return the value of the <TaskType> token, from the given task type or
    from the task. If neither is given, return an empty value, as for the
    department token.
    """
    folder = ""
    if task_type is None and task is not None:
        task_type = task_types_service.get_task_type(task["task_type_id"])
        if task_type is not None:
            folder = task_type[field]
    elif task_type is not None:
        folder = task_type[field]
    return folder


def get_folder_from_asset(asset, field="name"):
    """
    Return the asset folder name. If there is no asset, return an empty
    value.
    """
    return asset[field] if asset is not None else ""


def get_folder_from_sequence(entity, field="name"):
    """
    Return the value of the <Sequence> token. Go up from a shot or a scene
    to its sequence.
    """
    if entity_types_service.is_shot(entity) or entity_types_service.is_scene(
        entity
    ):
        sequence = shots_service.get_sequence_from_shot(entity)
        sequence_name = sequence[field]
    elif entity_types_service.is_sequence(entity):
        sequence_name = entity[field]
    else:
        sequence_name = ""
    return sequence_name


def get_folder_from_episode(entity, field="name"):
    """
    Return the episode folder name of the given entity. If it is a shot or a
    scene, go up through its sequence. If an entity has no episode, use
    e001, the name for a flat production.
    """
    episode = None
    sequence = None

    if entity_types_service.is_episode(entity):
        episode = entity
    else:
        if entity_types_service.is_shot(
            entity
        ) or entity_types_service.is_scene(entity):
            try:
                sequence = shots_service.get_sequence_from_shot(entity)
            except SequenceNotFoundException:
                sequence = None
        elif entity_types_service.is_sequence(entity):
            sequence = entity
        # Some entities have no parent to go up to:
        # - an entity of a different kind (an asset)
        # - a shot without a sequence
        # - a sequence without an episode (a production that is not a tv
        #   show).
        # These entities use the default value below.
        if sequence is not None:
            try:
                episode = shots_service.get_episode_from_sequence(sequence)
            except EpisodeNotFoundException:
                episode = None

    try:
        episode_name = episode[field]
    except Exception:
        episode_name = "e001"

    return episode_name


def get_folder_from_temporal_entity(entity, field="name"):
    """
    Return the folder name of the given temporal entity (shot, sequence...).
    """
    if entity is None:
        raise MalformedFileTreeException("Given temporal entity is null.")
    return entities_service.get_entity(entity["id"])[field]


def get_folder_from_temporal_entity_type(entity, field="name"):
    """
    Return the folder name of the type of the given temporal entity.
    """
    if entity is None:
        raise MalformedFileTreeException("Given temporal entity type is null.")
    entity_type = entity_types_service.get_entity_type(
        entity["entity_type_id"]
    )
    return entity_type[field].lower()


def get_folder_from_asset_type(asset, field="name"):
    """
    Return the folder name of the type of the given asset.
    """
    if asset is None:
        raise MalformedFileTreeException("Given asset is null.")
    return entity_types_service.get_asset_type(asset["entity_type_id"])[field]


def get_folder_from_software(software, field="name"):
    """
    Return the value of the <Software> token. If a template needs a software
    and none is given, use 3ds Max. If 3ds Max does not exist, create it.
    """
    if software is None:
        software = files_service.get_or_create_software(
            "3dsmax", "max", ".max"
        )
    return software[field]


def get_folder_from_scene(scene, field="name"):
    """
    Return the scene folder name. If there is no scene, return an empty
    value.
    """
    return scene[field] if scene is not None else ""


def get_folder_from_asset_instance(asset_instance, field):
    """
    Return the value of the <Instance> token. This is the instance name. If
    the field is not the name, or if the instance has no name, use its
    number padded to four digits. If there is no instance, return an empty
    value.
    """
    folder = ""
    if asset_instance is not None:
        number = str(asset_instance.get("number", 0)).zfill(4)
        if field == "name":
            folder = asset_instance.get("name", number)
            if folder is None:
                folder = number
        else:
            folder = number

    return folder


def get_folder_from_representation(representation):
    """
    Return the value of the <Representation> token as it is given. It is a
    free string from the client, not a stored entity.
    """
    return representation


def get_folder_from_revision(revision):
    """
    Return the value of the <Version> and <Revision> tokens, padded to three
    digits. Thus, a file browser sorts the revisions in the correct order.
    """
    return str(revision).zfill(3)


def join_path(left, right, sep=os.sep):
    """
    Join two path fragments. If one fragment is empty, do not add the
    separator.
    """
    if left == "":
        return right
    if right == "":
        return left
    return f"{left}{sep}{right}"


def apply_style(file_name, style):
    """
    Apply the case that the tree gives. For a value other than uppercase or
    lowercase, do not change the name. A tree uses this to disable the case
    change.
    """
    if style == "uppercase":
        file_name = file_name.upper()

    elif style == "lowercase":
        file_name = file_name.lower()

    return file_name


class PathTokens(object):
    """
    Return the names of the tokens that a file tree template can have.
    """

    PROJECT = "Project"
    EPISODE = "Episode"
    SEQUENCE = "Sequence"
    SCENE = "Scene"
    SHOT = "Shot"
    ASSET_TYPE = "AssetType"
    ASSET = "Asset"
    DEPARTMENT = "Department"
    TASK_TYPE = "TaskType"
    TASK = "Task"
    OUTPUT_TYPE = "OutputType"
    NAME = "Name"
    REPRESENTATION = "Representation"
    SOFTWARE = "Software"
    VERSION = "Version"
    ENTITY_TYPE = "TemporalEntityType"
    ENTITY = "TemporalEntity"
    INSTANCE = "Instance"


def get_shot_task_from_path(file_path, project, mode="working", sep="/"):
    """
    Find the shot task of a working file path. Compare the path with the
    shot template of the project.
    """
    template_elements = get_shot_template_folders(project, mode, sep)
    elements = get_path_folders(project, file_path, mode, sep)

    if len(elements) != len(template_elements):
        tree = get_tree_from_project(project)
        template = get_shot_path_template(tree, mode)
        raise WrongPathFormatException(f"{file_path} doesn't match {template}")

    data_names = extract_variable_values_from_path(elements, template_elements)

    shot = guess_shot(
        project,
        data_names.get(PathTokens.EPISODE, ""),
        data_names.get(PathTokens.SEQUENCE, ""),
        data_names.get(PathTokens.SHOT, ""),
    )
    task_type = guess_task_type(
        data_names.get(PathTokens.DEPARTMENT, ""),
        data_names.get(PathTokens.TASK_TYPE, ""),
    )
    task = guess_task(shot, task_type, data_names.get(PathTokens.TASK, ""))

    return task.serialize()


def get_asset_task_from_path(file_path, project, mode="working", sep="/"):
    """
    Find the asset task of a working file path. Compare the path with the
    asset template of the project.
    """
    template_elements = get_asset_template_folders(project, mode, sep)
    elements = get_path_folders(project, file_path, mode, sep)

    if len(elements) != len(template_elements):
        tree = get_tree_from_project(project)
        template = get_asset_path_template(tree, mode)
        raise WrongPathFormatException(f"{file_path} doesn't match {template}")

    data_names = extract_variable_values_from_path(elements, template_elements)

    asset = guess_asset(
        project,
        data_names.get(PathTokens.ASSET_TYPE, ""),
        data_names.get(PathTokens.ASSET, ""),
    )
    task_type = guess_task_type(
        data_names.get(PathTokens.DEPARTMENT, ""),
        data_names.get(PathTokens.TASK_TYPE, ""),
    )
    task = guess_task(asset, task_type, data_names.get(PathTokens.TASK, ""))

    return task.serialize()


def extract_variable_values_from_path(elements, template_elements):
    """
    Map each template token to the value at the same position in the path.
    A token can have a prefix and a suffix (`v<Version>` and `v003` give
    `003`). If a token occurs more than one time, use the first occurrence.
    """
    data_names = OrderedDict()
    max_count = min(len(elements), len(template_elements))
    for i, template_element in enumerate(template_elements):
        if i == max_count:
            break

        # Use the prefix and the suffix to get only the token value.
        # For example, for `v<Version>` and `v003`, the result is `003`
        # without the `v` prefix.
        token = re.search(
            r"(?P<prefix>\w*)<(?P<token>\w*)>(?P<suffix>\w*)", template_element
        )

        if token is None:
            if template_element == elements[i]:
                continue
            else:
                raise WrongPathFormatException(
                    f"{elements} doesn't match {template_elements}"
                )

        data_type = token.group("token")
        value = elements[i].replace("_", " ")
        value = value[
            len(token.group("prefix")) : len(value)
            - len(token.group("suffix"))
        ]

        if not data_names.get(data_type):
            data_names[data_type] = value

    return data_names


def get_shot_path_template(tree, mode="working"):
    """
    Return the shot folder template of the given tree. If it does not exist,
    return an empty value.
    """
    return tree[mode]["folder_path"].get("shot", "")


def get_asset_path_template(tree, mode="working"):
    """
    Return the asset folder template of the given tree. If it does not
    exist, return an empty value.
    """
    return tree[mode]["folder_path"].get("asset", "")


def get_shot_template_folders(project, mode="working", sep="/"):
    """
    Split the shot template of the project into its folder elements.
    """
    tree = get_tree_from_project(project)
    template = get_shot_path_template(tree, mode)
    return template.split(sep)


def get_asset_template_folders(project, mode="working", sep="/"):
    """
    Split the asset template of the project into its folder elements.
    """
    tree = get_tree_from_project(project)
    template = get_asset_path_template(tree, mode)
    return template.split(sep)


def get_path_folders(project, file_path, mode="working", sep="/"):
    """
    Split a file path into folder elements, without the root. Thus, the
    elements align with the template elements.
    """
    tree = get_tree_from_project(project)
    root = get_root_path(tree, mode, sep)
    file_path = file_path[len(root) :]
    return file_path.split(sep)


def _get_child_by_name(name, entity_type_id, constraints, parent_token):
    """
    Return the entity of the given type that a path token names. If the path
    already gave a parent, use it to limit the search.
    """
    if not constraints.get(PathTokens.PROJECT):
        return None

    criterions = {
        "entity_type_id": entity_type_id,
        "project_id": constraints[PathTokens.PROJECT],
    }
    if constraints.get(parent_token):
        criterions["parent_id"] = constraints[parent_token]

    return Entity.get_by(Entity.name.ilike(name), **criterions)


def get_data_from_token(type_token, value_token, constraints=None):
    """
    Return the first data that matches the given type and value tokens:
    - an active record
    - a string for a name or a representation
    - an int for a version.
    If nothing matches or a constraint is missing, return None.
    """
    if not constraints:
        constraints = {}
    data = None

    if type_token == PathTokens.ASSET:
        # An asset needs a project and an asset type.
        if not constraints.get(PathTokens.PROJECT) or not constraints.get(
            PathTokens.ASSET_TYPE
        ):
            return None

        data = Entity.get_by(
            Entity.name.ilike(value_token),
            entity_type_id=constraints[PathTokens.ASSET_TYPE],
            project_id=constraints[PathTokens.PROJECT],
        )

    elif type_token == PathTokens.ASSET_TYPE:
        data = EntityType.get_by(EntityType.name.ilike(value_token))

    elif type_token == PathTokens.DEPARTMENT:
        data = Department.get_by(Department.name.ilike(value_token))

    elif type_token == PathTokens.EPISODE:
        # An episode needs a project.
        if not constraints.get(PathTokens.PROJECT):
            return None

        data = Entity.get_by(
            Entity.name.ilike(value_token),
            entity_type_id=entity_types_service.get_episode_type()["id"],
            project_id=constraints[PathTokens.PROJECT],
        )

    elif type_token == PathTokens.SEQUENCE:
        # A sequence needs a project. It needs an episode only in a
        # production with episodes: if the path has an episode, use it to
        # limit the search. Do not make the episode mandatory. The supplied
        # trees put no <Episode> token before the sequence. Thus, all the
        # paths of a flat production stop here.
        data = _get_child_by_name(
            value_token,
            entity_types_service.get_sequence_type()["id"],
            constraints,
            parent_token=PathTokens.EPISODE,
        )

    elif type_token == PathTokens.SCENE:
        # A scene needs a project. If the path has a sequence, the scene also
        # needs this sequence.
        data = _get_child_by_name(
            value_token,
            entity_types_service.get_scene_type()["id"],
            constraints,
            parent_token=PathTokens.SEQUENCE,
        )

    elif type_token == PathTokens.OUTPUT_TYPE:
        data = OutputType.get_by(OutputType.name.ilike(value_token))

    elif type_token == PathTokens.SHOT:
        # A shot needs a project and a sequence.
        if not constraints.get(PathTokens.PROJECT) or not constraints.get(
            PathTokens.SEQUENCE
        ):
            return None

        data = Entity.get_by(
            Entity.name.ilike(value_token),
            entity_type_id=entity_types_service.get_shot_type()["id"],
            parent_id=constraints[PathTokens.SEQUENCE],
            project_id=constraints[PathTokens.PROJECT],
        )

    elif type_token == PathTokens.TASK:
        # A task needs a project, a task type and an entity.
        if not constraints.get(PathTokens.PROJECT) or not constraints.get(
            PathTokens.TASK_TYPE
        ):
            return None

        name_filter = Task.name.ilike(value_token)
        kwargs = {
            "task_type_id": constraints[PathTokens.TASK_TYPE],
            "project_id": constraints[PathTokens.PROJECT],
        }

        for entity in [PathTokens.SCENE, PathTokens.ASSET, PathTokens.SHOT]:
            if constraints.get(entity):
                kwargs["entity_id"] = constraints[entity]
                break
        else:
            return None

        data = Task.get_by(name_filter, **kwargs)

    elif type_token == PathTokens.TASK_TYPE:
        data = TaskType.get_by(TaskType.name.ilike(value_token))

    elif type_token == PathTokens.PROJECT:
        data = Project.get_by(Project.name.ilike(value_token))

    elif type_token == PathTokens.NAME:
        data = value_token

    elif type_token == PathTokens.REPRESENTATION:
        data = value_token

    elif type_token == PathTokens.VERSION:
        try:
            data = int(value_token)
        except ValueError:
            return None

    elif type_token == PathTokens.ENTITY_TYPE:
        data = EntityType.get_by(EntityType.name.ilike(value_token))

    elif type_token == PathTokens.ENTITY:
        # An entity needs a project and an entity type.
        if not constraints.get(PathTokens.PROJECT) or not constraints.get(
            PathTokens.ENTITY_TYPE
        ):
            return None

        data = Entity.get_by(
            Entity.name.ilike(value_token),
            entity_type_id=constraints[PathTokens.ENTITY_TYPE],
            project_id=constraints[PathTokens.PROJECT],
        )

    elif type_token == PathTokens.INSTANCE:
        if not constraints.get(PathTokens.EPISODE):
            return None

        data = AssetInstance.get_by(
            AssetInstance.name.ilike(value_token),
            episode_id=constraints.get(PathTokens.EPISODE),
        )

    return data


def guess_shot(project, episode_name, sequence_name, shot_name):
    """
    Find the shot that the tokens of a path name. Find the episode, then the
    sequence, then the shot. If a name gives no result, set its parent to
    None and continue. Thus, a flat production still matches. Only a
    missing shot name is an error.
    """
    episode_id = None
    if len(episode_name) > 0:
        episode = Entity.get_by(
            name=episode_name,
            entity_type_id=entity_types_service.get_episode_type()["id"],
            project_id=project["id"],
        )
        if episode is not None:
            episode_id = episode.id

    sequence_id = None
    if len(sequence_name) > 0:
        sequence = Entity.get_by(
            name=sequence_name,
            entity_type_id=entity_types_service.get_sequence_type()["id"],
            parent_id=episode_id,
            project_id=project["id"],
        )
        if sequence is not None:
            sequence_id = sequence.id
    else:
        sequence_id = None

    if len(shot_name) > 0:
        shot = Entity.get_by(
            name=shot_name,
            entity_type_id=entity_types_service.get_shot_type()["id"],
            parent_id=sequence_id,
            project_id=project["id"],
        )
    else:
        raise WrongPathFormatException("Shot name was not found in given path")
    return shot


def guess_asset(project, asset_type_name, asset_name):
    """
    Find the asset that the tokens of a path name. The asset type only
    limits the search. If the asset type is unknown, ignore it and continue.
    A missing asset name is an error.
    """
    asset_type_id = None
    if len(asset_type_name) > 0:
        asset_type = EntityType.get_by(name=asset_type_name)
        if asset_type is not None:
            asset_type_id = asset_type.id

    if len(asset_name) > 0:
        asset = Entity.get_by(
            name=asset_name,
            entity_type_id=asset_type_id,
            project_id=project["id"],
        )
    else:
        raise WrongPathFormatException(
            "Asset name was not found in given path."
        )

    return asset


def guess_task_type(department_name, task_type_name):
    """
    Find the task type that the tokens of a path name. The department
    identifies the correct task type when two departments have task types
    with the same name. It only limits the search. If the department is
    unknown, ignore it and continue, as for the asset type and the episode
    in the two functions above.
    """
    criterions = {"name": task_type_name}
    if len(department_name) > 0:
        department = Department.get_by(name=department_name)
        if department is not None:
            criterions["department_id"] = department.id

    task_type = TaskType.get_by(**criterions)
    if task_type is None:
        raise WrongPathFormatException(
            f"Task type {task_type_name} was not found in given path."
        )
    return task_type


def guess_task(entity, task_type, task_name):
    """
    Find the task of the given entity and task type. If the path has a task
    name, use it to limit the search. The productions that name their tasks
    have many tasks for the same type.
    """
    if entity is None:
        raise WrongPathFormatException("No asset or shot found in given path.")

    criterions = {"entity_id": entity.id, "task_type_id": task_type.id}
    if len(task_name) > 0:
        criterions["name"] = task_name

    task = Task.get_by(**criterions)
    if task is None:
        raise TaskNotFoundException
    else:
        return task


def guess_from_path(project_id, file_path, sep="/"):
    """
    Return the list of the project file tree templates that can match a
    file path. Also return the data ids of the template tokens.

    Example:
        .. code-block:: text

        [
            {
                'Asset': '<asset_id>',
                'Project': '<project_id>',
                'Template': 'asset'
            },
            {
                'Project': '<project_id>',
                'Template': 'instance'
            },
            ...
        ]
    """
    matching_templates = []
    project = projects_service.get_project(project_id)
    tree = get_tree_from_project(project)

    for mode in tree.keys():
        # Apply the style of the mode to the file path.
        style = tree[mode]["folder_path"].get("style", "")
        root = apply_style(get_root_path(tree, mode, sep), style)
        styled_path = apply_style(file_path, style)

        if not styled_path.startswith(root):
            continue

        styled_path = styled_path[len(root) :]

        # Try to get the template data from the path.
        for template, template_path in tree[mode]["folder_path"].items():
            template_elements = template_path.split(sep)
            elements = styled_path.split(sep)

            # The template does not match the content of the given file path.
            try:
                tokens = extract_variable_values_from_path(
                    elements, template_elements
                )
            except WrongPathFormatException:
                continue

            if not tokens:
                continue

            template_data = {
                "Template": template,
            }

            # Fill the template data dict in the order of the tokens in the
            # template path (left to right). Some data needs the previous data
            # to be found.
            # This prevents wrong data from the database, for example data
            # with the same name in a different project.
            for template_element in template_elements:
                # Get the token of the template_element.
                # Some template_element values have no token, for example the
                # "05_publish" folder.
                for token, token_value in tokens.items():
                    if f"<{token}>" in template_element:
                        break
                else:
                    continue

                data = get_data_from_token(token, token_value, template_data)

                # If no data is found, stop the search for the given template.
                # Keep the valid data found before.
                if not data:
                    break

                # The production is the one that the caller gave. The route
                # checked the permission of the caller on it. A path that names
                # a different production is for a different user. Do not fill
                # it with the ids of that production.
                if token == PathTokens.PROJECT and str(data.id) != str(
                    project["id"]
                ):
                    break

                if isinstance(data, str):
                    template_data[token] = data
                elif isinstance(data, int):
                    template_data[token] = str(data)
                else:
                    template_data[token] = data.serialize()["id"]

            if template_data not in matching_templates:
                matching_templates.append(template_data)

    return matching_templates
