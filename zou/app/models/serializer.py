import sqlalchemy.orm as orm
from sqlalchemy.inspection import inspect
from zou.app.utils.fields import serialize_value


class SerializerMixin(object):
    """
    Helpers to facilitate JSON serialization of models.
    """

    @classmethod
    def _is_join_attr(cls, attr):
        descriptor = getattr(cls, attr)
        return hasattr(descriptor, "impl") and isinstance(
            descriptor.impl,
            orm.attributes.CollectionAttributeImpl,
        )

    @classmethod
    def _serializable_attrs(cls):
        """
        Return (all attrs, non-join attrs) for the model, computed once
        per class: inspecting descriptors for every attribute of every
        row dominated serialize_list profiles.
        """
        cached = cls.__dict__.get("_serializable_attrs_cache")
        if cached is None:
            attrs = tuple(inspect(cls).all_orm_descriptors.keys())
            plain = tuple(
                attr for attr in attrs if not cls._is_join_attr(attr)
            )
            cached = (attrs, plain)
            cls._serializable_attrs_cache = cached
        return cached

    def is_join(self, attr):
        return self._is_join_attr(attr)

    def serialize(
        self,
        obj_type=None,
        relations=False,
        milliseconds=False,
        ignored_attrs=[],
    ):
        all_attrs, plain_attrs = self._serializable_attrs()
        attrs = all_attrs if relations else plain_attrs
        obj_dict = {
            attr: serialize_value(
                getattr(self, attr), milliseconds=milliseconds
            )
            for attr in attrs
            if attr not in ignored_attrs
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
