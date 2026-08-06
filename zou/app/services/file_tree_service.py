import os
import re
import orjson as json

from collections import OrderedDict
from slugify import slugify

from zou.app.models.asset_instance import AssetInstance
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.output_type import OutputType
from zou.app.models.task_type import TaskType
from zou.app.models.task import Task
from zou.app.models.department import Department
from zou.app.models.project import Project

from zou.app.services import (
    assets_service,
    entities_service,
    files_service,
    shots_service,
    projects_service,
    tasks_service,
)
from zou.app.services.exception import (
    MalformedFileTreeException,
    WrongFileTreeFileException,
    WrongPathFormatException,
    TaskNotFoundException,
)

ALLOWED_FIELDS = {"short_name", "name", "number", "id"}
UUID_PATTERN = re.compile(
    r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89aAbB][a-f0-9]{3}-[a-f0-9]{12}"
)


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
    Return working file path based on given paramaters. The task is mandatory
    to get the whole context. The mode matches a template described in the
    file tree file. Software, output type and name are required only if they
    are set in the template.
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
    Return output file path based on given parameters. It starts from the
    entity and not from a task, unlike the working variant: an output file
    belongs to the entity and carries its task type instead.
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
    Render the working file name of given task with the file name template of
    its project. output_type is accepted to mirror the output variant, the
    working templates have no <OutputType> token to fill.
    """
    entity = entities_service.get_entity(task["entity_id"])
    project = get_project(entity)
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
    Render the output file name of given entity with the file name template of
    its project. An output covering several elements gets a _[1-N] suffix, the
    range notation the DCCs expand into one file per element.
    """
    project = get_project(entity)
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
    Render the output file name of an asset instance inside given temporal
    entity. The asset comes from the instance, the project from the entity the
    instance sits in.
    """
    asset = entities_service.get_entity(asset_instance["asset_id"])
    project = get_project(temporal_entity)
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
    Render the working folder of given task: the root path of the mode, then
    the folder template with its tokens filled and its slashes turned into the
    separator of the target platform.
    """
    entity = entities_service.get_entity(task["entity_id"])
    project = get_project(entity)
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
    Render the output folder of given entity, same way as the working one but
    with the output tokens: task type, output type and representation.
    """
    project = get_project(entity)
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
    Render the output folder of an asset instance. The template is looked up
    from the instance and not from the temporal entity it sits in, so a tree
    can give instances a layout of their own.
    """
    asset = entities_service.get_entity(asset_instance["asset_id"])
    project = get_project(temporal_entity)
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


def get_project(entity):
    """
    Return the project given entity belongs to.
    """
    return projects_service.get_project(entity["project_id"])


def get_tree_from_project(project):
    """
    Return the file tree configured on given project.
    """
    return project["file_tree"]


_file_tree_cache = {}

_FILE_TREE_NAME_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


def get_tree_from_file(tree_name):
    """
    Read a file tree shipped in zou/app/file_trees. The name comes from the
    client on the set-file-tree route, so it is matched against a plain
    identifier first: os.path.join neither normalizes ".." nor keeps the
    prefix when the second argument is absolute, and the file content ends
    up in the response.
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
    Return the template of given section ("folder_path" or "file_name") for
    the kind of given entity. A tree missing the mode or the kind is
    malformed: the KeyError is turned into the domain exception.
    """
    # The tree is read inside each branch, not hoisted: the entity kind is
    # resolved first, as it always was, so a malformed tree keeps surfacing
    # after the dispatch rather than before it.
    try:
        if entity["type"] == "AssetInstance":
            if entity.get("target_asset_id", None) is not None:
                return tree[mode][section]["instance_asset"]
            return tree[mode][section]["instance"]
        elif shots_service.is_shot(entity):
            return tree[mode][section]["shot"]
        elif shots_service.is_sequence(entity):
            return tree[mode][section]["sequence"]
        elif shots_service.is_scene(entity):
            return tree[mode][section]["scene"]
        elif shots_service.is_episode(entity):
            return tree[mode][section]["episode"]
        else:
            return tree[mode][section]["asset"]
    except KeyError:
        raise MalformedFileTreeException


def get_folder_path_template(tree, mode, entity):
    """
    Return the folder path template matching the kind of given entity.
    """
    return _get_template(tree, mode, entity, "folder_path")


