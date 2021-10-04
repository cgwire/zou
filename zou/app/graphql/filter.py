import graphene
from sqlalchemy import inspection
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm.attributes import InstrumentedAttribute


class Filter(graphene.InputObjectType):
    filter_type = graphene.String()
    filter_value = graphene.String()


class FilterSet(graphene.InputObjectType):
    filters = graphene.List(Filter)
    field = graphene.String()


def get_model_fields_data(model):
    """
    Get model columns.

    Args:
        model: SQLAlchemy model.
        only_fields: Filter of fields.

    Returns:
        Fields info.

    """
    model_fields = {}

    inspected = inspection.inspect(model)
    for descr in inspected.all_orm_descriptors:
        if isinstance(descr, hybrid_property):
            attr = descr
            name = attr.__name__

            model_fields[name] = {
                "column": attr,
                "type": None,
                "nullable": True,
            }

        elif isinstance(descr, InstrumentedAttribute):
            attr = descr.property
            name = attr.key

            column = attr.columns[0]
            model_fields[name] = {
                "column": column,
                "type": column.type,
                "nullable": column.nullable,
            }

    return model_fields


def test_dynamic(model):
    data = get_model_fields_data(model)
    print(data)

    def dynamic_type():
        return graphene.Field(graphene.String)

    return graphene.Dynamic(dynamic_type)
