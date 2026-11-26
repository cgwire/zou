import logging

from sqlalchemy import func, orm
from sqlalchemy.exc import IntegrityError
from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.utils import date_helpers, fields

logger = logging.getLogger(__name__)


class BaseMixin(object):
    """
    This mixin gives every model its primary key, its audit timestamps and its
    CRUD shorthands. Models declare it as ``class Thing(db.Model, BaseMixin,
    SerializerMixin)``.

    The class follows two conventions:

    - Methods come in pairs. ``create``, ``update`` and ``delete`` commit,
      and roll back if an error occurs. Their ``*_no_commit`` counterparts
      only add the change to the session. Thus a caller can put many writes
      in one transaction and commit one time.
    - ``update`` and ``create`` accept relationship fields as lists of IDs,
      of dicts that hold an ID, or of loaded instances.
      ``_resolve_relations`` changes them into active records. It ignores,
      without an error, the IDs that match no row.

    ``db.Model`` comes before this class in the MRO, thus its definitions have
    priority. For this reason, this mixin does not define ``query`` or
    ``__repr__``. Flask-SQLAlchemy gives both, and Python never uses a
    definition on this mixin. If a model needs a better repr, it defines its
    own ``__repr__``, as about twelve models do.
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
        Return the active record with the given ID, or None if no row matches.
        """
        return db.session.get(cls, id)

    @classmethod
    def get_by(cls, *criterions, **kw):
        """
        Return the first active record that matches the given filters.
        """
        return cls.query.filter(*criterions).filter_by(**kw).first()

    @classmethod
    def get_by_case_insensitive(cls, *criterions, **kw):
        """
        Return an active record that matches the given filters. The comparison
        ignores the case of String values. The positional criterions add
        conditions, as in get_by. The query has no order, thus the result is
        any one of the matches. It only tells whether a match exists. If a
        caller needs the row itself, it must make the match unique. For
        example, it can exclude from the query the rows that it already knows.
        """
        filters = []
        for key, value in kw.items():
            column = getattr(cls, key)
            if isinstance(column.type, db.String):
                filters.append(func.lower(column) == func.lower(value))
            else:
                filters.append(column == value)

        return cls.query.filter(*criterions).filter(*filters).first()

    @classmethod
    def get_all(cls):
        """
        Return all the active records of the model.
        """
        return cls.query.all()

    @classmethod
    def get_all_by(cls, **kw):
        """
        Return all the active records that match the given filters.
        """
        return cls.query.filter_by(**kw).all()

    @classmethod
    def get_id_map(cls, field="shotgun_id"):
        """
        Return a dict that maps each value of the given field to the ID of its
        row. Mass imports use this dict to set foreign keys.
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
        Create an active record through the database session, then commit.
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
        Create an active record through the database session. This method does
        not commit.
        """
        kw.update(cls._resolve_relations(kw))
        instance = cls(**kw)
        db.session.add(instance)
        return instance

    @classmethod
    def get_or_create(cls, **kw):
        """
        Return the first active record that matches the given filters. If no
        record matches, create one with these filters as values, then commit.
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
        Set updated_at, add this instance to the session and commit. If an
        error occurs, roll back.
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
        Update the instance with the given data and commit. If an error occurs,
        roll back.
        """
        try:
            self.update_no_commit(data)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def update_no_commit(self, data):
        """
        Set the given data and updated_at on the instance. Ignore the keys that
        are not model attributes. This method does not commit.
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
        Delete the row of this instance through the database session, then
        commit.
        """
        try:
            self.delete_no_commit()
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def delete_no_commit(self):
        """
        Delete the row of this instance through the database session. This
        method does not commit.
        """
        db.session.delete(self)
        return True

    @classmethod
    def delete_all_by(cls, *criterions, **kw):
        """
        Delete the rows that match the given filters, then commit. Return the
        number of deleted rows.
        """
        result = cls.query.filter(*criterions).filter_by(**kw).delete()
        db.session.commit()
        return result

    @classmethod
    def delete_all_by_no_commit(cls, *criterions, **kw):
        """
        Delete the rows that match the given filters. This method does not
        commit. It expires the loaded instances, as the commit of delete_all_by
        does. Without this, a many-to-many collection loaded before still holds
        the objects that the deleted rows link. Then the flush that deletes the
        owner of this collection deletes those rows again. It finds no rows and
        raises a StaleDataError.
        """
        result = cls.query.filter(*criterions).filter_by(**kw).delete()
        db.session.expire_all()
        return result

    @classmethod
    def commit(cls):
        """
        Commit the pending changes. If the commit fails, roll back the session,
        so that the next request can use it.
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
        Map each relationship field of the data to a list of active records. A
        value can be an ID, a dict that holds an ID, or a loaded instance.
        Ignore the IDs that match no row. Leave out the fields that are not
        relationships.
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
        Link this instance to the given IDs through a link table, and add the
        rows that are missing. Do not change or remove the links that exist.
        Thus this method adds to the set, it does not replace it. Commit at the
        end.
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
        Create or update an instance of the model from data that comes from the
        Zou API. Return ``(instance, is_update)``. ``is_update`` is True if the
        method updated a row that exists, and False if it created a row.
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
        Create a list of instances of the model from data that comes from the
        Zou API.
        """
        if "data" in data_list:
            data_list = data_list["data"]
        for data in data_list:
            try:
                cls.create_from_import(data)
            except IntegrityError:
                # One broken row must not stop the import of the other rows.
                # create or update already rolled back the session.
                logger.error(
                    f"Failed to import {cls.__name__} {data.get('id')}",
                    exc_info=1,
                )

    @classmethod
    def delete_from_import(cls, instance_id):
        """
        If the entry with the given ID exists, delete it and commit. Return the
        ID.
        """
        instance = cls.get(instance_id)
        if instance is not None:
            instance.delete()
        return instance_id
