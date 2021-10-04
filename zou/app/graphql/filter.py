import graphene
from sqlalchemy import inspection
from sqlalchemy.orm.attributes import InstrumentedAttribute
from graphene_sqlalchemy.converter import convert_sqlalchemy_type
from sqlalchemy.orm.properties import ColumnProperty


class Filter(graphene.InputObjectType):
    filter_type = graphene.String()
    filter_value = graphene.String()


class FilterSet(graphene.InputObjectType):
    filters = graphene.List(Filter)
    field = graphene.String()


def create_filters(model):
    extra_filters = {}
    inspected = inspection.inspect(model)
    for descriptor in inspected.all_orm_descriptors:
        if not isinstance(descriptor.property, ColumnProperty):
            continue

        name = descriptor.property.key
        column = descriptor.property.columns[0]
        column_type = getattr(column, "type", None)
        graphql_type = convert_sqlalchemy_type(column_type, column)
        extra_filters[name] = graphql_type

    print(extra_filters)

    MyType = type(
        "MyType",
        (graphene.InputObjectType,),
        {
            "something": graphene.String(),
            "field": graphene.String(),
            "filters": graphene.List(Filter),
        },
    )

    return MyType
