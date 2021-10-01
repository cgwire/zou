import graphene

class Filter(graphene.InputObjectType):
    filter_type = graphene.String()
    filter_value = graphene.String()

class FilterSet(graphene.InputObjectType):
    filters = graphene.List(Filter)
    field = graphene.String()
