from sqlalchemy_utils import UUIDType
from sqlalchemy.dialects.postgresql import JSONB

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


preview_link_table = db.Table(
    "comment_preview_link",
    db.Column(
        "comment",
        UUIDType(binary=False),
        db.ForeignKey("comment.id"),
        primary_key=True,
    ),
    db.Column(
        "preview_file",
        UUIDType(binary=False),
        db.ForeignKey("preview_file.id"),
        primary_key=True,
    ),
)


mentions_table = db.Table(
    "comment_mentions",
    db.Column(
        "comment",
        UUIDType(binary=False),
        db.ForeignKey("comment.id"),
        primary_key=True,
    ),
    db.Column(
        "person",
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        primary_key=True,
    ),
)


acknowledgements_table = db.Table(
    "comment_acknoledgments",
    db.Column(
        "comment",
        UUIDType(binary=False),
        db.ForeignKey("comment.id"),
        primary_key=True,
    ),
    db.Column(
        "person",
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        primary_key=True,
    ),
)


class Comment(db.Model, BaseMixin, SerializerMixin):
    """
    Comment can occur on any object but they are mainly used on tasks.
    In the case of comment tasks, they are linked to a task status and
    eventually to some preview files.
    The status means that comment leads to task status change. The preview file
    means that the comment relates to this preview in the context of the task.
    """

    shotgun_id = db.Column(db.Integer)

    object_id = db.Column(UUIDType(binary=False), nullable=False, index=True)
    object_type = db.Column(db.String(80), nullable=False, index=True)
    text = db.Column(db.Text())
    data = db.Column(JSONB)
    replies = db.Column(JSONB, default=[])
    checklist = db.Column(JSONB)
    pinned = db.Column(db.Boolean)

    task_status_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_status.id")
    )
    person_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("person.id"), nullable=False
    )
    preview_file_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("preview_file.id")
    )
    previews = db.relationship(
        "PreviewFile", secondary=preview_link_table, backref="comments"
    )
    mentions = db.relationship("Person", secondary=mentions_table)
    acknowledgements = db.relationship(
        "Person", secondary=acknowledgements_table
    )
    attachment_files = db.relationship("AttachmentFile", backref="comment")

    def __repr__(self):
        return "<Comment of %s>" % self.object_id

    def set_preview_files(self, preview_file_ids):
        from zou.app.models.preview_file import PreviewFile

        self.set_many_to_one("previews", PreviewFile, preview_file_ids)

    def set_mentions(self, person_ids):
        from zou.app.models.person import Person

        self.mentions = []
        self.set_many_to_one("mentions", Person, person_ids)

    def set_acknowledgements(self, person_ids):
        from zou.app.models.person import Person

        self.set_many_to_one("acknowledgements", Person, person_ids)

    def set_attachment_files(self, attachment_file_ids):
        from zou.app.models.attachment_file import AttachmentFile

        self.set_many_to_one(
            "attachment_files", AttachmentFile, attachment_file_ids
        )

    def set_many_to_one(self, field_name, model, model_ids):
        setattr(self, field_name, [])
        for model_id in model_ids:
            instance = model.get(model_id)
            if instance is not None:
                getattr(self, field_name).append(instance)
        self.save()

    @classmethod
    def create_from_import(cls, data):
        is_update = False
        previous_comment = cls.get(data["id"])
        data.pop("type", None)
        preview_file_ids = data.pop("previews", None)
        mention_ids = data.pop("mentions", None)
        acknowledgement_ids = data.pop("acknowledgements", None)
        attachment_file_ids = data.pop("attachment_files", None)

        if previous_comment is None:
            previous_comment = cls.create(**data)
            previous_comment.save()
        else:
            is_update = True
            previous_comment.update(data)
            previous_comment.save()

        if preview_file_ids is not None:
            previous_comment.set_preview_files(preview_file_ids)

        if mention_ids is not None:
            previous_comment.set_mentions(mention_ids)

        if acknowledgement_ids is not None:
            previous_comment.set_acknowledgements(acknowledgement_ids)

        if attachment_file_ids is not None:
            previous_comment.set_attachment_files(attachment_file_ids)

        return (previous_comment, is_update)
