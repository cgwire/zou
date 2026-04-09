from sqlalchemy_utils import UUIDType, ChoiceType

from sqlalchemy.dialects.postgresql import JSONB

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

from zou.app.models.person import ROLE_TYPES
from zou.app.models.project import PROJECT_STYLES


class ProjectTemplateTaskTypeLink(db.Model, BaseMixin, SerializerMixin):
    __tablename__ = "project_template_task_type_link"
    project_template_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("project_template.id"),
        primary_key=True,
        index=True,
    )
    task_type_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("task_type.id"),
        primary_key=True,
        index=True,
    )
    priority = db.Column(db.Integer, default=None)

    __table_args__ = (
        db.UniqueConstraint(
            "project_template_id",
            "task_type_id",
            name="project_template_tasktype_uc",
        ),
    )


class ProjectTemplateTaskStatusLink(db.Model, BaseMixin, SerializerMixin):
    __tablename__ = "project_template_task_status_link"
    project_template_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("project_template.id"),
        primary_key=True,
        index=True,
    )
    task_status_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("task_status.id"),
        primary_key=True,
        index=True,
    )
    priority = db.Column(db.Integer, default=None)
    roles_for_board = db.Column(
        db.ARRAY(ChoiceType(ROLE_TYPES)),
        default=["user", "admin", "supervisor", "manager", "vendor"],
    )

    __table_args__ = (
        db.UniqueConstraint(
            "project_template_id",
            "task_status_id",
            name="project_template_taskstatus_uc",
        ),
    )


class ProjectTemplateAssetTypeLink(db.Model):
    __tablename__ = "project_template_asset_type_link"
    project_template_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("project_template.id"),
        primary_key=True,
        index=True,
    )
    asset_type_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("entity_type.id"),
        primary_key=True,
        index=True,
    )


class ProjectTemplateStatusAutomationLink(db.Model):
    __tablename__ = "project_template_status_automation_link"
    project_template_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("project_template.id"),
        primary_key=True,
        index=True,
    )
    status_automation_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("status_automation.id"),
        primary_key=True,
        index=True,
    )


class ProjectTemplate(db.Model, BaseMixin, SerializerMixin):
    """
    A reusable snapshot of a project's configuration (task types, task
    statuses, status automations, asset types, metadata descriptors and
    production settings). It does not contain any production data (no tasks,
    no entities, no team).
    """

    name = db.Column(db.String(80), nullable=False, unique=True, index=True)
    description = db.Column(db.Text())

    # Production settings (mirror of Project)
    fps = db.Column(db.String(10), default="25")
    ratio = db.Column(db.String(10), default="16:9")
    resolution = db.Column(db.String(12), default="1920x1080")
    production_type = db.Column(db.String(20), default="short")
    production_style = db.Column(
        ChoiceType(PROJECT_STYLES), default="2d3d", nullable=False
    )
    max_retakes = db.Column(db.Integer, default=0)
    is_clients_isolated = db.Column(db.Boolean(), default=False)
    is_preview_download_allowed = db.Column(db.Boolean(), default=False)
    is_set_preview_automated = db.Column(db.Boolean(), default=False)
    is_publish_default_for_artists = db.Column(db.Boolean(), default=False)
    homepage = db.Column(db.String(80), default="assets")
    hd_bitrate_compression = db.Column(db.Integer, default=28)
    ld_bitrate_compression = db.Column(db.Integer, default=6)
    file_tree = db.Column(JSONB)
    data = db.Column(JSONB)

    # Metadata descriptor snapshot stored as JSONB to avoid creating
    # MetadataDescriptor rows that aren't linked to any project. Each entry
    # has the shape:
    #   {
    #     "entity_type": "Asset",
    #     "name": "Difficulty",
    #     "field_name": "difficulty",
    #     "data_type": "list",
    #     "choices": ["easy", "medium", "hard"],
    #     "for_client": false,
    #     "departments": ["<department_id>", ...],
    #     "position": 1
    #   }
    metadata_descriptors = db.Column(JSONB, default=list)

    # Relationships
    task_types = db.relationship(
        "TaskType", secondary=ProjectTemplateTaskTypeLink.__table__
    )
    task_statuses = db.relationship(
        "TaskStatus", secondary=ProjectTemplateTaskStatusLink.__table__
    )
    asset_types = db.relationship(
        "EntityType", secondary=ProjectTemplateAssetTypeLink.__table__
    )
    status_automations = db.relationship(
        "StatusAutomation",
        secondary=ProjectTemplateStatusAutomationLink.__table__,
    )

    def set_task_types(self, task_type_ids):
        return self.set_links(
            task_type_ids,
            ProjectTemplateTaskTypeLink,
            "project_template_id",
            "task_type_id",
        )

    def set_task_statuses(self, task_status_ids):
        return self.set_links(
            task_status_ids,
            ProjectTemplateTaskStatusLink,
            "project_template_id",
            "task_status_id",
        )

    def set_asset_types(self, asset_type_ids):
        return self.set_links(
            asset_type_ids,
            ProjectTemplateAssetTypeLink,
            "project_template_id",
            "asset_type_id",
        )

    def set_status_automations(self, status_automation_ids):
        return self.set_links(
            status_automation_ids,
            ProjectTemplateStatusAutomationLink,
            "project_template_id",
            "status_automation_id",
        )
