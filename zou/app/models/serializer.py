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

    def serialize(
        self,
        obj_type=None,
        relations=False,
        milliseconds=False,
        ignored_attrs=[],
    ):
        attrs = inspect(self.__class__).all_orm_descriptors.keys()
        obj_dict = {
            attr: serialize_value(
                getattr(self, attr), milliseconds=milliseconds
            )
            for attr in attrs
            if attr not in ignored_attrs
            and (relations or not self.is_join(attr))
        }
        obj_dict["type"] = obj_type or type(self).__name__
        return obj_dict

    @staticmethod
    def serialize_list(
        models, obj_type=None, relations=False, milliseconds=False, **kwargs
    ):
        return [
            model.serialize(
                obj_type=obj_type,
                relations=relations,
                milliseconds=milliseconds,
                **kwargs
            )
            for model in models
        ]
