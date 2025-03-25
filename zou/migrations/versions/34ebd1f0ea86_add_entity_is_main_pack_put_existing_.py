"""Add entity.is_main_pack + put existing main pack

Revision ID: 34ebd1f0ea86
Revises: 307edd8c639d
Create Date: 2025-03-11 17:24:00.856665

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm.session import Session
from zou.migrations.utils.base import BaseMixin
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy_utils import ChoiceType
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy_utils import UUIDType


# revision identifiers, used by Alembic.
revision = "34ebd1f0ea86"
down_revision = "307edd8c639d"
branch_labels = None
depends_on = None

base = declarative_base()

PROJECT_STYLES = [
    ("2d", "2D Animation"),
    ("2dpaper", "2D Animation (Paper)"),
    ("3d", "3D Animation"),
    ("2d3d", "2D/3D Animation"),
    ("ar", "Augmented Reality"),
    ("vfx", "VFX"),
    ("stop-motion", "Stop Motion"),
    ("motion-design", "Motion Design"),
    ("archviz", "Archviz"),
    ("commercial", "Commercial"),
    ("catalog", "Catalog"),
    ("immersive", "Immersive Experience"),
    ("nft", "NFT Collection"),
    ("video-game", "Video Game"),
    ("vr", "Virtual Reality"),
]


class Project(base, BaseMixin):
    """
    Describes a production the studio works on.
    """

    __tablename__ = "project"

    name = sa.Column(sa.String(80), nullable=False, unique=True, index=True)
    code = sa.Column(sa.String(80))
    description = sa.Column(sa.Text())
    shotgun_id = sa.Column(sa.Integer)
    file_tree = sa.Column(JSONB)
    data = sa.Column(JSONB)
    has_avatar = sa.Column(sa.Boolean(), default=False)
    fps = sa.Column(sa.String(10), default=25)
    ratio = sa.Column(sa.String(10), default="16:9")
    resolution = sa.Column(sa.String(12), default="1920x1080")
    production_type = sa.Column(sa.String(20), default="short")
    production_style = sa.Column(
        ChoiceType(PROJECT_STYLES), default="2d3d", nullable=False
    )
    start_date = sa.Column(sa.Date())
    end_date = sa.Column(sa.Date())
    man_days = sa.Column(sa.Integer)
    nb_episodes = sa.Column(sa.Integer, default=0)
    episode_span = sa.Column(sa.Integer, default=0)
    max_retakes = sa.Column(sa.Integer, default=0)
    is_clients_isolated = sa.Column(sa.Boolean(), default=False)
    is_preview_download_allowed = sa.Column(sa.Boolean(), default=False)
    is_set_preview_automated = sa.Column(sa.Boolean(), default=False)
    homepage = sa.Column(sa.String(80), default="assets")
    is_publish_default_for_artists = sa.Column(sa.Boolean(), default=False)
    hd_bitrate_compression = sa.Column(sa.Integer, default=28)
    ld_bitrate_compression = sa.Column(sa.Integer, default=6)

    project_status_id = sa.Column(
        UUIDType(binary=False), sa.ForeignKey("project_status.id"), index=True
    )

    default_preview_background_file_id = sa.Column(
        UUIDType(binary=False),
        sa.ForeignKey("preview_background_file.id"),
        default=None,
        index=True,
    )


ENTITY_STATUSES = [
    ("standby", "Stand By"),
    ("running", "Running"),
    ("complete", "Complete"),
    ("canceled", "Canceled"),
]


class Entity(base, BaseMixin):
    """
    Base model to represent assets, shots, sequences, episodes and scenes.
    They have different meaning but they share the same behaviour toward
    tasks and files.
    """

    __tablename__ = "entity"

    id = BaseMixin.id
    name = sa.Column(sa.String(160), nullable=False)
    code = sa.Column(sa.String(160))  # To store sanitized version of name
    description = sa.Column(sa.Text())
    shotgun_id = sa.Column(sa.Integer)
    canceled = sa.Column(sa.Boolean, default=False)

    nb_frames = sa.Column(sa.Integer)  # Specific to shots
    nb_entities_out = sa.Column(sa.Integer, default=0)
    is_casting_standby = sa.Column(sa.Boolean, default=False)

    is_shared = sa.Column(sa.Boolean, default=False, nullable=False)

    # specific to episodes
    is_main_pack = sa.Column(sa.Boolean, default=False, nullable=False)

    status = sa.Column(
        ChoiceType(ENTITY_STATUSES), default="running", nullable=False
    )

    project_id = sa.Column(
        UUIDType(binary=False),
        sa.ForeignKey("project.id"),
        nullable=False,
        index=True,
    )
    entity_type_id = sa.Column(
        UUIDType(binary=False),
        sa.ForeignKey("entity_type.id"),
        nullable=False,
        index=True,
    )

    parent_id = sa.Column(
        UUIDType(binary=False), sa.ForeignKey("entity.id"), index=True
    )  # sequence or episode

    source_id = sa.Column(
        UUIDType(binary=False),
        sa.ForeignKey("entity.id"),
        index=True,
        nullable=True,
    )  # if the entity is generated from another one (like shots from scene).

    preview_file_id = sa.Column(
        UUIDType(binary=False),
    )
    data = sa.Column(JSONB)

    ready_for = sa.Column(
        UUIDType(binary=False),
    )

    created_by = sa.Column(
        UUIDType(binary=False),
        nullable=True,
    )


class EntityType(base, BaseMixin):
    """
    Type of entities. It can describe either an asset type, or tell if target
    entity is a shot, sequence, episode or layout scene.
    """

    __tablename__ = "entity_type"

    name = sa.Column(sa.String(30), unique=True, nullable=False, index=True)
    short_name = sa.Column(sa.String(20))
    description = sa.Column(sa.Text())
    archived = sa.Column(sa.Boolean(), default=False)


class Playlist(base, BaseMixin):
    """
    Describes a playlist. The goal is to review a set of shipped materials.
    """

    __tablename__ = "playlist"

    name = sa.Column(sa.String(80), nullable=False)
    shots = sa.Column(JSONB)

    project_id = sa.Column(
        UUIDType(binary=False), sa.ForeignKey("project.id"), index=True
    )
    episode_id = sa.Column(
        UUIDType(binary=False), sa.ForeignKey("entity.id"), index=True
    )
    task_type_id = sa.Column(
        UUIDType(binary=False), sa.ForeignKey("task_type.id"), index=True
    )
    for_client = sa.Column(sa.Boolean(), default=False, index=True)
    for_entity = sa.Column(sa.String(10), default="shot", index=True)
    is_for_all = sa.Column(sa.Boolean, default=False)


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("entity", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_main_pack",
                sa.Boolean(),
                server_default=sa.text("false"),
                default=False,
                nullable=False,
            )
        )
    with op.batch_alter_table("entity", schema=None) as batch_op:
        session = Session(bind=op.get_bind())
        episode_entity_type_id = (
            session.query(EntityType.id)
            .where(EntityType.name == "Episode")
            .first()
        )[0]
        temporal_entity_type_ids = [
            i[0]
            for i in session.query(EntityType.id)
            .where(
                EntityType.name.not_in(
                    ["Shot", "Scene", "Sequence", "Episode", "Edit", "Concept"]
                )
            )
            .distinct()
            .all()
        ]
        for project_id in (
            session.query(Project.id)
            .where(Project.production_type == "tvshow")
            .all()
        ):
            main_pack_episode = Entity(
                name="MP",
                project_id=project_id[0],
                entity_type_id=episode_entity_type_id,
                is_main_pack=True,
            )
            session.add(main_pack_episode)
            session.commit()
            session.refresh(main_pack_episode)

            session.query(Entity).filter(
                Entity.project_id == project_id[0],
                Entity.entity_type_id.in_(temporal_entity_type_ids),
                Entity.source_id == None,
            ).update({Entity.source_id: main_pack_episode.id})
            session.commit()

            session.query(Playlist).filter(
                Playlist.project_id == project_id[0],
                Playlist.episode_id == None,
            ).update({Playlist.episode_id: main_pack_episode.id})
            session.commit()

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("entity", schema=None) as batch_op:
        session = Session(bind=op.get_bind())

        for project_id in (
            session.query(Project.id)
            .where(Project.production_type == "tvshow")
            .all()
        ):
            main_pack_episode = (
                session.query(Entity)
                .where(
                    Entity.project_id == project_id[0],
                    Entity.is_main_pack == True,
                )
                .first()
            )
            session.query(Entity).filter(
                Entity.project_id == project_id[0],
                Entity.source_id == main_pack_episode.id,
            ).update({Entity.source_id: None})

            session.query(Playlist).filter(
                Playlist.project_id == project_id[0],
                Playlist.episode_id == main_pack_episode.id,
            ).update({Playlist.episode_id: None})
        session.query(Entity).where(Entity.is_main_pack == True).delete()
        session.commit()
        batch_op.drop_column("is_main_pack")

    # ### end Alembic commands ###
