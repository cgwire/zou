import graphene
from sqlalchemy_utils import UUIDType, EmailType, LocaleType, TimezoneType
from graphene_sqlalchemy.converter import convert_sqlalchemy_type

from zou.app import db


@convert_sqlalchemy_type.register(EmailType)
@convert_sqlalchemy_type.register(LocaleType)
@convert_sqlalchemy_type.register(TimezoneType)
@convert_sqlalchemy_type.register(db.LargeBinary)
def convert_unknown(type, column, registry=None):
    return graphene.String


@convert_sqlalchemy_type.register(UUIDType)
def convert_id(type, column, registry=None):
    return graphene.ID
