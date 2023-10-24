import os
import re
import orjson as json

from collections import OrderedDict
from slugify import slugify

from zou.app import app

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

    return "%s" % file_name


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
        file_name += "_[1-%s]" % nb_elements

    return "%s" % file_name


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
        file_name += "_[1-%s]" % nb_elements

    return "%s" % file_name


def get_working_folder_path(
    task,
    mode="working",
    software=None,
    output_type=None,
    name="",
    revision=1,
    sep=os.sep,
):
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
    return projects_service.get_project(entity["project_id"])


def get_tree_from_project(project):
    return project["file_tree"]


def get_tree_from_file(tree_name):
    try:
        tree_path = os.path.join(
            os.path.join(app.root_path, "file_trees"), "%s.json" % tree_name
        )
        tree_string = open(tree_path).read()
    except IOError:
        raise WrongFileTreeFileException(
            "File Tree file not found: %s." % tree_path
        )
    return json.loads(tree_string)


def get_folder_path_template(tree, mode, entity):
    try:
        if entity["type"] == "AssetInstance":
            if entity.get("target_asset_id", None) is not None:
                return tree[mode]["folder_path"]["instance_asset"]
            else:
                return tree[mode]["folder_path"]["instance"]
        elif shots_service.is_shot(entity):
            return tree[mode]["folder_path"]["shot"]
        elif shots_service.is_sequence(entity):
            return tree[mode]["folder_path"]["sequence"]
        elif shots_service.is_scene(entity):
            return tree[mode]["folder_path"]["scene"]
        elif shots_service.is_episode(entity):
            return tree[mode]["folder_path"]["episode"]
        else:
            return tree[mode]["folder_path"]["asset"]
    except KeyError:
        raise MalformedFileTreeException


def get_file_name_template(tree, mode, entity):
    try:
        if entity["type"] == "AssetInstance":
            if entity.get("target_asset_id", None) is not None:
                return tree[mode]["file_name"]["instance_asset"]
            else:
                return tree[mode]["file_name"]["instance"]
        elif shots_service.is_shot(entity):
            return tree[mode]["file_name"]["shot"]
        elif shots_service.is_sequence(entity):
            return tree[mode]["file_name"]["sequence"]
        elif shots_service.is_scene(entity):
            return tree[mode]["file_name"]["scene"]
        elif shots_service.is_episode(entity):
            return tree[mode]["file_name"]["episode"]
        else:
            return tree[mode]["file_name"]["asset"]
    except KeyError:
        raise MalformedFileTreeException


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
    return folder_path.replace("/", sep)


def get_root_path(tree, mode, sep):
    if tree is None:
        raise MalformedFileTreeException(
            "No tree can be found for given project."
        )

    if mode not in tree:
        raise MalformedFileTreeException(
            "Mode %s cannot be found on given tree." % mode
        )

    try:
        mountpoint = tree[mode]["mountpoint"]
        root = tree[mode]["root"]
    except KeyError:
        raise MalformedFileTreeException(
            "Can't find given mode (%s) in given tree." % mode
        )
    if root:
        return "%s%s%s%s" % (mountpoint, sep, root, sep)
    else:
        return "%s%s" % (mountpoint, sep)


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
        raise MalformedFileTreeException("Unknown data type: %s." % datatype)

    return folder


def get_folder_from_project(entity, field="name"):
    project = get_project(entity)
    return project[field]


def get_folder_from_task(task, field="name"):
    return task[field]


def get_folder_from_shot(shot, field="name"):
    return shot[field]


def get_folder_from_output_type(output_type, field="name"):
    if output_type is None:
        output_type = files_service.get_or_create_output_type("Geometry")

    return output_type[field].lower()


def get_folder_from_department(task, task_type, field="name"):
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
    folder = ""
    if task_type is None and task is not None:
        task_type = tasks_service.get_task_type(task["task_type_id"])
        if task_type is not None:
            folder = task_type[field]
    elif task_type is not None:
        folder = task_type[field]
    return folder


def get_folder_from_asset(asset, field="name"):
    folder = ""
    if asset is not None:
        folder = asset[field]
    return folder


