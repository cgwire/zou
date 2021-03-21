import sqlalchemy.orm as orm
from sqlalchemy.inspection import inspect
from zou.app.utils.fields import serialize_value


class SerializerMixin(object):
    """
    Helpers to facilitate JSON serialization of models.
    """

    def is_join(self, attr):
        return isinstance(
            getattr(self.__class__, attr).impl,
            orm.attributes.CollectionAttributeImpl,
        )

    def serialize(self, obj_type=None, relations=False):
        attrs = inspect(self).attrs.keys()
        if relations:
            obj_dict = {
                attr: serialize_value(getattr(self, attr)) for attr in attrs
            }
        else:
            obj_dict = {
                attr: serialize_value(getattr(self, attr))
                for attr in attrs
                if not self.is_join(attr)
            }
        obj_dict["type"] = obj_type or type(self).__name__
        return obj_dict

    @staticmethod
    def serialize_list(models, obj_type=None, relations=False):
        return [
            model.serialize(obj_type=obj_type, relations=relations)
            for model in models
        ]
