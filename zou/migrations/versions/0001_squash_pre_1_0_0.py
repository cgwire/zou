"""Squash all pre-1.0.0 migrations into a single initial schema

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-04-23 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlalchemy_utils
import uuid

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "asset_instance",
        sa.Column(
            "asset_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("name", sa.String(length=80)),
        sa.Column("number", sa.Integer()),
        sa.Column("description", sa.String(length=200)),
        sa.Column("active", sa.Boolean()),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "scene_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "target_asset_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "entity_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "entity_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["scene_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["entity_type_id"], ["entity_type.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["target_asset_id"], ["entity.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id",
            "target_asset_id",
            "scene_id",
            "number",
            name="asset_instance_uc",
        ),
    )
    op.create_table(
        "chat",
        sa.Column(
            "object_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("object_type", sa.String(length=80), nullable=False),
        sa.Column("last_message", sa.DateTime(timezone=False)),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "custom_action",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("url", sa.String(length=400)),
        sa.Column("entity_type", sa.String(length=40)),
        sa.Column("is_ajax", sa.Boolean()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "data_import_error",
        sa.Column(
            "event_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=7)),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "department",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("archived", sa.Boolean()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "entity",
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("code", sa.String(length=160)),
        sa.Column("description", sa.String(length=None)),
        sa.Column("shotgun_id", sa.Integer()),
        sa.Column("canceled", sa.Boolean()),
        sa.Column("nb_frames", sa.Integer()),
        sa.Column("nb_entities_out", sa.Integer()),
        sa.Column("is_casting_standby", sa.Boolean()),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column("status", ChoiceType(length=255), nullable=False),
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "entity_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "source_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "preview_file_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "ready_for",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "created_by",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["parent_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["person.id"]),
        sa.ForeignKeyConstraint(["preview_file_id"], ["preview_file.id"]),
        sa.ForeignKeyConstraint(["entity_type_id"], ["entity_type.id"]),
        sa.ForeignKeyConstraint(["ready_for"], ["task_type.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name",
            "project_id",
            "entity_type_id",
            "parent_id",
            name="entity_uc",
        ),
    )
    op.create_table(
        "entity_type",
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("short_name", sa.String(length=20)),
        sa.Column("description", sa.String(length=None)),
        sa.Column("archived", sa.Boolean()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "file_status",
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "hardware_item",
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("short_name", sa.String(length=20), nullable=False),
        sa.Column("archived", sa.Boolean()),
        sa.Column("monthly_cost", sa.Integer()),
        sa.Column("inventory_amount", sa.Integer()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "organisation",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("hours_by_day", sa.Float(), nullable=False),
        sa.Column("has_avatar", sa.Boolean()),
        sa.Column("use_original_file_name", sa.Boolean()),
        sa.Column("timesheets_locked", sa.Boolean()),
        sa.Column("format_duration_in_hours", sa.Boolean()),
        sa.Column("hd_by_default", sa.Boolean()),
        sa.Column("chat_token_slack", sa.String(length=80)),
        sa.Column("chat_webhook_mattermost", sa.String(length=80)),
        sa.Column("chat_token_discord", sa.String(length=80)),
        sa.Column("dark_theme_by_default", sa.Boolean()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "output_file",
        sa.Column("shotgun_id", sa.Integer()),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("canceled", sa.Boolean(), nullable=False),
        sa.Column("size", sa.Integer()),
        sa.Column("checksum", sa.String(length=32)),
        sa.Column("description", sa.String(length=None)),
        sa.Column("comment", sa.String(length=None)),
        sa.Column("extension", sa.String(length=10)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("representation", sa.String(length=20)),
        sa.Column("nb_elements", sa.Integer()),
        sa.Column("source", sa.String(length=40)),
        sa.Column("path", sa.String(length=400)),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "file_status_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "asset_instance_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "output_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "task_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "source_file_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "temporal_entity_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["task_type_id"], ["task_type.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["source_file_id"], ["working_file.id"]),
        sa.ForeignKeyConstraint(["file_status_id"], ["file_status.id"]),
        sa.ForeignKeyConstraint(["output_type_id"], ["output_type.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["asset_instance_id"], ["asset_instance.id"]),
        sa.ForeignKeyConstraint(["temporal_entity_id"], ["entity.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name",
            "entity_id",
            "asset_instance_id",
            "output_type_id",
            "task_type_id",
            "temporal_entity_id",
            "representation",
            "revision",
            name="output_file_uc",
        ),
    )
    op.create_table(
        "output_type",
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("short_name", sa.String(length=20), nullable=False),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "plugin",
        sa.Column("plugin_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=None)),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("maintainer_name", sa.String(length=200), nullable=False),
        sa.Column("maintainer_email", EmailType(length=255)),
        sa.Column("website", URLType()),
        sa.Column("license", sa.String(length=80), nullable=False),
        sa.Column("revision", sa.String(length=12)),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "preview_background_file",
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("archived", sa.Boolean()),
        sa.Column("is_default", sa.Boolean()),
        sa.Column("original_name", sa.String(length=250)),
        sa.Column("extension", sa.String(length=6)),
        sa.Column("file_size", sa.BigInteger()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "preview_file",
        sa.Column("name", sa.String(length=250)),
        sa.Column("original_name", sa.String(length=250)),
        sa.Column("revision", sa.Integer()),
        sa.Column("position", sa.Integer()),
        sa.Column("extension", sa.String(length=6)),
        sa.Column("description", sa.String(length=None)),
        sa.Column("path", sa.String(length=400)),
        sa.Column("source", sa.String(length=40)),
        sa.Column("file_size", sa.BigInteger()),
        sa.Column("status", ChoiceType(length=255), nullable=False),
        sa.Column("validation_status", ChoiceType(length=255), nullable=False),
        sa.Column("annotations", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("duration", sa.Float()),
        sa.Column(
            "task_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "source_file_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column("shotgun_id", sa.Integer()),
        sa.Column("is_movie", sa.Boolean()),
        sa.Column("url", sa.String(length=600)),
        sa.Column("uploaded_movie_url", sa.String(length=600)),
        sa.Column("uploaded_movie_name", sa.String(length=150)),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["source_file_id"], ["output_file.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "task_id", "revision", name="preview_uc"),
        sa.UniqueConstraint("shotgun_id"),
    )
    op.create_table(
        "project_status",
        sa.Column("name", sa.String(length=20), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "software",
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("short_name", sa.String(length=20), nullable=False),
        sa.Column("archived", sa.Boolean()),
        sa.Column("version", sa.String(length=20)),
        sa.Column("file_extension", sa.String(length=20), nullable=False),
        sa.Column(
            "secondary_extensions", postgresql.JSONB(astext_type=sa.Text())
        ),
        sa.Column("monthly_cost", sa.Integer()),
        sa.Column("inventory_amount", sa.Integer()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "studio",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("archived", sa.Boolean()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "task",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=None)),
        sa.Column("priority", sa.Integer()),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("duration", sa.Float()),
        sa.Column("estimation", sa.Float()),
        sa.Column("completion_rate", sa.Integer()),
        sa.Column("retake_count", sa.Integer()),
        sa.Column("sort_order", sa.Integer()),
        sa.Column("start_date", sa.DateTime(timezone=False)),
        sa.Column("due_date", sa.DateTime(timezone=False)),
        sa.Column("real_start_date", sa.DateTime(timezone=False)),
        sa.Column("end_date", sa.DateTime(timezone=False)),
        sa.Column("done_date", sa.DateTime(timezone=False)),
        sa.Column("last_comment_date", sa.DateTime(timezone=False)),
        sa.Column("nb_assets_ready", sa.Integer()),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("nb_drawings", sa.Integer()),
        sa.Column("shotgun_id", sa.Integer()),
        sa.Column(
            "last_preview_file_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "task_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "task_status_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "entity_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "assigner_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["task_status_id"], ["task_status.id"]),
        sa.ForeignKeyConstraint(["assigner_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["task_type_id"], ["task_type.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name", "project_id", "task_type_id", "entity_id", name="task_uc"
        ),
    )
    op.create_table(
        "task_status",
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("archived", sa.Boolean()),
        sa.Column("short_name", sa.String(length=10), nullable=False),
        sa.Column("description", sa.String(length=None)),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("priority", sa.Integer()),
        sa.Column("is_done", sa.Boolean()),
        sa.Column("is_artist_allowed", sa.Boolean()),
        sa.Column("is_client_allowed", sa.Boolean()),
        sa.Column("is_retake", sa.Boolean()),
        sa.Column("is_feedback_request", sa.Boolean()),
        sa.Column("is_default", sa.Boolean()),
        sa.Column("is_wip", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("shotgun_id", sa.Integer()),
        sa.Column(
            "for_concept", sa.Boolean(), server_default=sa.text("false")
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "working_file",
        sa.Column("shotgun_id", sa.Integer()),
        sa.Column("name", sa.String(length=250)),
        sa.Column("description", sa.String(length=None)),
        sa.Column("comment", sa.String(length=None)),
        sa.Column("revision", sa.Integer()),
        sa.Column("size", sa.Integer()),
        sa.Column("checksum", sa.Integer()),
        sa.Column("path", sa.String(length=400)),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "task_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "entity_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "software_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["software_id"], ["software.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name", "task_id", "entity_id", "revision", name="working_file_uc"
        ),
    )
    op.create_table(
        "asset_instance_link",
        sa.Column(
            "entity_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "asset_instance_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_instance_id"], ["asset_instance.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"]),
        sa.PrimaryKeyConstraint("entity_id", "asset_instance_id"),
    )
    op.create_table(
        "entity_concept_link",
        sa.Column(
            "entity_in_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "entity_out_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["entity_out_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["entity_in_id"], ["entity.id"]),
        sa.PrimaryKeyConstraint("entity_in_id", "entity_out_id", "id"),
    )
    op.create_table(
        "entity_link",
        sa.Column(
            "entity_in_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "entity_out_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("nb_occurences", sa.Integer()),
        sa.Column("label", sa.String(length=80)),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["entity_out_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["entity_in_id"], ["entity.id"]),
        sa.PrimaryKeyConstraint("entity_in_id", "entity_out_id", "id"),
        sa.UniqueConstraint(
            "entity_in_id", "entity_out_id", name="entity_link_uc"
        ),
    )
    op.create_table(
        "hardware_item_department_link",
        sa.Column(
            "department_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "hardware_item_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["hardware_item_id"], ["hardware_item.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("department_id", "hardware_item_id", "id"),
        sa.UniqueConstraint(
            "hardware_item_id",
            "department_id",
            name="hardware_item_department_link_uc",
        ),
    )
    op.create_table(
        "person",
        sa.Column("first_name", sa.String(length=80), nullable=False),
        sa.Column("last_name", sa.String(length=80), nullable=False),
        sa.Column("email", EmailType(length=255)),
        sa.Column("phone", sa.String(length=30)),
        sa.Column("contract_type", ChoiceType(length=255), nullable=False),
        sa.Column("active", sa.Boolean()),
        sa.Column("archived", sa.Boolean()),
        sa.Column("last_presence", sa.Date()),
        sa.Column("password", sa.LargeBinary()),
        sa.Column("desktop_login", sa.String(length=80)),
        sa.Column("login_failed_attemps", sa.Integer()),
        sa.Column("last_login_failed", sa.DateTime(timezone=False)),
        sa.Column("totp_enabled", sa.Boolean()),
        sa.Column("totp_secret", sa.String(length=32)),
        sa.Column("email_otp_enabled", sa.Boolean()),
        sa.Column("email_otp_secret", sa.String(length=32)),
        sa.Column("fido_enabled", sa.Boolean()),
        sa.Column("fido_credentials", ARRAY(JSONB(astext_type=Text()))),
        sa.Column("otp_recovery_codes", ARRAY(LargeBinary(length=60))),
        sa.Column(
            "preferred_two_factor_authentication", ChoiceType(length=255)
        ),
        sa.Column("shotgun_id", sa.Integer()),
        sa.Column("timezone", TimezoneType(length=50)),
        sa.Column("locale", LocaleType(length=10)),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("role", ChoiceType(length=255), nullable=False),
        sa.Column("position", ChoiceType(length=255)),
        sa.Column("seniority", ChoiceType(length=255)),
        sa.Column("daily_salary", sa.Integer()),
        sa.Column("has_avatar", sa.Boolean()),
        sa.Column("notifications_enabled", sa.Boolean()),
        sa.Column("notifications_slack_enabled", sa.Boolean()),
        sa.Column("notifications_slack_userid", sa.String(length=60)),
        sa.Column("notifications_mattermost_enabled", sa.Boolean()),
        sa.Column("notifications_mattermost_userid", sa.String(length=60)),
        sa.Column("notifications_discord_enabled", sa.Boolean()),
        sa.Column("notifications_discord_userid", sa.String(length=60)),
        sa.Column("is_bot", sa.Boolean(), nullable=False),
        sa.Column("jti", sa.String(length=60)),
        sa.Column("expiration_date", sa.Date()),
        sa.Column(
            "studio_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column("is_generated_from_ldap", sa.Boolean()),
        sa.Column("ldap_uid", sa.String(length=60)),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["studio_id"], ["studio.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti"),
        sa.UniqueConstraint("shotgun_id"),
        sa.UniqueConstraint("ldap_uid"),
    )
    op.create_table(
        "project",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=80)),
        sa.Column("description", sa.String(length=None)),
        sa.Column("shotgun_id", sa.Integer()),
        sa.Column("file_tree", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("has_avatar", sa.Boolean()),
        sa.Column("fps", sa.String(length=10)),
        sa.Column("ratio", sa.String(length=10)),
        sa.Column("resolution", sa.String(length=12)),
        sa.Column("production_type", sa.String(length=20)),
        sa.Column("production_style", ChoiceType(length=255), nullable=False),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("man_days", sa.Integer()),
        sa.Column("nb_episodes", sa.Integer()),
        sa.Column("episode_span", sa.Integer()),
        sa.Column("max_retakes", sa.Integer()),
        sa.Column("is_clients_isolated", sa.Boolean()),
        sa.Column("is_preview_download_allowed", sa.Boolean()),
        sa.Column("is_set_preview_automated", sa.Boolean()),
        sa.Column("homepage", sa.String(length=80)),
        sa.Column("is_publish_default_for_artists", sa.Boolean()),
        sa.Column("hd_bitrate_compression", sa.Integer()),
        sa.Column("ld_bitrate_compression", sa.Integer()),
        sa.Column(
            "project_status_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "default_preview_background_file_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "from_schedule_version_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["project_status_id"], ["project_status.id"]),
        sa.ForeignKeyConstraint(
            ["from_schedule_version_id"], ["production_schedule_version.id"]
        ),
        sa.ForeignKeyConstraint(
            ["default_preview_background_file_id"],
            ["preview_background_file.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "salary_scale",
        sa.Column(
            "department_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("position", ChoiceType(length=255)),
        sa.Column("seniority", ChoiceType(length=255)),
        sa.Column("salary", sa.Integer(), nullable=False),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "software_department_link",
        sa.Column(
            "department_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "software_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.ForeignKeyConstraint(["software_id"], ["software.id"]),
        sa.PrimaryKeyConstraint("department_id", "software_id", "id"),
        sa.UniqueConstraint(
            "department_id", "software_id", name="software_department_link_uc"
        ),
    )
    op.create_table(
        "task_type",
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("short_name", sa.String(length=20)),
        sa.Column("description", sa.String(length=None)),
        sa.Column("color", sa.String(length=7)),
        sa.Column("priority", sa.Integer()),
        sa.Column("for_entity", sa.String(length=30)),
        sa.Column("allow_timelog", sa.Boolean()),
        sa.Column("archived", sa.Boolean()),
        sa.Column("shotgun_id", sa.Integer()),
        sa.Column(
            "department_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name", "for_entity", "department_id", name="task_type_uc"
        ),
    )
    op.create_table(
        "api_event",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "user_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "budget",
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("currency", sa.String(length=3)),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chat_message",
        sa.Column(
            "chat_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("text", sa.String(length=None)),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["chat_id"], ["chat.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chat_participant",
        sa.Column(
            "chat_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chat.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("chat_id", "person_id"),
    )
    op.create_table(
        "comment",
        sa.Column("shotgun_id", sa.Integer()),
        sa.Column(
            "object_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("object_type", sa.String(length=80), nullable=False),
        sa.Column("text", sa.String(length=None)),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("replies", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("checklist", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("pinned", sa.Boolean()),
        sa.Column("links", ARRAY(String())),
        sa.Column(
            "task_status_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "editor_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "preview_file_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["task_status_id"], ["task_status.id"]),
        sa.ForeignKeyConstraint(["editor_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["preview_file_id"], ["preview_file.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "day_off",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=None)),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "date", name="day_off_uc"),
    )
    op.create_table(
        "department_link",
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "department_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("person_id", "department_id"),
        sa.UniqueConstraint(
            "person_id", "department_id", name="department_link_uc"
        ),
    )
    op.create_table(
        "desktop_login_log",
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("date", sa.DateTime(timezone=False), nullable=False),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "entity_version",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "entity_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "login_log",
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("ip_address", IPAddressType(length=50)),
        sa.Column("origin", ChoiceType(length=255)),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "metadata_descriptor",
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("data_type", ChoiceType(length=255)),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        sa.Column("choices", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("for_client", sa.Boolean()),
        sa.Column("position", sa.Integer()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "entity_type",
            "field_name",
            name="metadata_descriptor_uc2",
        ),
        sa.UniqueConstraint(
            "project_id", "entity_type", "name", name="metadata_descriptor_uc"
        ),
    )
    op.create_table(
        "milestone",
        sa.Column("date", sa.Date()),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "task_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["task_type_id"], ["task_type.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "playlist",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("shots", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "episode_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "task_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column("for_client", sa.Boolean()),
        sa.Column("for_entity", sa.String(length=10)),
        sa.Column("is_for_all", sa.Boolean()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["episode_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["task_type_id"], ["task_type.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["person.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name", "project_id", "episode_id", name="playlist_uc"
        ),
    )
    op.create_table(
        "production_schedule_version",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "production_schedule_from",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column("locked", sa.Boolean()),
        sa.Column("canceled", sa.Boolean()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(
            ["production_schedule_from"], ["production_schedule_version.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name", "project_id", name="production_schedule_version_uc"
        ),
    )
    op.create_table(
        "project_asset_type_link",
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "asset_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_type_id"], ["entity_type.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("project_id", "asset_type_id"),
    )
    op.create_table(
        "project_person_link",
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("shotgun_id", sa.Integer()),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("project_id", "person_id"),
    )
    op.create_table(
        "project_preview_background_file_link",
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "preview_background_file_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(
            ["preview_background_file_id"], ["preview_background_file.id"]
        ),
        sa.PrimaryKeyConstraint("project_id", "preview_background_file_id"),
    )
    op.create_table(
        "project_task_status_link",
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "task_status_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("priority", sa.Integer()),
        sa.Column("roles_for_board", ARRAY(ChoiceType(length=255))),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["task_status_id"], ["task_status.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("project_id", "task_status_id", "id"),
        sa.UniqueConstraint(
            "project_id", "task_status_id", name="project_taskstatus_uc"
        ),
    )
    op.create_table(
        "project_task_type_link",
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "task_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("priority", sa.Integer()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["task_type_id"], ["task_type.id"]),
        sa.PrimaryKeyConstraint("project_id", "task_type_id", "id"),
        sa.UniqueConstraint(
            "project_id", "task_type_id", name="project_tasktype_uc"
        ),
    )
    op.create_table(
        "schedule_item",
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("man_days", sa.Integer()),
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "task_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "object_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["task_type_id"], ["task_type.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "task_type_id", "object_id", name="schedule_item_uc"
        ),
    )
    op.create_table(
        "search_filter_group",
        sa.Column("list_type", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80)),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("color", sa.String(length=8), nullable=False),
        sa.Column(
            "is_shared",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "department_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "status_automation",
        sa.Column("entity_type", sa.String(length=40)),
        sa.Column(
            "in_task_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "in_task_status_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column("out_field_type", ChoiceType(length=255), nullable=False),
        sa.Column(
            "out_task_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "out_task_status_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column("import_last_revision", sa.Boolean()),
        sa.Column("archived", sa.Boolean()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["in_task_status_id"], ["task_status.id"]),
        sa.ForeignKeyConstraint(["out_task_type_id"], ["task_type.id"]),
        sa.ForeignKeyConstraint(["out_task_status_id"], ["task_status.id"]),
        sa.ForeignKeyConstraint(["in_task_type_id"], ["task_type.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "subscription",
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "entity_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "task_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["task_type_id"], ["task_type.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "person_id",
            "task_type_id",
            "entity_id",
            name="subscription_entity_uc",
        ),
        sa.UniqueConstraint(
            "person_id", "task_id", name="subscription_task_uc"
        ),
    )
    op.create_table(
        "task_person_link",
        sa.Column(
            "task_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("task_id", "person_id"),
    )
    op.create_table(
        "task_type_asset_type_link",
        sa.Column(
            "asset_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "task_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_type_id"], ["task_type.id"]),
        sa.ForeignKeyConstraint(["asset_type_id"], ["entity_type.id"]),
        sa.PrimaryKeyConstraint("asset_type_id", "task_type_id"),
        sa.UniqueConstraint(
            "asset_type_id",
            "task_type_id",
            name="task_type_asset_type_link_uc",
        ),
    )
    op.create_table(
        "time_spent",
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "task_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "person_id", "task_id", "date", name="time_spent_uc"
        ),
    )
    op.create_table(
        "attachment_file",
        sa.Column("name", sa.String(length=250)),
        sa.Column("size", sa.Integer()),
        sa.Column("extension", sa.String(length=6)),
        sa.Column("mimetype", sa.String(length=255)),
        sa.Column(
            "comment_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "reply_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "chat_message_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["chat_message_id"], ["chat_message.id"]),
        sa.ForeignKeyConstraint(["comment_id"], ["comment.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "budget_entry",
        sa.Column(
            "budget_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "department_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("months_duration", sa.Integer(), nullable=False),
        sa.Column("daily_salary", sa.Float(), nullable=False),
        sa.Column("position", ChoiceType(length=255)),
        sa.Column("seniority", ChoiceType(length=255)),
        sa.Column("exceptions", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["budget_id"], ["budget.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "build_job",
        sa.Column("status", ChoiceType(length=255), nullable=False),
        sa.Column("job_type", ChoiceType(length=255), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=False)),
        sa.Column(
            "playlist_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["playlist_id"], ["playlist.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "comment_acknoledgments",
        sa.Column(
            "comment",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "person",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["comment"], ["comment.id"]),
        sa.ForeignKeyConstraint(["person"], ["person.id"]),
        sa.PrimaryKeyConstraint("comment", "person"),
    )
    op.create_table(
        "comment_department_mentions",
        sa.Column(
            "comment",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "department",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["department"], ["department.id"]),
        sa.ForeignKeyConstraint(["comment"], ["comment.id"]),
        sa.PrimaryKeyConstraint("comment", "department"),
    )
    op.create_table(
        "comment_mentions",
        sa.Column(
            "comment",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "person",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["person"], ["person.id"]),
        sa.ForeignKeyConstraint(["comment"], ["comment.id"]),
        sa.PrimaryKeyConstraint("comment", "person"),
    )
    op.create_table(
        "comment_preview_link",
        sa.Column(
            "comment",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "preview_file",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["preview_file"], ["preview_file.id"]),
        sa.ForeignKeyConstraint(["comment"], ["comment.id"]),
        sa.PrimaryKeyConstraint("comment", "preview_file"),
    )
    op.create_table(
        "department_metadata_descriptor_link",
        sa.Column(
            "metadata_descriptor_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "department_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.ForeignKeyConstraint(
            ["metadata_descriptor_id"], ["metadata_descriptor.id"]
        ),
        sa.PrimaryKeyConstraint("metadata_descriptor_id", "department_id"),
        sa.UniqueConstraint(
            "metadata_descriptor_id",
            "department_id",
            name="department_metadata_descriptor_link_uc",
        ),
    )
    op.create_table(
        "news",
        sa.Column("change", sa.Boolean(), nullable=False),
        sa.Column(
            "author_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "comment_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "task_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "preview_file_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["author_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["preview_file_id"], ["preview_file.id"]),
        sa.ForeignKeyConstraint(["comment_id"], ["comment.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "notification",
        sa.Column("read", sa.Boolean(), nullable=False),
        sa.Column("change", sa.Boolean(), nullable=False),
        sa.Column("type", ChoiceType(length=255), nullable=False),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "author_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "comment_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "task_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "playlist_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "reply_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["author_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["comment_id"], ["comment.id"]),
        sa.ForeignKeyConstraint(["playlist_id"], ["playlist.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "person_id",
            "author_id",
            "comment_id",
            "reply_id",
            "playlist_id",
            "type",
            name="notification_uc",
        ),
    )
    op.create_table(
        "production_schedule_version_task_link",
        sa.Column(
            "production_schedule_version_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("start_date", sa.DateTime(timezone=False)),
        sa.Column("due_date", sa.DateTime(timezone=False)),
        sa.Column("estimation", sa.Float()),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(
            ["production_schedule_version_id"],
            ["production_schedule_version.id"],
        ),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "production_schedule_version_id",
            "task_id",
            name="production_schedule_version_task_link_uc",
        ),
    )
    op.create_table(
        "project_status_automation_link",
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "status_automation_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(
            ["status_automation_id"], ["status_automation.id"]
        ),
        sa.PrimaryKeyConstraint("project_id", "status_automation_id"),
    )
    op.create_table(
        "search_filter",
        sa.Column("list_type", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80)),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("search_query", sa.String(length=500), nullable=False),
        sa.Column(
            "is_shared",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "department_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "search_filter_group_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False)),
        sa.Column("updated_at", sa.DateTime(timezone=False)),
        sa.ForeignKeyConstraint(
            ["search_filter_group_id"], ["search_filter_group.id"]
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "production_schedule_version_task_link_person_link",
        sa.Column(
            "production_schedule_version_task_link_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(
            ["production_schedule_version_task_link_id"],
            ["production_schedule_version_task_link.id"],
        ),
        sa.PrimaryKeyConstraint(
            "production_schedule_version_task_link_id", "person_id"
        ),
    )
    op.create_index(
        "ix_asset_instance_asset_id",
        "asset_instance",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        "ix_asset_instance_scene_id",
        "asset_instance",
        ["scene_id"],
        unique=False,
    )
    op.create_index(
        "ix_asset_instance_target_asset_id",
        "asset_instance",
        ["target_asset_id"],
        unique=False,
    )
    op.create_index("ix_chat_object_id", "chat", ["object_id"], unique=False)
    op.create_index(
        "ix_chat_object_type", "chat", ["object_type"], unique=False
    )
    op.create_index(
        "ix_entity_project_id", "entity", ["project_id"], unique=False
    )
    op.create_index(
        "ix_entity_parent_id", "entity", ["parent_id"], unique=False
    )
    op.create_index(
        "ix_entity_entity_type_id", "entity", ["entity_type_id"], unique=False
    )
    op.create_index(
        "ix_entity_source_id", "entity", ["source_id"], unique=False
    )
    op.create_index(
        "ix_entity_type_name", "entity_type", ["name"], unique=True
    )
    op.create_index(
        "ix_output_file_temporal_entity_id",
        "output_file",
        ["temporal_entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_output_file_entity_id", "output_file", ["entity_id"], unique=False
    )
    op.create_index(
        "ix_output_file_task_type_id",
        "output_file",
        ["task_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_output_file_source_file_id",
        "output_file",
        ["source_file_id"],
        unique=False,
    )
    op.create_index(
        "ix_output_file_output_type_id",
        "output_file",
        ["output_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_output_file_file_status_id",
        "output_file",
        ["file_status_id"],
        unique=False,
    )
    op.create_index(
        "ix_output_file_person_id", "output_file", ["person_id"], unique=False
    )
    op.create_index(
        "ix_output_file_asset_instance_id",
        "output_file",
        ["asset_instance_id"],
        unique=False,
    )
    op.create_index(
        "ix_output_file_representation",
        "output_file",
        ["representation"],
        unique=False,
    )
    op.create_index(
        "ix_output_type_name", "output_type", ["name"], unique=True
    )
    op.create_index("ix_plugin_name", "plugin", ["name"], unique=False)
    op.create_index(
        "ix_plugin_plugin_id", "plugin", ["plugin_id"], unique=True
    )
    op.create_index(
        "ix_preview_background_file_is_default",
        "preview_background_file",
        ["is_default"],
        unique=False,
    )
    op.create_index(
        "ix_preview_file_task_id", "preview_file", ["task_id"], unique=False
    )
    op.create_index(
        "ix_project_status_name", "project_status", ["name"], unique=True
    )
    op.create_index(
        "ix_task_task_status_id", "task", ["task_status_id"], unique=False
    )
    op.create_index(
        "ix_task_assigner_id", "task", ["assigner_id"], unique=False
    )
    op.create_index(
        "ix_task_task_type_id", "task", ["task_type_id"], unique=False
    )
    op.create_index("ix_task_entity_id", "task", ["entity_id"], unique=False)
    op.create_index("ix_task_project_id", "task", ["project_id"], unique=False)
    op.create_index(
        "ix_task_status_is_wip", "task_status", ["is_wip"], unique=False
    )
    op.create_index(
        "ix_task_status_is_done", "task_status", ["is_done"], unique=False
    )
    op.create_index(
        "ix_task_status_is_feedback_request",
        "task_status",
        ["is_feedback_request"],
        unique=False,
    )
    op.create_index(
        "ix_task_status_short_name", "task_status", ["short_name"], unique=True
    )
    op.create_index(
        "ix_task_status_is_default",
        "task_status",
        ["is_default"],
        unique=False,
    )
    op.create_index(
        "ix_working_file_software_id",
        "working_file",
        ["software_id"],
        unique=False,
    )
    op.create_index(
        "ix_working_file_task_id", "working_file", ["task_id"], unique=False
    )
    op.create_index(
        "ix_working_file_person_id",
        "working_file",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "ix_working_file_entity_id",
        "working_file",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_working_file_shotgun_id",
        "working_file",
        ["shotgun_id"],
        unique=False,
    )
    op.create_index(
        "ix_entity_link_entity_out_id",
        "entity_link",
        ["entity_out_id"],
        unique=False,
    )
    op.create_index(
        "ix_entity_link_entity_in_id",
        "entity_link",
        ["entity_in_id"],
        unique=False,
    )
    op.create_index(
        "ix_hardware_item_department_link_hardware_item_id",
        "hardware_item_department_link",
        ["hardware_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_hardware_item_department_link_department_id",
        "hardware_item_department_link",
        ["department_id"],
        unique=False,
    )
    op.create_index(
        "only_one_email_by_person", "person", ["email", "is_bot"], unique=True
    )
    op.create_index(
        "ix_person_studio_id", "person", ["studio_id"], unique=False
    )
    op.create_index("ix_project_name", "project", ["name"], unique=True)
    op.create_index(
        "ix_project_from_schedule_version_id",
        "project",
        ["from_schedule_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_project_status_id",
        "project",
        ["project_status_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_default_preview_background_file_id",
        "project",
        ["default_preview_background_file_id"],
        unique=False,
    )
    op.create_index(
        "ix_salary_scale_department_id",
        "salary_scale",
        ["department_id"],
        unique=False,
    )
    op.create_index(
        "ix_software_department_link_software_id",
        "software_department_link",
        ["software_id"],
        unique=False,
    )
    op.create_index(
        "ix_software_department_link_department_id",
        "software_department_link",
        ["department_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_type_department_id",
        "task_type",
        ["department_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_type_shotgun_id", "task_type", ["shotgun_id"], unique=False
    )
    op.create_index("ix_api_event_name", "api_event", ["name"], unique=False)
    op.create_index(
        "ix_api_event_user_id", "api_event", ["user_id"], unique=False
    )
    op.create_index(
        "ix_api_event_project_id", "api_event", ["project_id"], unique=False
    )
    op.create_index(
        "ix_budget_project_id", "budget", ["project_id"], unique=False
    )
    op.create_index(
        "ix_chat_message_chat_id", "chat_message", ["chat_id"], unique=False
    )
    op.create_index(
        "ix_chat_message_person_id",
        "chat_message",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "ix_comment_object_id", "comment", ["object_id"], unique=False
    )
    op.create_index(
        "ix_comment_task_status_id",
        "comment",
        ["task_status_id"],
        unique=False,
    )
    op.create_index(
        "ix_comment_editor_id", "comment", ["editor_id"], unique=False
    )
    op.create_index(
        "ix_comment_person_id", "comment", ["person_id"], unique=False
    )
    op.create_index(
        "ix_comment_object_type", "comment", ["object_type"], unique=False
    )
    op.create_index(
        "ix_day_off_person_id", "day_off", ["person_id"], unique=False
    )
    op.create_index(
        "ix_department_link_person_id",
        "department_link",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "ix_department_link_department_id",
        "department_link",
        ["department_id"],
        unique=False,
    )
    op.create_index(
        "ix_desktop_login_log_person_id",
        "desktop_login_log",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "ix_entity_version_entity_id",
        "entity_version",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_entity_version_person_id",
        "entity_version",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "ix_login_log_person_id", "login_log", ["person_id"], unique=False
    )
    op.create_index(
        "ix_metadata_descriptor_for_client",
        "metadata_descriptor",
        ["for_client"],
        unique=False,
    )
    op.create_index(
        "ix_metadata_descriptor_entity_type",
        "metadata_descriptor",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_metadata_descriptor_project_id",
        "metadata_descriptor",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_milestone_project_id", "milestone", ["project_id"], unique=False
    )
    op.create_index(
        "ix_milestone_task_type_id",
        "milestone",
        ["task_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_playlist_task_type_id", "playlist", ["task_type_id"], unique=False
    )
    op.create_index(
        "ix_playlist_project_id", "playlist", ["project_id"], unique=False
    )
    op.create_index(
        "ix_playlist_episode_id", "playlist", ["episode_id"], unique=False
    )
    op.create_index(
        "ix_playlist_for_client", "playlist", ["for_client"], unique=False
    )
    op.create_index(
        "ix_playlist_for_entity", "playlist", ["for_entity"], unique=False
    )
    op.create_index(
        "ix_production_schedule_version_production_schedule_from",
        "production_schedule_version",
        ["production_schedule_from"],
        unique=False,
    )
    op.create_index(
        "ix_production_schedule_version_project_id",
        "production_schedule_version",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_person_link_project_id",
        "project_person_link",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_person_link_person_id",
        "project_person_link",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_task_status_link_project_id",
        "project_task_status_link",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_task_status_link_task_status_id",
        "project_task_status_link",
        ["task_status_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_task_type_link_project_id",
        "project_task_type_link",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_task_type_link_task_type_id",
        "project_task_type_link",
        ["task_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_schedule_item_task_type_id",
        "schedule_item",
        ["task_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_schedule_item_project_id",
        "schedule_item",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_schedule_item_object_id",
        "schedule_item",
        ["object_id"],
        unique=False,
    )
    op.create_index(
        "ix_search_filter_group_list_type",
        "search_filter_group",
        ["list_type"],
        unique=False,
    )
    op.create_index(
        "ix_status_automation_in_task_type_id",
        "status_automation",
        ["in_task_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_status_automation_out_task_type_id",
        "status_automation",
        ["out_task_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_status_automation_in_task_status_id",
        "status_automation",
        ["in_task_status_id"],
        unique=False,
    )
    op.create_index(
        "ix_status_automation_out_task_status_id",
        "status_automation",
        ["out_task_status_id"],
        unique=False,
    )
    op.create_index(
        "ix_subscription_entity_id",
        "subscription",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_subscription_task_id", "subscription", ["task_id"], unique=False
    )
    op.create_index(
        "ix_subscription_task_type_id",
        "subscription",
        ["task_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_subscription_person_id",
        "subscription",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_type_asset_type_link_asset_type_id",
        "task_type_asset_type_link",
        ["asset_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_type_asset_type_link_task_type_id",
        "task_type_asset_type_link",
        ["task_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_time_spent_task_id", "time_spent", ["task_id"], unique=False
    )
    op.create_index(
        "ix_time_spent_person_id", "time_spent", ["person_id"], unique=False
    )
    op.create_index(
        "ix_attachment_file_chat_message_id",
        "attachment_file",
        ["chat_message_id"],
        unique=False,
    )
    op.create_index(
        "ix_attachment_file_comment_id",
        "attachment_file",
        ["comment_id"],
        unique=False,
    )
    op.create_index(
        "ix_budget_entry_department_id",
        "budget_entry",
        ["department_id"],
        unique=False,
    )
    op.create_index(
        "ix_budget_entry_person_id",
        "budget_entry",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "ix_budget_entry_budget_id",
        "budget_entry",
        ["budget_id"],
        unique=False,
    )
    op.create_index(
        "ix_build_job_playlist_id", "build_job", ["playlist_id"], unique=False
    )
    op.create_index(
        "ix_comment_preview_link_comment",
        "comment_preview_link",
        ["comment"],
        unique=False,
    )
    op.create_index(
        "ix_comment_preview_link_preview_file",
        "comment_preview_link",
        ["preview_file"],
        unique=False,
    )
    op.create_index(
        "ix_department_metadata_descriptor_link_metadata_descriptor_id",
        "department_metadata_descriptor_link",
        ["metadata_descriptor_id"],
        unique=False,
    )
    op.create_index(
        "ix_department_metadata_descriptor_link_department_id",
        "department_metadata_descriptor_link",
        ["department_id"],
        unique=False,
    )
    op.create_index("ix_news_author_id", "news", ["author_id"], unique=False)
    op.create_index(
        "ix_news_preview_file_id", "news", ["preview_file_id"], unique=False
    )
    op.create_index("ix_news_comment_id", "news", ["comment_id"], unique=False)
    op.create_index("ix_news_task_id", "news", ["task_id"], unique=False)
    op.create_index(
        "ix_notification_task_id", "notification", ["task_id"], unique=False
    )
    op.create_index(
        "ix_notification_comment_id",
        "notification",
        ["comment_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_author_id",
        "notification",
        ["author_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_reply_id", "notification", ["reply_id"], unique=False
    )
    op.create_index(
        "ix_notification_person_id",
        "notification",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_playlist_id",
        "notification",
        ["playlist_id"],
        unique=False,
    )
    op.create_index(
        "ix_production_schedule_version_task_link_production_schedule_version_id",
        "production_schedule_version_task_link",
        ["production_schedule_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_production_schedule_version_task_link_task_id",
        "production_schedule_version_task_link",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_status_automation_link_status_automation_id",
        "project_status_automation_link",
        ["status_automation_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_status_automation_link_project_id",
        "project_status_automation_link",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_search_filter_person_id",
        "search_filter",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "ix_search_filter_list_type",
        "search_filter",
        ["list_type"],
        unique=False,
    )
    op.create_index(
        "ix_search_filter_project_id",
        "search_filter",
        ["project_id"],
        unique=False,
    )


def downgrade():
    op.drop_table("production_schedule_version_task_link_person_link")
    op.drop_index("ix_search_filter_person_id", table_name="search_filter")
    op.drop_index("ix_search_filter_list_type", table_name="search_filter")
    op.drop_index("ix_search_filter_project_id", table_name="search_filter")
    op.drop_table("search_filter")
    op.drop_index(
        "ix_project_status_automation_link_status_automation_id",
        table_name="project_status_automation_link",
    )
    op.drop_index(
        "ix_project_status_automation_link_project_id",
        table_name="project_status_automation_link",
    )
    op.drop_table("project_status_automation_link")
    op.drop_index(
        "ix_production_schedule_version_task_link_production_schedule_version_id",
        table_name="production_schedule_version_task_link",
    )
    op.drop_index(
        "ix_production_schedule_version_task_link_task_id",
        table_name="production_schedule_version_task_link",
    )
    op.drop_table("production_schedule_version_task_link")
    op.drop_index("ix_notification_task_id", table_name="notification")
    op.drop_index("ix_notification_comment_id", table_name="notification")
    op.drop_index("ix_notification_author_id", table_name="notification")
    op.drop_index("ix_notification_reply_id", table_name="notification")
    op.drop_index("ix_notification_person_id", table_name="notification")
    op.drop_index("ix_notification_playlist_id", table_name="notification")
    op.drop_table("notification")
    op.drop_index("ix_news_author_id", table_name="news")
    op.drop_index("ix_news_preview_file_id", table_name="news")
    op.drop_index("ix_news_comment_id", table_name="news")
    op.drop_index("ix_news_task_id", table_name="news")
    op.drop_table("news")
    op.drop_index(
        "ix_department_metadata_descriptor_link_metadata_descriptor_id",
        table_name="department_metadata_descriptor_link",
    )
    op.drop_index(
        "ix_department_metadata_descriptor_link_department_id",
        table_name="department_metadata_descriptor_link",
    )
    op.drop_table("department_metadata_descriptor_link")
    op.drop_index(
        "ix_comment_preview_link_comment", table_name="comment_preview_link"
    )
    op.drop_index(
        "ix_comment_preview_link_preview_file",
        table_name="comment_preview_link",
    )
    op.drop_table("comment_preview_link")
    op.drop_table("comment_mentions")
    op.drop_table("comment_department_mentions")
    op.drop_table("comment_acknoledgments")
    op.drop_index("ix_build_job_playlist_id", table_name="build_job")
    op.drop_table("build_job")
    op.drop_index("ix_budget_entry_department_id", table_name="budget_entry")
    op.drop_index("ix_budget_entry_person_id", table_name="budget_entry")
    op.drop_index("ix_budget_entry_budget_id", table_name="budget_entry")
    op.drop_table("budget_entry")
    op.drop_index(
        "ix_attachment_file_chat_message_id", table_name="attachment_file"
    )
    op.drop_index(
        "ix_attachment_file_comment_id", table_name="attachment_file"
    )
    op.drop_table("attachment_file")
    op.drop_index("ix_time_spent_task_id", table_name="time_spent")
    op.drop_index("ix_time_spent_person_id", table_name="time_spent")
    op.drop_table("time_spent")
    op.drop_index(
        "ix_task_type_asset_type_link_asset_type_id",
        table_name="task_type_asset_type_link",
    )
    op.drop_index(
        "ix_task_type_asset_type_link_task_type_id",
        table_name="task_type_asset_type_link",
    )
    op.drop_table("task_type_asset_type_link")
    op.drop_table("task_person_link")
    op.drop_index("ix_subscription_entity_id", table_name="subscription")
    op.drop_index("ix_subscription_task_id", table_name="subscription")
    op.drop_index("ix_subscription_task_type_id", table_name="subscription")
    op.drop_index("ix_subscription_person_id", table_name="subscription")
    op.drop_table("subscription")
    op.drop_index(
        "ix_status_automation_in_task_type_id", table_name="status_automation"
    )
    op.drop_index(
        "ix_status_automation_out_task_type_id", table_name="status_automation"
    )
    op.drop_index(
        "ix_status_automation_in_task_status_id",
        table_name="status_automation",
    )
    op.drop_index(
        "ix_status_automation_out_task_status_id",
        table_name="status_automation",
    )
    op.drop_table("status_automation")
    op.drop_index(
        "ix_search_filter_group_list_type", table_name="search_filter_group"
    )
    op.drop_table("search_filter_group")
    op.drop_index("ix_schedule_item_task_type_id", table_name="schedule_item")
    op.drop_index("ix_schedule_item_project_id", table_name="schedule_item")
    op.drop_index("ix_schedule_item_object_id", table_name="schedule_item")
    op.drop_table("schedule_item")
    op.drop_index(
        "ix_project_task_type_link_project_id",
        table_name="project_task_type_link",
    )
    op.drop_index(
        "ix_project_task_type_link_task_type_id",
        table_name="project_task_type_link",
    )
    op.drop_table("project_task_type_link")
    op.drop_index(
        "ix_project_task_status_link_project_id",
        table_name="project_task_status_link",
    )
    op.drop_index(
        "ix_project_task_status_link_task_status_id",
        table_name="project_task_status_link",
    )
    op.drop_table("project_task_status_link")
    op.drop_table("project_preview_background_file_link")
    op.drop_index(
        "ix_project_person_link_project_id", table_name="project_person_link"
    )
    op.drop_index(
        "ix_project_person_link_person_id", table_name="project_person_link"
    )
    op.drop_table("project_person_link")
    op.drop_table("project_asset_type_link")
    op.drop_index(
        "ix_production_schedule_version_production_schedule_from",
        table_name="production_schedule_version",
    )
    op.drop_index(
        "ix_production_schedule_version_project_id",
        table_name="production_schedule_version",
    )
    op.drop_table("production_schedule_version")
    op.drop_index("ix_playlist_task_type_id", table_name="playlist")
    op.drop_index("ix_playlist_project_id", table_name="playlist")
    op.drop_index("ix_playlist_episode_id", table_name="playlist")
    op.drop_index("ix_playlist_for_client", table_name="playlist")
    op.drop_index("ix_playlist_for_entity", table_name="playlist")
    op.drop_table("playlist")
    op.drop_index("ix_milestone_project_id", table_name="milestone")
    op.drop_index("ix_milestone_task_type_id", table_name="milestone")
    op.drop_table("milestone")
    op.drop_index(
        "ix_metadata_descriptor_for_client", table_name="metadata_descriptor"
    )
    op.drop_index(
        "ix_metadata_descriptor_entity_type", table_name="metadata_descriptor"
    )
    op.drop_index(
        "ix_metadata_descriptor_project_id", table_name="metadata_descriptor"
    )
    op.drop_table("metadata_descriptor")
    op.drop_index("ix_login_log_person_id", table_name="login_log")
    op.drop_table("login_log")
    op.drop_index("ix_entity_version_entity_id", table_name="entity_version")
    op.drop_index("ix_entity_version_person_id", table_name="entity_version")
    op.drop_table("entity_version")
    op.drop_index(
        "ix_desktop_login_log_person_id", table_name="desktop_login_log"
    )
    op.drop_table("desktop_login_log")
    op.drop_index("ix_department_link_person_id", table_name="department_link")
    op.drop_index(
        "ix_department_link_department_id", table_name="department_link"
    )
    op.drop_table("department_link")
    op.drop_index("ix_day_off_person_id", table_name="day_off")
    op.drop_table("day_off")
    op.drop_index("ix_comment_object_id", table_name="comment")
    op.drop_index("ix_comment_task_status_id", table_name="comment")
    op.drop_index("ix_comment_editor_id", table_name="comment")
    op.drop_index("ix_comment_person_id", table_name="comment")
    op.drop_index("ix_comment_object_type", table_name="comment")
    op.drop_table("comment")
    op.drop_table("chat_participant")
    op.drop_index("ix_chat_message_chat_id", table_name="chat_message")
    op.drop_index("ix_chat_message_person_id", table_name="chat_message")
    op.drop_table("chat_message")
    op.drop_index("ix_budget_project_id", table_name="budget")
    op.drop_table("budget")
    op.drop_index("ix_api_event_name", table_name="api_event")
    op.drop_index("ix_api_event_user_id", table_name="api_event")
    op.drop_index("ix_api_event_project_id", table_name="api_event")
    op.drop_table("api_event")
    op.drop_index("ix_task_type_department_id", table_name="task_type")
    op.drop_index("ix_task_type_shotgun_id", table_name="task_type")
    op.drop_table("task_type")
    op.drop_index(
        "ix_software_department_link_software_id",
        table_name="software_department_link",
    )
    op.drop_index(
        "ix_software_department_link_department_id",
        table_name="software_department_link",
    )
    op.drop_table("software_department_link")
    op.drop_index("ix_salary_scale_department_id", table_name="salary_scale")
    op.drop_table("salary_scale")
    op.drop_index("ix_project_name", table_name="project")
    op.drop_index("ix_project_from_schedule_version_id", table_name="project")
    op.drop_index("ix_project_project_status_id", table_name="project")
    op.drop_index(
        "ix_project_default_preview_background_file_id", table_name="project"
    )
    op.drop_table("project")
    op.drop_index("only_one_email_by_person", table_name="person")
    op.drop_index("ix_person_studio_id", table_name="person")
    op.drop_table("person")
    op.drop_index(
        "ix_hardware_item_department_link_hardware_item_id",
        table_name="hardware_item_department_link",
    )
    op.drop_index(
        "ix_hardware_item_department_link_department_id",
        table_name="hardware_item_department_link",
    )
    op.drop_table("hardware_item_department_link")
    op.drop_index("ix_entity_link_entity_out_id", table_name="entity_link")
    op.drop_index("ix_entity_link_entity_in_id", table_name="entity_link")
    op.drop_table("entity_link")
    op.drop_table("entity_concept_link")
    op.drop_table("asset_instance_link")
    op.drop_index("ix_working_file_software_id", table_name="working_file")
    op.drop_index("ix_working_file_task_id", table_name="working_file")
    op.drop_index("ix_working_file_person_id", table_name="working_file")
    op.drop_index("ix_working_file_entity_id", table_name="working_file")
    op.drop_index("ix_working_file_shotgun_id", table_name="working_file")
    op.drop_table("working_file")
    op.drop_index("ix_task_status_is_wip", table_name="task_status")
    op.drop_index("ix_task_status_is_done", table_name="task_status")
    op.drop_index(
        "ix_task_status_is_feedback_request", table_name="task_status"
    )
    op.drop_index("ix_task_status_short_name", table_name="task_status")
    op.drop_index("ix_task_status_is_default", table_name="task_status")
    op.drop_table("task_status")
    op.drop_index("ix_task_task_status_id", table_name="task")
    op.drop_index("ix_task_assigner_id", table_name="task")
    op.drop_index("ix_task_task_type_id", table_name="task")
    op.drop_index("ix_task_entity_id", table_name="task")
    op.drop_index("ix_task_project_id", table_name="task")
    op.drop_table("task")
    op.drop_table("studio")
    op.drop_table("software")
    op.drop_index("ix_project_status_name", table_name="project_status")
    op.drop_table("project_status")
    op.drop_index("ix_preview_file_task_id", table_name="preview_file")
    op.drop_table("preview_file")
    op.drop_index(
        "ix_preview_background_file_is_default",
        table_name="preview_background_file",
    )
    op.drop_table("preview_background_file")
    op.drop_index("ix_plugin_name", table_name="plugin")
    op.drop_index("ix_plugin_plugin_id", table_name="plugin")
    op.drop_table("plugin")
    op.drop_index("ix_output_type_name", table_name="output_type")
    op.drop_table("output_type")
    op.drop_index(
        "ix_output_file_temporal_entity_id", table_name="output_file"
    )
    op.drop_index("ix_output_file_entity_id", table_name="output_file")
    op.drop_index("ix_output_file_task_type_id", table_name="output_file")
    op.drop_index("ix_output_file_source_file_id", table_name="output_file")
    op.drop_index("ix_output_file_output_type_id", table_name="output_file")
    op.drop_index("ix_output_file_file_status_id", table_name="output_file")
    op.drop_index("ix_output_file_person_id", table_name="output_file")
    op.drop_index("ix_output_file_asset_instance_id", table_name="output_file")
    op.drop_index("ix_output_file_representation", table_name="output_file")
    op.drop_table("output_file")
    op.drop_table("organisation")
    op.drop_table("hardware_item")
    op.drop_table("file_status")
    op.drop_index("ix_entity_type_name", table_name="entity_type")
    op.drop_table("entity_type")
    op.drop_index("ix_entity_project_id", table_name="entity")
    op.drop_index("ix_entity_parent_id", table_name="entity")
    op.drop_index("ix_entity_entity_type_id", table_name="entity")
    op.drop_index("ix_entity_source_id", table_name="entity")
    op.drop_table("entity")
    op.drop_table("department")
    op.drop_table("data_import_error")
    op.drop_table("custom_action")
    op.drop_index("ix_chat_object_id", table_name="chat")
    op.drop_index("ix_chat_object_type", table_name="chat")
    op.drop_table("chat")
    op.drop_index("ix_asset_instance_asset_id", table_name="asset_instance")
    op.drop_index("ix_asset_instance_scene_id", table_name="asset_instance")
    op.drop_index(
        "ix_asset_instance_target_asset_id", table_name="asset_instance"
    )
    op.drop_table("asset_instance")