def get_file_name_template(tree, mode, entity):
    """
    Return the file name template matching the kind of given entity.
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
    Render the file name template of given tree and slugify the result with
    the style of the mode. UUIDs are collected before slugifying and put back
    after: slugify would lowercase and cut them, and an id is meant to stay
    usable as an id.
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
    Rewrite a template's slashes with the separator of the target platform.
    """
    return folder_path.replace("/", sep)


def get_root_path(tree, mode, sep):
    """
    Build the absolute prefix every path of given mode starts with:
    mountpoint, then root when one is set.
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
    Replace every <Token> of a template by its value. A token may name the
    field to read, as in <Shot.id>; an unknown field falls back to name. Every
    value is slugified and styled, except an id, which has to stay verbatim to
    remain usable.
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
    Return the value a template token stands for. This is the dispatch of the
    whole file tree rendering: every <Token> the templates accept is resolved
    here, and an unknown one makes the tree malformed.
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
    Value of the <Project> token: read on the project of given entity, not on
    the entity.
    """
    project = get_project(entity)
    return project[field]


def get_folder_from_task(task, field="name"):
    """
    Value of the <Task> token.
    """
    return task[field]


def get_folder_from_shot(shot, field="name"):
    """
    Value of the <Shot> token.
    """
    return shot[field]


def get_folder_from_output_type(output_type, field="name"):
    """
    Value of the <OutputType> token, lowercased. A template asking for an
    output type when none is given falls back to Geometry, created on the fly
    if the studio never made one.
    """
    if output_type is None:
        output_type = files_service.get_or_create_output_type("Geometry")

    return output_type[field].lower()


def get_folder_from_department(task, task_type, field="name"):
    """
    Value of the <Department> token, resolved from the task type when there is
    one and from the task otherwise. Empty when neither is given, which keeps
    a template usable on a path that has no task.
    """
    folder = ""
    if task_type is None and task is not None:
        department = tasks_service.get_department_from_task(task["id"])
        folder = department[field]
    elif task_type is not None:
        department = tasks_service.get_department_from_task_type(
            task_type["id"]
        )
        folder = department[field]
    return folder


def get_folder_from_task_type(task, task_type, field="name"):
    """
    Value of the <TaskType> token, taken from the given task type or read back
    from the task. Empty when neither is given, like the department token.
    """
    folder = ""
    if task_type is None and task is not None:
        task_type = tasks_service.get_task_type(task["task_type_id"])
        if task_type is not None:
            folder = task_type[field]
    elif task_type is not None:
        folder = task_type[field]
    return folder


def get_folder_from_asset(asset, field="name"):
    """
    Return the asset folder name, empty when there is no asset.
    """
    return asset[field] if asset is not None else ""


def get_folder_from_sequence(entity, field="name"):
    """
    Value of the <Sequence> token, walking up from a shot or a scene to its
    sequence. A name carrying "Seq" is rewritten as S plus the number padded
    to three digits, so Seq2 and Seq02 land in the same folder.
    """
    if shots_service.is_shot(entity) or shots_service.is_scene(entity):
        sequence = shots_service.get_sequence_from_shot(entity)
        sequence_name = sequence[field]
    elif shots_service.is_sequence(entity):
        sequence_name = entity[field]
    else:
        sequence_name = ""

    if "Seq" in sequence_name:
        sequence_number = sequence_name[3:]
        sequence_name = f"S{sequence_number.zfill(3)}"
    return sequence_name


def get_folder_from_episode(entity, field="name"):
    """
    Return the episode folder name of given entity, walking up through its
    sequence when it is a shot or a scene. Entities that lead to no episode
    fall back to e001, the name a flat production uses.
    """
    episode = None
    sequence = None

    if shots_service.is_episode(entity):
        episode = entity
    else:
        if shots_service.is_shot(entity) or shots_service.is_scene(entity):
            sequence = shots_service.get_sequence_from_shot(entity)
        elif shots_service.is_sequence(entity):
            sequence = entity
        # An entity that is none of those (an asset) has no sequence to
        # walk up from, and falls back below like a missing episode does.
        if sequence is not None:
            episode = shots_service.get_episode_from_sequence(sequence)

    try:
        episode_name = episode[field]
    except Exception:
        episode_name = "e001"

    return episode_name


def get_folder_from_temporal_entity(entity, field="name"):
    """
    Return the folder name of given temporal entity (shot, sequence...).
    """
    if entity is None:
        raise MalformedFileTreeException("Given temporal entity is null.")
    return entities_service.get_entity(entity["id"])[field]