def get_folder_from_sequence(entity, field="name"):
    if shots_service.is_shot(entity) or shots_service.is_scene(entity):
        sequence = shots_service.get_sequence_from_shot(entity)
        sequence_name = sequence[field]
    elif shots_service.is_sequence(entity):
        sequence_name = entity[field]
    else:
        sequence_name = ""

    if "Seq" in sequence_name:
        sequence_number = sequence.name[3:]
        sequence_name = "S%s" % sequence_number.zfill(3)
    return sequence_name


def get_folder_from_episode(entity, field="name"):
    if shots_service.is_shot(entity) or shots_service.is_scene(entity):
        sequence = shots_service.get_sequence_from_shot(entity)
    elif shots_service.is_sequence(entity):
        sequence = entity

    try:
        episode = shots_service.get_episode_from_sequence(sequence)
        episode_name = episode[field]
    except BaseException:
        episode_name = "e001"

    return episode_name


def get_folder_from_temporal_entity(entity, field="name"):
    if entity is not None:
        entity = entities_service.get_entity(entity["id"])
        folder = entity[field]
    else:
        raise MalformedFileTreeException("Given temporal entity is null.")
    return folder


def get_folder_from_temporal_entity_type(entity, field="name"):
    if entity is not None:
        entity_type = entities_service.get_entity_type(
            entity["entity_type_id"]
        )
        folder = entity_type[field].lower()
    else:
        raise MalformedFileTreeException("Given temporal entity type is null.")
    return folder


def get_folder_from_asset_type(asset, field="name"):
    if asset is not None:
        asset_type = assets_service.get_asset_type(asset["entity_type_id"])
        folder = asset_type[field]
    else:
        raise MalformedFileTreeException("Given asset is null.")
    return folder


def get_folder_from_software(software, field="name"):
    if software is None:
        software = files_service.get_or_create_software(
            "3dsmax", "max", ".max"
        )
    return software[field]


def get_folder_from_scene(scene, field="name"):
    folder = ""
    if scene is not None:
        folder = scene[field]
    return folder


def get_folder_from_asset_instance(asset_instance, field):
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
    return representation


def get_folder_from_revision(revision):
    return str(revision).zfill(3)


def join_path(left, right, sep=os.sep):
    if left == "":
        return right
    elif right == "":
        return left
    else:
        return "%s%s%s" % (left, sep, right)


def apply_style(file_name, style):
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
    template_elements = get_shot_template_folders(project, mode, sep)
    elements = get_path_folders(project, file_path, mode, sep)

    if len(elements) != len(template_elements):
        tree = get_tree_from_project(project)
        template = get_shot_path_template(tree, mode)
        raise WrongPathFormatException(
            "%s doesn't match %s" % (file_path, template)
        )

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
    template_elements = get_asset_template_folders(project, mode, sep)
    elements = get_path_folders(project, file_path, mode, sep)

    if len(elements) != len(template_elements):
        tree = get_tree_from_project(project)
        template = get_asset_path_template(tree, mode)
        raise WrongPathFormatException(
            "%s doesn't match %s" % (file_path, template)
        )

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
                    "{} doesn't match {}".format(elements, template_elements)
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
    return tree[mode]["folder_path"].get("shot", "")


def get_asset_path_template(tree, mode="working"):
    return tree[mode]["folder_path"].get("asset", "")


def get_shot_template_folders(project, mode="working", sep="/"):
    tree = get_tree_from_project(project)
    template = get_shot_path_template(tree, mode)
    return template.split(sep)


def get_asset_template_folders(project, mode="working", sep="/"):
    tree = get_tree_from_project(project)
    template = get_asset_path_template(tree, mode)
    return template.split(sep)


