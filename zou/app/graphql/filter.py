import uuid
import graphene
from sqlalchemy import inspection
from graphene_sqlalchemy.converter import convert_sqlalchemy_type
from sqlalchemy.orm.properties import ColumnProperty


# TODO: Use this class to allow multiple filter types like
# equal, not equal, less than, more than...
class Filter(graphene.InputObjectType):
    filter_type = graphene.String()
    filter_value = graphene.String()


class FilterSet(graphene.InputObjectType):
    id = graphene.String()


def create_filter_set(model):
    filters = {}
    inspected = inspection.inspect(model)
    for descriptor in inspected.all_orm_descriptors:
        if not isinstance(descriptor.property, ColumnProperty):
            continue

        name = descriptor.property.key
        column = descriptor.property.columns[0]
        column_type = getattr(column, "type", None)
        graphql_type = convert_sqlalchemy_type(column_type, column)
        filters[name] = graphql_type(required=False)

    uid = uuid.uuid1()
    filter_set_type = type(
        f"FilterSet_{model.__name__}_{uid}",
        (graphene.InputObjectType,),
        {
            **filters,
        },
    )

    return filter_set_type