def get_folder_from_temporal_entity_type(entity, field="name"):
    """
    Return the folder name of the type of given temporal entity.
    """
    if entity is None:
        raise MalformedFileTreeException("Given temporal entity type is null.")
    entity_type = entities_service.get_entity_type(entity["entity_type_id"])
    return entity_type[field].lower()


def get_folder_from_asset_type(asset, field="name"):
    """
    Return the folder name of the type of given asset.
    """
    if asset is None:
        raise MalformedFileTreeException("Given asset is null.")
    return assets_service.get_asset_type(asset["entity_type_id"])[field]


def get_folder_from_software(software, field="name"):
    """
    Value of the <Software> token. A template asking for a software when none
    is given falls back to 3ds Max, created on the fly if the studio never
    declared it.
    """
    if software is None:
        software = files_service.get_or_create_software(
            "3dsmax", "max", ".max"
        )
    return software[field]


def get_folder_from_scene(scene, field="name"):
    """
    Return the scene folder name, empty when there is no scene.
    """
    return scene[field] if scene is not None else ""


def get_folder_from_asset_instance(asset_instance, field):
    """
    Value of the <Instance> token: the instance name, or its number padded to
    four digits when the field is not the name or when the instance carries no
    name. Empty when there is no instance.
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
    Value of the <Representation> token, taken as given: it is a free string
    the client sends, not a stored entity.
    """
    return representation


def get_folder_from_revision(revision):
    """
    Value of the <Version> and <Revision> tokens, padded to three digits so
    revisions sort in order in a file browser.
    """
    return str(revision).zfill(3)


def join_path(left, right, sep=os.sep):
    """
    Join two path fragments, skipping the separator when one is empty.
    """
    if left == "":
        return right
    if right == "":
        return left
    return f"{left}{sep}{right}"


def apply_style(file_name, style):
    """
    Apply the case a tree asks for. Any other value than uppercase or
    lowercase leaves the name untouched, which is how a tree opts out.
    """
    if style == "uppercase":
        file_name = file_name.upper()

    elif style == "lowercase":
        file_name = file_name.lower()

    return file_name


class PathTokens(object):
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
    Resolve the shot task a working file path points at, by matching the
    path against the project's shot template.
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
    Resolve the asset task a working file path points at, by matching the
    path against the project's asset template.
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
    Map each template token to the value found at the same position in the
    path. A token may carry a prefix and a suffix (`v<Version>` matching
    `v003` yields `003`); the first occurrence of a token wins.
    """
    data_names = OrderedDict()
    max_count = min(len(elements), len(template_elements))
    for i, template_element in enumerate(template_elements):
        if i == max_count:
            break

        # Use prefix and suffix to get only the token value.
        # For example, for `v<Version>` and `v003`, the result will be `003`
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
    Return the shot folder template of given tree, empty when absent.
    """
    return tree[mode]["folder_path"].get("shot", "")


def get_asset_path_template(tree, mode="working"):
    """
    Return the asset folder template of given tree, empty when absent.
    """
    return tree[mode]["folder_path"].get("asset", "")


def get_shot_template_folders(project, mode="working", sep="/"):
    """
    Split the project's shot template into its folder elements.
    """
    tree = get_tree_from_project(project)
    template = get_shot_path_template(tree, mode)
    return template.split(sep)


def get_asset_template_folders(project, mode="working", sep="/"):
    """
    Split the project's asset template into its folder elements.
    """
    tree = get_tree_from_project(project)
    template = get_asset_path_template(tree, mode)
    return template.split(sep)


def get_path_folders(project, file_path, mode="working", sep="/"):
    """
    Split a file path into folder elements, root stripped, so it lines up
    with the template elements.
    """
    tree = get_tree_from_project(project)
    root = get_root_path(tree, mode, sep)
    file_path = file_path[len(root) :]
    return file_path.split(sep)


