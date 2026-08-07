import logging

from sqlalchemy_utils import UUIDType
from sqlalchemy import func, orm
from sqlalchemy.exc import IntegrityError
from zou.app import db
from zou.app.utils import date_helpers, fields

logger = logging.getLogger(__name__)


class BaseMixin(object):
    """
    Primary key, audit timestamps and the CRUD shorthands shared by every
    model. Models declare it as ``class Thing(db.Model, BaseMixin,
    SerializerMixin)``.

    Two conventions run through the class:

    - Methods come in pairs. ``create``/``update``/``delete`` commit and roll
      back on failure; their ``*_no_commit`` counterparts only stage the
      change, so a caller can group several writes into one transaction and
      commit once.
    - ``update`` and ``create`` accept relationship fields as lists of ids,
      dicts holding an id, or loaded instances. ``_resolve_relations`` turns
      them into ORM instances and silently drops the ids that match nothing.

    Note that ``db.Model`` sits before this class in the MRO, so anything it
    already defines wins. That is why there is no ``query`` and no
    ``__repr__`` here: Flask-SQLAlchemy provides both, and a definition on
    this mixin would never be reached. Models that want a friendlier repr
    define ``__repr__`` on themselves, as a dozen of them do.
    """

    id = db.Column(
        UUIDType(binary=False),
        primary_key=True,
        default=fields.gen_uuid,
    )

    # Audit fields
    created_at = db.Column(
        db.DateTime, default=date_helpers.get_utc_now_datetime
    )
    updated_at = db.Column(
        db.DateTime,
        default=date_helpers.get_utc_now_datetime,
        onupdate=date_helpers.get_utc_now_datetime,
    )

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, id):
        """
        Shorthand to retrieve data by id.
        """
        return db.session.get(cls, id)

    @classmethod
    def get_by(cls, *criterions, **kw):
        """
        Shorthand to retrieve data by using filters. It returns the first
        element of the returned data.
        """
        return cls.query.filter(*criterions).filter_by(**kw).first()

    @classmethod
    def get_by_case_insensitive(cls, **kw):
        """
        Shorthand to retrieve data by using filters. It returns the first
        element of the returned data without checking case for any String type value.
        """
        filters = []
        for key, value in kw.items():
            column = getattr(cls, key)
            if isinstance(column.type, db.String):
                filters.append(func.lower(column) == func.lower(value))
            else:
                filters.append(column == value)

        return cls.query.filter(*filters).first()

    @classmethod
    def get_all(cls):
        """
        Shorthand to retrieve all data for a model.
        """
        return cls.query.all()

    @classmethod
    def get_all_by(cls, **kw):
        """
        Shorthand to retrieve data by using filters.
        """
        return cls.query.filter_by(**kw).all()

    @classmethod
    def get_id_map(cls, field="shotgun_id"):
        """
        Build a map to easily match a field value with an id. It's useful during
        mass import to build foreign keys.
        """
        entry_map = {}
        entries = cls.query.all()
        for entry in entries:
            entry_map[getattr(entry, field)] = entry.id
        return entry_map

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, **kw):
        """
        Shorthand to create an entry via the database session.
        """

        try:
            instance = cls.create_no_commit(**kw)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return instance

    @classmethod
    def create_no_commit(cls, **kw):
        """
        Shorthand to create an entry via the database session without commiting
        the request.
        """
        kw.update(cls._resolve_relations(kw))
        instance = cls(**kw)
        db.session.add(instance)
        return instance

    @classmethod
    def get_or_create(cls, **kw):
        """
        Shorthand to retrieve data by using filters.
        """
        instance = cls.get_by(**kw)
        if instance is None:
            instance = cls.create(**kw)
        return instance

    # ------------------------------------------------------------------
    # Instance mutation
    # ------------------------------------------------------------------

    def save(self):
        """
        Shorthand to create an entry via the database session based on current
        instance fields.
        """
        try:
            self.updated_at = date_helpers.get_utc_now_datetime()
            db.session.add(self)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def update(self, data):
        """
        Shorthand to update an entry via the database session based on current
        instance fields.
        """
        try:
            self.update_no_commit(data)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def update_no_commit(self, data):
        """
        Shorthand to update an entry via the database session based on current
        instance fields. It doesn't generate a commit.
        """
        self.updated_at = date_helpers.get_utc_now_datetime()
        resolved = self._resolve_relations(data)
        for key, value in data.items():
            field_key = getattr(self.__class__, key, None)
            if not hasattr(field_key, "property"):
                continue
            setattr(self, key, resolved.get(key, value))
        db.session.add(self)

    def delete(self):
        """
        Shorthand to delete an entry via the database session based on current
        instance id.
        """
        try:
            self.delete_no_commit()
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def delete_no_commit(self):
        """
        Shorthand to delete an entry via the database session based on current
        instance id. The change is not commited.
        """
        db.session.delete(self)
        return True

    @classmethod
    def delete_all_by(cls, *criterions, **kw):
        """
        Shorthand to delete data by using filters.
        """
        result = cls.query.filter(*criterions).filter_by(**kw).delete()
        db.session.commit()
        return result

    @classmethod
    def commit(cls):
        """
        Commit the pending changes, rolling back the session on failure so
        it stays usable for the next request.
        """
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    # ------------------------------------------------------------------
    # Relations
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_relations(cls, data):
        """
        Map relationship fields of data to lists of ORM instances. Values
        can be ids, dicts holding an id or already-loaded instances;
        unknown ids are dropped. Non-relationship fields are left out.
        """
        resolved = {}
        for key, value in data.items():
            field_key = getattr(cls, key, None)
            if not hasattr(field_key, "property") or not isinstance(
                field_key.property, orm.properties.RelationshipProperty
            ):
                continue
            class_ = field_key.property.entity.class_
            values = []
            if value is not None:
                for id in value:
                    if isinstance(id, str):
                        v = class_.get(id)
                    elif isinstance(id, dict):
                        v = class_.get(id["id"])
                    else:
                        v = id
                    if v is not None:
                        values.append(v)
            resolved[key] = values
        return resolved

    def set_links(self, ids, LinkTable, field_left, field_right):
        """
        Point this instance at the given ids through a link table, adding
        the rows that are missing. Existing links are left untouched and
        none are removed, so this adds to the set, it does not replace it.
        """
        for id in ids:
            link = LinkTable.query.filter_by(
                **{field_left: self.id, field_right: id}
            ).first()
            if link is None:
                link = LinkTable(**{field_left: self.id, field_right: id})
                db.session.add(link)
        db.session.commit()

    # ------------------------------------------------------------------
    # Import from another Zou instance
    # ------------------------------------------------------------------

    @classmethod
    def create_from_import(cls, data):
        """
        Create a new instance of the model based on data that comes from the Zou
        API. Returns ``(instance, is_update)`` where ``is_update`` is True when
        an existing row was updated and False when a new row was created.
        """
        if "type" in data:
            del data["type"]
        previous_data = cls.get(data["id"])
        if previous_data is None:
            return cls.create(**data), False
        else:
            previous_data.update(data)
            return previous_data, True

    @classmethod
    def create_from_import_list(cls, data_list):
        """
        Create a list of instances of the model based on data that comes from
        the Zou API.
        """
        if "data" in data_list:
            data_list = data_list["data"]
        for data in data_list:
            try:
                cls.create_from_import(data)
            except IntegrityError:
                # One broken row must not lose the rest of the list. The
                # session was already rolled back by create/save.
                logger.error(
                    f"Failed to import {cls.__name__} {data.get('id')}",
                    exc_info=1,
                )

    @classmethod
    def delete_from_import(cls, instance_id):
        """
        Delete an entry and its related base on the entry id.
        """
        instance = cls.get(instance_id)
        if instance is not None:
            instance.delete()
        return instance_id
