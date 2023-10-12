from sqlalchemy_utils import EmailType

from zou.app import db
from zou.app.models.identity import Identity


class ApiToken(db.Model, Identity):
    """
    Describe an API Token.
    """

    name = db.Column(db.String(80), nullable=False, unique=True)
    email = db.Column(EmailType)
    jti = db.Column(db.String(60), nullable=True, unique=True)
    days_duration = db.Column(db.Integer(), nullable=True)
    description = db.Column(db.Text())

    def __repr__(self):
        return f"<ApiToken {self.full_name()}>"

    def full_name(self):
        return self.name

    def serialize(self, obj_type="ApiToken", relations=False):
        data = super().serialize(obj_type, relations=relations)
        return data

    def serialize_safe(self, relations=False):
        data = super().serialize_safe(relations=relations)
        del data["jti"]
        return data

    def present_minimal(self, relations=False):
        data = self.serialize(relations=relations)
        return {
            "id": data["id"],
            "name": data["name"],
            "full_name": self.full_name(),
            "has_avatar": data["has_avatar"],
            "active": data["active"],
            "departments": data.get("departments", []),
            "role": data["role"],
        }