def get_path_folders(project, file_path, mode="working", sep="/"):
    tree = get_tree_from_project(project)
    root = get_root_path(tree, mode, sep)
    file_path = file_path[len(root) :]
    return file_path.split(sep)


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
            name=Entity.name.ilike(value_token),
            entity_type_id=constraints[PathTokens.ASSET_TYPE],
            project_id=constraints[PathTokens.PROJECT],
        )

    elif type_token == PathTokens.ASSET_TYPE:
        data = EntityType.get_by(name=EntityType.name.ilike(value_token))

    elif type_token == PathTokens.DEPARTMENT:
        data = Department.get_by(name=Department.name.ilike(value_token))

    elif type_token == PathTokens.EPISODE:
        # An episode depends on a project
        if not constraints.get(PathTokens.PROJECT):
            return None

        data = Entity.get_by(
            name=Entity.name.ilike(value_token),
            entity_type_id=shots_service.get_episode_type()["id"],
            project_id=constraints[PathTokens.PROJECT],
        )

    elif type_token == PathTokens.SEQUENCE:
        # A sequence depends on a project and an episode
        if not constraints.get(PathTokens.PROJECT) or not constraints.get(
            PathTokens.EPISODE
        ):
            return None

        data = Entity.get_by(
            name=Entity.name.ilike(value_token),
            entity_type_id=shots_service.get_sequence_type()["id"],
            parent_id=constraints[PathTokens.EPISODE],
            project_id=constraints[PathTokens.PROJECT],
        )

    elif type_token == PathTokens.SCENE:
        # A scene depends on a project and a sequence
        if not constraints.get(PathTokens.PROJECT) or not constraints.get(
            PathTokens.EPISODE
        ):
            return None

        data = Entity.get_by(
            name=Entity.name.ilike(value_token),
            entity_type_id=shots_service.get_scene_type()["id"],
            project_id=constraints[PathTokens.PROJECT],
            parent_id=constraints[PathTokens.SEQUENCE],
        )

    elif type_token == PathTokens.OUTPUT_TYPE:
        data = OutputType.get_by(name=OutputType.name.ilike(value_token))

    elif type_token == PathTokens.SHOT:
        # A shot depends on a project and a sequence
        if not constraints.get(PathTokens.PROJECT) or not constraints.get(
            PathTokens.SEQUENCE
        ):
            return None

        data = Entity.get_by(
            name=Entity.name.ilike(value_token),
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

        kwargs = {
            "name": Task.name.ilike(value_token),
            "task_type_id": constraints[PathTokens.TASK_TYPE],
            "project_id": constraints[PathTokens.PROJECT],
        }

        for entity in [PathTokens.SCENE, PathTokens.ASSET, PathTokens.SHOT]:
            if constraints.get(entity):
                kwargs["entity_id"] = constraints[entity]
                break
        else:
            return None

        data = Task.get_by(**kwargs)

    elif type_token == PathTokens.TASK_TYPE:
        data = TaskType.get_by(name=TaskType.name.ilike(value_token))

    elif type_token == PathTokens.PROJECT:
        data = Project.get_by(name=Project.name.ilike(value_token))

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
        data = EntityType.get_by(name=EntityType.name.ilike(value_token))

    elif type_token == PathTokens.ENTITY:
        # An entity depends on a project and an entity type
        if not constraints.get(PathTokens.PROJECT) or not constraints.get(
            PathTokens.ENTITY_TYPE
        ):
            return None

        data = Entity.get_by(
            name=Entity.name.ilike(value_token),
            entity_type_id=constraints[PathTokens.ENTITY_TYPE],
            project_id=constraints[PathTokens.PROJECT],
        )

    elif type_token == PathTokens.INSTANCE:
        if not constraints.get(PathTokens.EPISODE):
            return None

        data = AssetInstance.get_by(
            name=AssetInstance.name.ilike(value_token),
            episode_id=constraints.get(PathTokens.EPISODE),
        )

    return data


def guess_shot(project, episode_name, sequence_name, shot_name):
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
    criterions = {"name": task_type_name}
    if len(department_name) > 0:
        criterions["department_id"] = Department.get_by(
            name=department_name
        ).id

    return TaskType.get_by(**criterions)


def guess_task(entity, task_type, task_name):
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
                    if "<{}>".format(token) in template_element:
                        break
                else:
                    continue

                # Try to get data from database using token and its value
                data = get_data_from_token(token, token_value, template_data)

                # Stop trying to get data from given template on latest valid
                # data found.
                if not data:
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