def _get_child_by_name(name, entity_type_id, constraints, parent_token):
    """
    Return the entity of given type named by a path token, narrowed by its
    parent when the path already resolved one.
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
    Get the first corresponding data using the given type and value tokens.
    """
    if not constraints:
        constraints = {}
    data = None

    if type_token == PathTokens.ASSET:
        # An asset depends on a project and an asset type
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
        # An episode depends on a project
        if not constraints.get(PathTokens.PROJECT):
            return None

        data = Entity.get_by(
            Entity.name.ilike(value_token),
            entity_type_id=shots_service.get_episode_type()["id"],
            project_id=constraints[PathTokens.PROJECT],
        )

    elif type_token == PathTokens.SEQUENCE:
        # A sequence depends on a project, and on an episode only in a
        # production that has any: the episode narrows the search when the
        # path carried one. Requiring it made every path of a flat
        # production stop here, since neither shipped tree puts an
        # <Episode> token in front of the sequence.
        data = _get_child_by_name(
            value_token,
            shots_service.get_sequence_type()["id"],
            constraints,
            parent_token=PathTokens.EPISODE,
        )

    elif type_token == PathTokens.SCENE:
        # A scene depends on a project, and on the sequence it sits in when
        # the path carried one.
        data = _get_child_by_name(
            value_token,
            shots_service.get_scene_type()["id"],
            constraints,
            parent_token=PathTokens.SEQUENCE,
        )

    elif type_token == PathTokens.OUTPUT_TYPE:
        data = OutputType.get_by(OutputType.name.ilike(value_token))

    elif type_token == PathTokens.SHOT:
        # A shot depends on a project and a sequence
        if not constraints.get(PathTokens.PROJECT) or not constraints.get(
            PathTokens.SEQUENCE
        ):
            return None

        data = Entity.get_by(
            Entity.name.ilike(value_token),
            entity_type_id=shots_service.get_shot_type()["id"],
            parent_id=constraints[PathTokens.SEQUENCE],
            project_id=constraints[PathTokens.PROJECT],
        )

    elif type_token == PathTokens.TASK:
        # A task depends on a project, a task type and an entity
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
        # An entity depends on a project and an entity type
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
    Find the shot named by the tokens read from a path, narrowing down episode
    then sequence then shot. A name that resolves to nothing leaves its parent
    at None instead of failing, so a flat production still matches. Only a
    missing shot name is an error.
    """
    episode_id = None
    if len(episode_name) > 0:
        episode = Entity.get_by(
            name=episode_name,
            entity_type_id=shots_service.get_episode_type()["id"],
            project_id=project["id"],
        )
        if episode is not None:
            episode_id = episode.id

    sequence_id = None
    if len(sequence_name) > 0:
        sequence = Entity.get_by(
            name=sequence_name,
            entity_type_id=shots_service.get_sequence_type()["id"],
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
            entity_type_id=shots_service.get_shot_type()["id"],
            parent_id=sequence_id,
            project_id=project["id"],
        )
    else:
        raise WrongPathFormatException("Shot name was not found in given path")
    return shot


def guess_asset(project, asset_type_name, asset_name):
    """
    Find the asset named by the tokens read from a path. The asset type only
    narrows the search: an unknown one leaves it out rather than failing. A
    missing asset name is an error.
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
    Find the task type named by the tokens read from a path. The department
    disambiguates two task types sharing a name across departments, and only
    narrows the search: an unknown one is left out rather than failing, as
    the asset type and the episode are in the two guesses above.
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
    Find the task of given entity and task type. The task name narrows it down
    when the path carries one, productions that name their tasks having
    several for the same type.
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
    Get list of possible project file tree templates matching a file path
    and data ids corresponding to template tokens.

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
        # Apply mode style to file path
        style = tree[mode]["folder_path"].get("style", "")
        root = apply_style(get_root_path(tree, mode, sep), style)
        styled_path = apply_style(file_path, style)

        if not styled_path.startswith(root):
            continue

        styled_path = styled_path[len(root) :]

        # Try to get template data from path
        for template, template_path in tree[mode]["folder_path"].items():
            template_elements = template_path.split(sep)
            elements = styled_path.split(sep)

            # Case when template doesn't match given file path content
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

            # Fill template data dictionary following tokens order in
            # template path (left to right): some data needs a previous data
            # to be found.
            # This prevents getting wrong data in database, like a data
            # with same name in other project.
            for template_element in template_elements:
                # Get template_element corresponding token.
                # Some template_element don't have a corresponding token,
                # like "05_publish" folder, for example.
                for token, token_value in tokens.items():
                    if f"<{token}>" in template_element:
                        break
                else:
                    continue

                # Try to get data from database using token and its value
                data = get_data_from_token(token, token_value, template_data)

                # Stop trying to get data from given template on latest valid
                # data found.
                if not data:
                    break

                # The production is the one the caller named, and the one
                # the route checked their permission against. A path naming
                # another production is a path for someone else: it must
                # not come back filled with that production's ids.
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
