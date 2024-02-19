import sqlalchemy.orm as orm
from sqlalchemy.inspection import inspect
from zou.app.utils.fields import serialize_value


class SerializerMixin(object):
    """
    Helpers to facilitate JSON serialization of models.
    """

    def is_join(self, attr):
        return hasattr(getattr(self.__class__, attr), "impl") and isinstance(
            getattr(self.__class__, attr).impl,
            orm.attributes.CollectionAttributeImpl,
        )

    def serialize(self, obj_type=None, relations=False, milliseconds=False):
        attrs = inspect(self.__class__).all_orm_descriptors.keys()
        if relations:
            obj_dict = {
                attr: serialize_value(
                    getattr(self, attr), milliseconds=milliseconds
                )
                for attr in attrs
            }
        else:
            obj_dict = {
                attr: serialize_value(
                    getattr(self, attr), milliseconds=milliseconds
                )
                for attr in attrs
                if not self.is_join(attr)
            }
        obj_dict["type"] = obj_type or type(self).__name__
        return obj_dict

    @staticmethod
    def serialize_list(
        models, obj_type=None, relations=False, milliseconds=False
    ):
        return [
            model.serialize(
                obj_type=obj_type,
                relations=relations,
                milliseconds=milliseconds,
            )
            for model in models
        ]
