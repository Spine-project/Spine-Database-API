######################################################################################################################
# Copyright (C) 2017 - 2019 Spine project consortium
# This file is part of Spine Database API.
# Spine Database API is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser
# General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""Provides :class:`.DatabaseMappingBase`.

:author: Manuel Marin (KTH)
:date:   11.8.2018
"""
# TODO: Finish docstrings

import os
import logging
from types import MethodType
from sqlalchemy import create_engine, inspect, func, case, MetaData, Table, Column, Integer, false, true, and_
from sqlalchemy.sql.expression import label, Alias
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, aliased
from sqlalchemy.exc import DatabaseError, NoSuchTableError
from alembic.migration import MigrationContext
from alembic.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from alembic.config import Config
from .exception import SpineDBAPIError, SpineDBVersionError, SpineTableNotFoundError
from .helpers import (
    create_new_spine_database,
    compare_schemas,
    model_meta,
    custom_generate_relationship,
    _create_first_spine_database,
    Anyone,
    forward_sweep,
)
from .filters.url_tools import pop_filter_configs


logging.getLogger("alembic").setLevel(logging.CRITICAL)


class DatabaseMappingBase:
    """Base class for all database mappings.

    It provides the :meth:`query` method for custom db querying.
    """

    def __init__(self, db_url, username=None, upgrade=False, codename=None, create=False, apply_filters=True):
        """
        Args:
            db_url (str or URL): A URL in RFC-1738 format pointing to the database to be mapped.
            username (str): A user name. If ``None``, it gets replaced by the string ``"anon"``.
            upgrade (bool): Whether or not the db at the given URL should be upgraded to the most recent version.
            codename (str): A name that uniquely identifies the class instance within a client application.
            create (bool): Whether or not to create a Spine db at the given URL if it's not already.
            apply_filters (bool): Whether or not filters in the URL's query part are applied to the database map.
        """
        if isinstance(db_url, str):
            filter_configs, db_url = pop_filter_configs(db_url)
        else:
            filter_configs = db_url.query.pop("spinedbfilter", [])
        self._filter_configs = filter_configs if apply_filters else None
        self.db_url = db_url
        self.sa_url = make_url(self.db_url)
        self.username = username if username else "anon"
        self.codename = self._make_codename(codename)
        self.engine = self._create_engine(db_url, upgrade=upgrade, create=create)
        self.connection = self.engine.connect()
        self.session = Session(self.connection, autoflush=False)
        self.Alternative = None
        self.Scenario = None
        self.ScenarioAlternative = None
        self.Commit = None
        self.EntityClassType = None
        self.EntityClass = None
        self.EntityType = None
        self.Entity = None
        self.ObjectClass = None
        self.Object = None
        self.RelationshipClass = None
        self.Relationship = None
        self.RelationshipEntity = None
        self.RelationshipEntityClass = None
        self.EntityGroup = None
        self.ParameterDefinition = None
        self.ParameterValue = None
        self.ParameterTag = None
        self.ParameterDefinitionTag = None
        self.ParameterValueList = None
        self.Tool = None
        self.Feature = None
        self.ToolFeature = None
        self.ToolFeatureMethod = None
        self.Metadata = None
        self.ParameterValueMetadata = None
        self.EntityMetadata = None
        self.IdsForIn = None
        self._ids_for_in_clause_id = 0
        # class and entity type id
        self._object_class_type = None
        self._relationship_class_type = None
        self._object_entity_type = None
        self._relationship_entity_type = None
        # Subqueries that select everything from each table
        self._alternative_sq = None
        self._scenario_sq = None
        self._scenario_alternative_sq = None
        self._entity_class_sq = None
        self._entity_sq = None
        self._entity_class_type_sq = None
        self._entity_type_sq = None
        self._object_sq = None
        self._object_class_sq = None
        self._object_sq = None
        self._relationship_class_sq = None
        self._relationship_sq = None
        self._entity_group_sq = None
        self._parameter_definition_sq = None
        self._parameter_value_sq = None
        self._parameter_tag_sq = None
        self._parameter_definition_tag_sq = None
        self._parameter_value_list_sq = None
        self._feature_sq = None
        self._tool_sq = None
        self._tool_feature_sq = None
        self._tool_feature_method_sq = None
        self._metadata_sq = None
        self._parameter_value_metadata_sq = None
        self._entity_metadata_sq = None
        # Special convenience subqueries that join two or more tables
        self._ext_scenario_sq = None
        self._wide_scenario_sq = None
        self._linked_scenario_alternative_sq = None
        self._ext_linked_scenario_alternative_sq = None
        self._ext_object_sq = None
        self._ext_relationship_class_sq = None
        self._wide_relationship_class_sq = None
        self._ext_relationship_sq = None
        self._wide_relationship_sq = None
        self._ext_object_group_sq = None
        self._entity_parameter_definition_sq = None
        self._object_parameter_definition_sq = None
        self._relationship_parameter_definition_sq = None
        self._object_parameter_value_sq = None
        self._relationship_parameter_value_sq = None
        self._ext_parameter_definition_tag_sq = None
        self._wide_parameter_definition_tag_sq = None
        self._wide_parameter_value_list_sq = None
        self._ext_feature_sq = None
        self._ext_tool_feature_sq = None
        self._ext_tool_feature_method_sq = None
        self._ext_parameter_value_metadata_sq = None
        self._ext_entity_metadata_sq = None
        self._table_to_sq_attr = {}
        # Table to class map for convenience
        self.table_to_class = {
            "alternative": "Alternative",
            "scenario": "Scenario",
            "scenario_alternative": "ScenarioAlternative",
            "commit": "Commit",
            "entity_class": "EntityClass",
            "entity_class_type": "EntityClassType",
            "entity": "Entity",
            "entity_type": "EntityType",
            "object": "Object",
            "object_class": "ObjectClass",
            "relationship_class": "RelationshipClass",
            "relationship": "Relationship",
            "relationship_entity": "RelationshipEntity",
            "relationship_entity_class": "RelationshipEntityClass",
            "entity_group": "EntityGroup",
            "parameter_definition": "ParameterDefinition",
            "parameter_value": "ParameterValue",
            "parameter_tag": "ParameterTag",
            "parameter_definition_tag": "ParameterDefinitionTag",
            "parameter_value_list": "ParameterValueList",
            "tool": "Tool",
            "feature": "Feature",
            "tool_feature": "ToolFeature",
            "tool_feature_method": "ToolFeatureMethod",
            "metadata": "Metadata",
            "parameter_value_metadata": "ParameterValueMetadata",
            "entity_metadata": "EntityMetadata",
        }
        # Table primary ids map:
        self.table_ids = {
            "relationship_entity_class": "entity_class_id",
            "object_class": "entity_class_id",
            "relationship_class": "entity_class_id",
            "object": "entity_id",
            "relationship": "entity_id",
            "relationship_entity": "entity_id",
        }
        self._create_mapping()
        self._create_ids_for_in()

    def _make_codename(self, codename):
        if codename:
            return str(codename)
        if self.sa_url.drivername == "sqlite":
            return os.path.basename(self.sa_url.database)
        return self.sa_url.database

    def _create_engine(self, db_url, upgrade=False, create=False):
        """Create engine.

        Args
            db_url (str): A URL to be passed to sqlalchemy.create_engine
            upgrade (bool, optional): If True, upgrade the db to the latest version.
            create (bool, optional): If True, create a new Spine db at the given url if none found.

        Returns
            Engine
        """
        try:
            engine = create_engine(db_url)
            with engine.connect():
                pass
        except Exception as e:
            raise SpineDBAPIError(
                f"Could not connect to '{db_url}': {str(e)}. "
                f"Please make sure that '{db_url}' is a valid sqlalchemy URL."
            )
        config = Config()
        config.set_main_option("script_location", "spinedb_api:alembic")
        script = ScriptDirectory.from_config(config)
        head = script.get_current_head()
        with engine.connect() as connection:
            migration_context = MigrationContext.configure(connection)
            try:
                current = migration_context.get_current_revision()
            except DatabaseError as error:
                raise SpineDBAPIError(str(error))
            if current is None:
                # No revision information. Check that the schema of the given url corresponds to a 'first' Spine db
                # Otherwise we either raise or create a new Spine db at the url.
                ref_engine = _create_first_spine_database("sqlite://")
                if not compare_schemas(engine, ref_engine):
                    if not create:
                        raise SpineDBAPIError(
                            "Unable to determine db revision. "
                            f"Please check that\n\n\t{self.db_url}\n\nis the URL of a valid Spine db."
                        )
                    return create_new_spine_database(db_url)
            if current != head:
                if not upgrade:
                    raise SpineDBVersionError(url=self.db_url, current=current, expected=head)

                # Upgrade function
                def upgrade_to_head(rev, context):
                    return script._upgrade_revs("head", rev)

                with EnvironmentContext(
                    config,
                    script,
                    fn=upgrade_to_head,
                    as_sql=False,
                    starting_rev=None,
                    destination_rev="head",
                    tag=None,
                ) as environment_context:
                    environment_context.configure(connection=connection, target_metadata=model_meta)
                    with environment_context.begin_transaction():
                        environment_context.run_migrations()
        return engine

    def _create_mapping(self):
        """Create ORM."""
        Base = automap_base()
        Base.prepare(self.engine, reflect=True, generate_relationship=custom_generate_relationship)
        not_found = []
        for tablename, classname in self.table_to_class.items():
            try:
                setattr(self, classname, getattr(Base.classes, tablename))
            except (NoSuchTableError, AttributeError):
                not_found.append(tablename)
        if not_found:
            raise SpineTableNotFoundError(not_found, self.db_url)

    def reconnect(self):
        self.connection = self.engine.connect()

    def _create_ids_for_in(self):
        """Create `ids_for_in` table if not exists and map it."""
        metadata = MetaData()
        ids_for_in_table = Table(
            "ids_for_in",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("clause_id", Integer),
            Column("id_for_in", Integer),
            prefixes=["TEMPORARY"],
        )
        ids_for_in_table.create(self.engine, checkfirst=True)
        metadata.create_all(self.connection)
        Base = automap_base(metadata=metadata)
        Base.prepare()
        self.IdsForIn = Base.classes.ids_for_in

    def in_(self, column, ids):
        """Returns an expression equivalent to ``column.in_(ids)`` that shouldn't trigger ``too many sql variables`` in sqlite.
        The strategy is to insert the ids in the temp table ``ids_for_in`` and then query them.
        """
        if Anyone in ids:
            return true()
        if not ids:
            return false()
        # NOTE: We need to isolate ids by clause, since there might be multiple clauses using this function in the same query.
        # TODO: Try to find something better
        self._ids_for_in_clause_id += 1
        clause_id = self._ids_for_in_clause_id
        self.session.bulk_insert_mappings(self.IdsForIn, ({"id_for_in": id_, "clause_id": clause_id} for id_ in ids))
        return column.in_(self.query(self.IdsForIn.id_for_in).filter_by(clause_id=clause_id))

    def _make_table_to_sq_attr(self):
        """Returns a dict mapping table names to subquery attribute names, involving that table.
        """
        # This 'loads' our subquery attributes
        for attr in dir(self):
            getattr(self, attr)
        table_to_sq_attr = {}
        for attr, val in vars(self).items():
            if not isinstance(val, Alias):
                continue
            tables = set()

            def _func(x):
                if isinstance(x, Table):
                    tables.add(x.name)  # pylint: disable=cell-var-from-loop

            forward_sweep(val, _func)
            # Now `tables` contains all tables related to `val`
            for table in tables:
                table_to_sq_attr.setdefault(table, set()).add(attr)
        return table_to_sq_attr

    def _clear_subqueries(self, *tablenames):
        """Set to `None` subquery attributes involving the affected tables.
        This forces the subqueries to be refreshed when the corresponding property is accessed.
        """
        attrs = set(attr for table in tablenames for attr in self._table_to_sq_attr.get(table, []))
        for attr in attrs:
            setattr(self, attr, None)

    def query(self, *args, **kwargs):
        """Return a sqlalchemy :class:`~sqlalchemy.orm.query.Query` object applied
        to this :class:`.DatabaseMappingBase`.

        To perform custom ``SELECT`` statements, call this method with one or more of the class documented
        :class:`~sqlalchemy.sql.expression.Alias` properties. For example, to select the object class with
        ``id`` equal to 1::

            from spinedb_api import DatabaseMapping
            url = 'sqlite:///spine.db'
            ...
            db_map = DatabaseMapping(url)
            db_map.query(db_map.object_class_sq).filter_by(id=1).one_or_none()

        To perform more complex queries, just use this method in combination with the SQLAlchemy API.
        For example, to select all object class names and the names of their objects concatenated in a string::

            from sqlalchemy import func

            db_map.query(
                db_map.object_class_sq.c.name, func.group_concat(db_map.object_sq.c.name)
            ).filter(
                db_map.object_sq.c.class_id == db_map.object_class_sq.c.id
            ).group_by(db_map.object_class_sq.c.name).all()
        """
        return self.session.query(*args, **kwargs)

    def _subquery(self, tablename):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM {tablename}

        :param str tablename: A string indicating the table to be queried.
        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        classname = self.table_to_class[tablename]
        class_ = getattr(self, classname)
        return self.query(*[c.label(c.name) for c in inspect(class_).mapper.columns]).subquery()

    @property
    def alternative_sq(self):
        if self._alternative_sq is None:
            self._alternative_sq = self._subquery("alternative")
        return self._alternative_sq

    @property
    def scenario_sq(self):
        if self._scenario_sq is None:
            self._scenario_sq = self._subquery("scenario")
        return self._scenario_sq

    @property
    def scenario_alternative_sq(self):
        if self._scenario_alternative_sq is None:
            self._scenario_alternative_sq = self._subquery("scenario_alternative")
        return self._scenario_alternative_sq

    @property
    def object_class_type(self):
        if self._object_class_type is None:
            result = self.query(self.entity_class_type_sq).filter(self.entity_class_type_sq.c.name == "object").first()
            self._object_class_type = result.id
        return self._object_class_type

    @property
    def relationship_class_type(self):
        if self._relationship_class_type is None:
            result = (
                self.query(self.entity_class_type_sq).filter(self.entity_class_type_sq.c.name == "relationship").first()
            )
            self._relationship_class_type = result.id
        return self._relationship_class_type

    @property
    def object_entity_type(self):
        if self._object_entity_type is None:
            result = self.query(self.entity_type_sq).filter(self.entity_type_sq.c.name == "object").first()
            self._object_entity_type = result.id
        return self._object_entity_type

    @property
    def relationship_entity_type(self):
        if self._relationship_entity_type is None:
            result = self.query(self.entity_type_sq).filter(self.entity_type_sq.c.name == "relationship").first()
            self._relationship_entity_type = result.id
        return self._relationship_entity_type

    @property
    def entity_class_type_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM class_type

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._entity_class_type_sq is None:
            self._entity_class_type_sq = self._subquery("entity_class_type")
        return self._entity_class_type_sq

    @property
    def entity_type_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM class_type

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._entity_type_sq is None:
            self._entity_type_sq = self._subquery("entity_type")
        return self._entity_type_sq

    @property
    def entity_class_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM class

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._entity_class_sq is None:
            self._entity_class_sq = self._make_entity_class_sq()
        return self._entity_class_sq

    @property
    def entity_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM entity

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._entity_sq is None:
            self._entity_sq = self._make_entity_sq()
        return self._entity_sq

    @property
    def object_class_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM object_class

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._object_class_sq is None:
            object_class_sq = self._subquery("object_class")
            self._object_class_sq = (
                self.query(
                    self.entity_class_sq.c.id.label("id"),
                    self.entity_class_sq.c.name.label("name"),
                    self.entity_class_sq.c.description.label("description"),
                    self.entity_class_sq.c.display_order.label("display_order"),
                    self.entity_class_sq.c.display_icon.label("display_icon"),
                    self.entity_class_sq.c.hidden.label("hidden"),
                    self.entity_class_sq.c.commit_id.label("commit_id"),
                )
                .filter(self.entity_class_sq.c.id == object_class_sq.c.entity_class_id)
                .subquery()
            )
        return self._object_class_sq

    @property
    def object_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM object

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._object_sq is None:
            object_sq = self._subquery("object")
            self._object_sq = (
                self.query(
                    self.entity_sq.c.id.label("id"),
                    self.entity_sq.c.class_id.label("class_id"),
                    self.entity_sq.c.name.label("name"),
                    self.entity_sq.c.description.label("description"),
                    self.entity_sq.c.commit_id.label("commit_id"),
                )
                .filter(self.entity_sq.c.id == object_sq.c.entity_id)
                .subquery()
            )
        return self._object_sq

    @property
    def relationship_class_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM relationship_class

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._relationship_class_sq is None:
            rel_ent_cls_sq = self._subquery("relationship_entity_class")
            self._relationship_class_sq = (
                self.query(
                    rel_ent_cls_sq.c.entity_class_id.label("id"),
                    rel_ent_cls_sq.c.dimension.label("dimension"),
                    rel_ent_cls_sq.c.member_class_id.label("object_class_id"),
                    self.entity_class_sq.c.name.label("name"),
                    self.entity_class_sq.c.description.label("description"),
                    self.entity_class_sq.c.hidden.label("hidden"),
                    self.entity_class_sq.c.commit_id.label("commit_id"),
                )
                .filter(self.entity_class_sq.c.id == rel_ent_cls_sq.c.entity_class_id)
                .subquery()
            )
        return self._relationship_class_sq

    @property
    def relationship_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM relationship

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._relationship_sq is None:
            rel_ent_sq = self._subquery("relationship_entity")
            self._relationship_sq = (
                self.query(
                    rel_ent_sq.c.entity_id.label("id"),
                    rel_ent_sq.c.dimension.label("dimension"),
                    rel_ent_sq.c.member_id.label("object_id"),
                    rel_ent_sq.c.entity_class_id.label("class_id"),
                    self.entity_sq.c.name.label("name"),
                    self.entity_sq.c.commit_id.label("commit_id"),
                )
                .filter(self.entity_sq.c.id == rel_ent_sq.c.entity_id)
                .subquery()
            )
        return self._relationship_sq

    @property
    def entity_group_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM entity_group

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._entity_group_sq is None:
            self._entity_group_sq = self._subquery("entity_group")
        return self._entity_group_sq

    @property
    def parameter_definition_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM parameter_definition

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """

        if self._parameter_definition_sq is None:
            self._parameter_definition_sq = self._make_parameter_definition_sq()
        return self._parameter_definition_sq

    @property
    def parameter_value_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM parameter_value

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._parameter_value_sq is None:
            self._parameter_value_sq = self._make_parameter_value_sq()
        return self._parameter_value_sq

    @property
    def parameter_tag_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM parameter_tag

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._parameter_tag_sq is None:
            self._parameter_tag_sq = self._subquery("parameter_tag")
        return self._parameter_tag_sq

    @property
    def parameter_definition_tag_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM parameter_definition_tag

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._parameter_definition_tag_sq is None:
            self._parameter_definition_tag_sq = self._subquery("parameter_definition_tag")
        return self._parameter_definition_tag_sq

    @property
    def parameter_value_list_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT * FROM parameter_value_list

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._parameter_value_list_sq is None:
            self._parameter_value_list_sq = self._subquery("parameter_value_list")
        return self._parameter_value_list_sq

    @property
    def feature_sq(self):
        if self._feature_sq is None:
            self._feature_sq = self._subquery("feature")
        return self._feature_sq

    @property
    def tool_sq(self):
        if self._tool_sq is None:
            self._tool_sq = self._subquery("tool")
        return self._tool_sq

    @property
    def tool_feature_sq(self):
        if self._tool_feature_sq is None:
            self._tool_feature_sq = self._subquery("tool_feature")
        return self._tool_feature_sq

    @property
    def tool_feature_method_sq(self):
        if self._tool_feature_method_sq is None:
            self._tool_feature_method_sq = self._subquery("tool_feature_method")
        return self._tool_feature_method_sq

    @property
    def metadata_sq(self):
        if self._metadata_sq is None:
            self._metadata_sq = self._subquery("metadata")
        return self._metadata_sq

    @property
    def parameter_value_metadata_sq(self):
        if self._parameter_value_metadata_sq is None:
            self._parameter_value_metadata_sq = self._subquery("parameter_value_metadata")
        return self._parameter_value_metadata_sq

    @property
    def entity_metadata_sq(self):
        if self._entity_metadata_sq is None:
            self._entity_metadata_sq = self._subquery("entity_metadata")
        return self._entity_metadata_sq

    @property
    def ext_scenario_sq(self):
        if self._ext_scenario_sq is None:
            self._ext_scenario_sq = (
                self.query(
                    self.scenario_sq.c.id.label("id"),
                    self.scenario_sq.c.name.label("name"),
                    self.scenario_sq.c.description.label("description"),
                    self.scenario_sq.c.active.label("active"),
                    self.scenario_alternative_sq.c.alternative_id.label("alternative_id"),
                    self.alternative_sq.c.name.label("alternative_name"),
                )
                .outerjoin(
                    self.scenario_alternative_sq, self.scenario_alternative_sq.c.scenario_id == self.scenario_sq.c.id
                )
                .outerjoin(
                    self.alternative_sq, self.alternative_sq.c.id == self.scenario_alternative_sq.c.alternative_id
                )
                .order_by(self.scenario_sq.c.id, self.scenario_alternative_sq.c.rank)
                .subquery()
            )
        return self._ext_scenario_sq

    @property
    def wide_scenario_sq(self):
        if self._wide_scenario_sq is None:
            self._wide_scenario_sq = (
                self.query(
                    self.ext_scenario_sq.c.id.label("id"),
                    self.ext_scenario_sq.c.name.label("name"),
                    self.ext_scenario_sq.c.description.label("description"),
                    self.ext_scenario_sq.c.active.label("active"),
                    func.group_concat(self.ext_scenario_sq.c.alternative_id).label("alternative_id_list"),
                    func.group_concat(self.ext_scenario_sq.c.alternative_name).label("alternative_name_list"),
                )
                .group_by(
                    self.ext_scenario_sq.c.id,
                    self.ext_scenario_sq.c.name,
                    self.ext_scenario_sq.c.description,
                    self.ext_scenario_sq.c.active,
                )
                .subquery()
            )
        return self._wide_scenario_sq

    @property
    def linked_scenario_alternative_sq(self):
        if self._linked_scenario_alternative_sq is None:
            scenario_next_alternative = aliased(self.scenario_alternative_sq)
            self._linked_scenario_alternative_sq = (
                self.query(
                    self.scenario_alternative_sq.c.id.label("id"),
                    self.scenario_alternative_sq.c.scenario_id.label("scenario_id"),
                    self.scenario_alternative_sq.c.alternative_id.label("alternative_id"),
                    scenario_next_alternative.c.alternative_id.label("next_alternative_id"),
                )
                .outerjoin(
                    scenario_next_alternative,
                    and_(
                        scenario_next_alternative.c.scenario_id == self.scenario_alternative_sq.c.scenario_id,
                        scenario_next_alternative.c.rank == self.scenario_alternative_sq.c.rank + 1,
                    ),
                )
                .order_by(self.scenario_alternative_sq.c.scenario_id, self.scenario_alternative_sq.c.rank)
                .subquery()
            )
        return self._linked_scenario_alternative_sq

    @property
    def ext_linked_scenario_alternative_sq(self):
        if self._ext_linked_scenario_alternative_sq is None:
            next_alternative = aliased(self.alternative_sq)
            self._ext_linked_scenario_alternative_sq = (
                self.query(
                    self.linked_scenario_alternative_sq.c.id.label("id"),
                    self.linked_scenario_alternative_sq.c.scenario_id.label("scenario_id"),
                    self.scenario_sq.c.name.label("scenario_name"),
                    self.linked_scenario_alternative_sq.c.alternative_id.label("alternative_id"),
                    self.alternative_sq.c.name.label("alternative_name"),
                    self.linked_scenario_alternative_sq.c.next_alternative_id.label("next_alternative_id"),
                    next_alternative.c.name.label("next_alternative_name"),
                )
                .filter(self.linked_scenario_alternative_sq.c.scenario_id == self.scenario_sq.c.id)
                .filter(self.alternative_sq.c.id == self.linked_scenario_alternative_sq.c.alternative_id)
                .outerjoin(
                    next_alternative, next_alternative.c.id == self.linked_scenario_alternative_sq.c.next_alternative_id
                )
                .subquery()
            )
        return self._ext_linked_scenario_alternative_sq

    @property
    def ext_object_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT
                o.id,
                o.class_id,
                oc.name AS class_name,
                o.name,
                o.description,
            FROM object AS o, object_class AS oc
            WHERE o.class_id = oc.id

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._ext_object_sq is None:
            self._ext_object_sq = (
                self.query(
                    self.object_sq.c.id.label("id"),
                    self.object_sq.c.class_id.label("class_id"),
                    self.object_class_sq.c.name.label("class_name"),
                    self.object_sq.c.name.label("name"),
                    self.object_sq.c.description.label("description"),
                )
                .filter(self.object_sq.c.class_id == self.object_class_sq.c.id)
                .subquery()
            )
        return self._ext_object_sq

    @property
    def ext_relationship_class_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT
                rc.id,
                rc.name,
                oc.id AS object_class_id,
                oc.name AS object_class_name
            FROM relationship_class AS rc, object_class AS oc
            WHERE rc.object_class_id = oc.id
            ORDER BY rc.id, rc.dimension

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._ext_relationship_class_sq is None:
            self._ext_relationship_class_sq = (
                self.query(
                    self.relationship_class_sq.c.id.label("id"),
                    self.relationship_class_sq.c.name.label("name"),
                    self.relationship_class_sq.c.description.label("description"),
                    self.object_class_sq.c.id.label("object_class_id"),
                    self.object_class_sq.c.name.label("object_class_name"),
                )
                .filter(self.relationship_class_sq.c.object_class_id == self.object_class_sq.c.id)
                .order_by(self.relationship_class_sq.c.id, self.relationship_class_sq.c.dimension)
                .subquery()
            )
        return self._ext_relationship_class_sq

    @property
    def wide_relationship_class_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT
                id,
                name,
                GROUP_CONCAT(object_class_id) AS object_class_id_list,
                GROUP_CONCAT(object_class_name) AS object_class_name_list
            FROM (
                SELECT
                    rc.id,
                    rc.name,
                    oc.id AS object_class_id,
                    oc.name AS object_class_name
                FROM relationship_class AS rc, object_class AS oc
                WHERE rc.object_class_id = oc.id
                ORDER BY rc.id, rc.dimension
            )
            GROUP BY id, name

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._wide_relationship_class_sq is None:
            self._wide_relationship_class_sq = (
                self.query(
                    self.ext_relationship_class_sq.c.id,
                    self.ext_relationship_class_sq.c.name,
                    self.ext_relationship_class_sq.c.description,
                    func.group_concat(self.ext_relationship_class_sq.c.object_class_id).label("object_class_id_list"),
                    func.group_concat(self.ext_relationship_class_sq.c.object_class_name).label(
                        "object_class_name_list"
                    ),
                )
                .group_by(self.ext_relationship_class_sq.c.id, self.ext_relationship_class_sq.c.name)
                .subquery()
            )
        return self._wide_relationship_class_sq

    @property
    def ext_relationship_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT
                r.id,
                r.class_id,
                r.name,
                o.id AS object_id,
                o.name AS object_name,
                o.class_id AS object_class_id,
            FROM relationship as r, object AS o
            WHERE r.object_id = o.id
            ORDER BY r.id, r.dimension

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._ext_relationship_sq is None:
            self._ext_relationship_sq = (
                self.query(
                    self.relationship_sq.c.id.label("id"),
                    self.relationship_sq.c.name.label("name"),
                    self.relationship_sq.c.class_id.label("class_id"),
                    self.wide_relationship_class_sq.c.name.label("class_name"),
                    self.ext_object_sq.c.id.label("object_id"),
                    self.ext_object_sq.c.name.label("object_name"),
                    self.ext_object_sq.c.class_id.label("object_class_id"),
                    self.ext_object_sq.c.class_name.label("object_class_name"),
                )
                .filter(self.relationship_sq.c.object_id == self.ext_object_sq.c.id)
                .filter(self.relationship_sq.c.class_id == self.wide_relationship_class_sq.c.id)
                .order_by(self.relationship_sq.c.id, self.relationship_sq.c.dimension)
                .subquery()
            )
        return self._ext_relationship_sq

    @property
    def wide_relationship_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT
                id,
                class_id,
                class_name,
                name,
                GROUP_CONCAT(object_id) AS object_id_list,
                GROUP_CONCAT(object_name) AS object_name_list
            FROM (
                SELECT
                    r.id,
                    r.class_id,
                    r.name,
                    o.id AS object_id,
                    o.name AS object_name
                FROM relationship as r, object AS o
                WHERE r.object_id = o.id
                ORDER BY r.id, r.dimension
            )
            GROUP BY id, class_id, name

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._wide_relationship_sq is None:
            self._wide_relationship_sq = (
                self.query(
                    self.ext_relationship_sq.c.id,
                    self.ext_relationship_sq.c.name,
                    self.ext_relationship_sq.c.class_id,
                    self.ext_relationship_sq.c.class_name,
                    func.group_concat(self.ext_relationship_sq.c.object_id).label("object_id_list"),
                    func.group_concat(self.ext_relationship_sq.c.object_name).label("object_name_list"),
                    func.group_concat(self.ext_relationship_sq.c.object_class_id).label("object_class_id_list"),
                    func.group_concat(self.ext_relationship_sq.c.object_class_name).label("object_class_name_list"),
                )
                .group_by(
                    self.ext_relationship_sq.c.id, self.ext_relationship_sq.c.class_id, self.ext_relationship_sq.c.name
                )
                .subquery()
            )
        return self._wide_relationship_sq

    @property
    def ext_object_group_sq(self):
        """A subquery of the form:

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._ext_object_group_sq is None:
            group_object = aliased(self.object_sq)
            member_object = aliased(self.object_sq)
            self._ext_object_group_sq = (
                self.query(
                    self.entity_group_sq.c.id.label("id"),
                    self.entity_group_sq.c.entity_class_id.label("class_id"),
                    self.entity_group_sq.c.entity_id.label("group_id"),
                    self.entity_group_sq.c.member_id.label("member_id"),
                    self.object_class_sq.c.name.label("class_name"),
                    group_object.c.name.label("group_name"),
                    member_object.c.name.label("member_name"),
                )
                .filter(self.entity_group_sq.c.entity_class_id == self.object_class_sq.c.id)
                .join(group_object, self.entity_group_sq.c.entity_id == group_object.c.id)
                .join(member_object, self.entity_group_sq.c.member_id == member_object.c.id)
                .subquery()
            )
        return self._ext_object_group_sq

    @property
    def entity_parameter_definition_sq(self):
        """
        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._entity_parameter_definition_sq is None:
            self._entity_parameter_definition_sq = (
                self.query(
                    self.parameter_definition_sq.c.id.label("id"),
                    self.parameter_definition_sq.c.entity_class_id,
                    self.entity_class_sq.c.name.label("entity_class_name"),
                    self.parameter_definition_sq.c.name.label("parameter_name"),
                    self.parameter_definition_sq.c.parameter_value_list_id.label("value_list_id"),
                    self.wide_parameter_value_list_sq.c.name.label("value_list_name"),
                    self.wide_parameter_definition_tag_sq.c.parameter_tag_id_list,
                    self.wide_parameter_definition_tag_sq.c.parameter_tag_list,
                    self.parameter_definition_sq.c.default_value,
                    self.parameter_definition_sq.c.description,
                )
                .filter(self.entity_class_sq.c.id == self.parameter_definition_sq.c.entity_class_id)
                .filter(self.wide_parameter_definition_tag_sq.c.id == self.parameter_definition_sq.c.id)
                .outerjoin(
                    self.wide_parameter_value_list_sq,
                    self.wide_parameter_value_list_sq.c.id == self.parameter_definition_sq.c.parameter_value_list_id,
                )
                .subquery()
            )
        return self._entity_parameter_definition_sq

    @property
    def object_parameter_definition_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT
                pd.id,
                oc.id AS object_class_id,
                oc.name AS object_class_name,
                pd.name AS parameter_name,
                wpvl.id AS value_list_id,
                wpvl.name AS value_list_name,
                wpdt.parameter_tag_id_list,
                wpdt.parameter_tag_list,
                pd.default_value
            FROM parameter_definition AS pd, object_class AS oc
            LEFT JOIN (
                SELECT
                    parameter_definition_id,
                    GROUP_CONCAT(parameter_tag_id) AS parameter_tag_id_list,
                    GROUP_CONCAT(parameter_tag) AS parameter_tag_list
                FROM (
                    SELECT
                        pdt.parameter_definition_id,
                        pt.id AS parameter_tag_id,
                        pt.tag AS parameter_tag
                    FROM parameter_definition_tag as pdt, parameter_tag AS pt
                    WHERE pdt.parameter_tag_id = pt.id
                )
                GROUP BY parameter_definition_id
            ) AS wpdt
            ON wpdt.parameter_definition_id = pd.id
            LEFT JOIN (
                SELECT
                    id,
                    name,
                    GROUP_CONCAT(value) AS value_list
                FROM (
                    SELECT id, name, value
                    FROM parameter_value_list
                    ORDER BY id, value_index
                )
                GROUP BY id, name
            ) AS wpvl
            ON wpvl.id = pd.parameter_value_list_id
            WHERE pd.object_class_id = oc.id

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._object_parameter_definition_sq is None:
            self._object_parameter_definition_sq = (
                self.query(
                    self.parameter_definition_sq.c.id.label("id"),
                    self.parameter_definition_sq.c.entity_class_id,
                    self.object_class_sq.c.id.label("object_class_id"),
                    self.object_class_sq.c.name.label("object_class_name"),
                    self.parameter_definition_sq.c.name.label("parameter_name"),
                    self.parameter_definition_sq.c.parameter_value_list_id.label("value_list_id"),
                    self.wide_parameter_value_list_sq.c.name.label("value_list_name"),
                    self.wide_parameter_definition_tag_sq.c.parameter_tag_id_list,
                    self.wide_parameter_definition_tag_sq.c.parameter_tag_list,
                    self.parameter_definition_sq.c.default_value,
                    self.parameter_definition_sq.c.description,
                )
                .filter(self.object_class_sq.c.id == self.parameter_definition_sq.c.object_class_id)
                .filter(self.wide_parameter_definition_tag_sq.c.id == self.parameter_definition_sq.c.id)
                .outerjoin(
                    self.wide_parameter_value_list_sq,
                    self.wide_parameter_value_list_sq.c.id == self.parameter_definition_sq.c.parameter_value_list_id,
                )
                .subquery()
            )
        return self._object_parameter_definition_sq

    @property
    def relationship_parameter_definition_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT
                pd.id,
                wrc.id AS relationship_class_id,
                wrc.name AS relationship_class_name,
                wrc.object_class_id_list,
                wrc.object_class_name_list,
                pd.name AS parameter_name,
                wpvl.id AS value_list_id,
                wpvl.name AS value_list_name,
                wpdt.parameter_tag_id_list,
                wpdt.parameter_tag_list,
                pd.default_value
            FROM
                parameter_definition AS pd,
                (
                    SELECT
                        id,
                        name,
                        GROUP_CONCAT(object_class_id) AS object_class_id_list,
                        GROUP_CONCAT(object_class_name) AS object_class_name_list
                    FROM (
                        SELECT
                            rc.id,
                            rc.name,
                            oc.id AS object_class_id,
                            oc.name AS object_class_name
                        FROM relationship_class AS rc, object_class AS oc
                        WHERE rc.object_class_id = oc.id
                        ORDER BY rc.id, rc.dimension
                    )
                    GROUP BY id, name
                ) AS wrc
            LEFT JOIN (
                SELECT
                    parameter_definition_id,
                    GROUP_CONCAT(parameter_tag_id) AS parameter_tag_id_list,
                    GROUP_CONCAT(parameter_tag) AS parameter_tag_list
                FROM (
                    SELECT
                        pdt.parameter_definition_id,
                        pt.id AS parameter_tag_id,
                        pt.tag AS parameter_tag
                    FROM parameter_definition_tag as pdt, parameter_tag AS pt
                    WHERE pdt.parameter_tag_id = pt.id
                )
                GROUP BY parameter_definition_id
            ) AS wpdt
            ON wpdt.parameter_definition_id = pd.id
            LEFT JOIN (
                SELECT
                    id,
                    name,
                    GROUP_CONCAT(value) AS value_list
                FROM (
                    SELECT id, name, value
                    FROM parameter_value_list
                    ORDER BY id, value_index
                )
                GROUP BY id, name
            ) AS wpvl
            ON wpvl.id = pd.parameter_value_list_id
            WHERE pd.relationship_class_id = wrc.id

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._relationship_parameter_definition_sq is None:
            self._relationship_parameter_definition_sq = (
                self.query(
                    self.parameter_definition_sq.c.id.label("id"),
                    self.parameter_definition_sq.c.entity_class_id,
                    self.wide_relationship_class_sq.c.id.label("relationship_class_id"),
                    self.wide_relationship_class_sq.c.name.label("relationship_class_name"),
                    self.wide_relationship_class_sq.c.object_class_id_list,
                    self.wide_relationship_class_sq.c.object_class_name_list,
                    self.parameter_definition_sq.c.name.label("parameter_name"),
                    self.parameter_definition_sq.c.parameter_value_list_id.label("value_list_id"),
                    self.wide_parameter_value_list_sq.c.name.label("value_list_name"),
                    self.wide_parameter_definition_tag_sq.c.parameter_tag_id_list,
                    self.wide_parameter_definition_tag_sq.c.parameter_tag_list,
                    self.parameter_definition_sq.c.default_value,
                    self.parameter_definition_sq.c.description,
                )
                .filter(self.parameter_definition_sq.c.relationship_class_id == self.wide_relationship_class_sq.c.id)
                .filter(self.wide_parameter_definition_tag_sq.c.id == self.parameter_definition_sq.c.id)
                .outerjoin(
                    self.wide_parameter_value_list_sq,
                    self.wide_parameter_value_list_sq.c.id == self.parameter_definition_sq.c.parameter_value_list_id,
                )
                .subquery()
            )
        return self._relationship_parameter_definition_sq

    @property
    def object_parameter_value_sq(self):
        """A subquery of the form:

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._object_parameter_value_sq is None:
            self._object_parameter_value_sq = (
                self.query(
                    self.parameter_value_sq.c.id.label("id"),
                    self.parameter_definition_sq.c.entity_class_id,
                    self.object_class_sq.c.id.label("object_class_id"),
                    self.object_class_sq.c.name.label("object_class_name"),
                    self.parameter_value_sq.c.entity_id,
                    self.object_sq.c.id.label("object_id"),
                    self.object_sq.c.name.label("object_name"),
                    self.parameter_definition_sq.c.id.label("parameter_id"),
                    self.parameter_definition_sq.c.name.label("parameter_name"),
                    self.parameter_value_sq.c.alternative_id,
                    self.alternative_sq.c.name.label("alternative_name"),
                    self.parameter_value_sq.c.value,
                )
                .filter(self.parameter_definition_sq.c.id == self.parameter_value_sq.c.parameter_definition_id)
                .filter(self.parameter_value_sq.c.object_id == self.object_sq.c.id)
                .filter(self.parameter_definition_sq.c.object_class_id == self.object_class_sq.c.id)
                .filter(self.parameter_value_sq.c.alternative_id == self.alternative_sq.c.id)
                .subquery()
            )
        return self._object_parameter_value_sq

    @property
    def relationship_parameter_value_sq(self):
        """A subquery of the form:


        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        # TODO: Should this also bring `value_list` and `tag_list`?
        if self._relationship_parameter_value_sq is None:
            self._relationship_parameter_value_sq = (
                self.query(
                    self.parameter_value_sq.c.id.label("id"),
                    self.parameter_definition_sq.c.entity_class_id,
                    self.wide_relationship_class_sq.c.id.label("relationship_class_id"),
                    self.wide_relationship_class_sq.c.name.label("relationship_class_name"),
                    self.wide_relationship_class_sq.c.object_class_id_list,
                    self.wide_relationship_class_sq.c.object_class_name_list,
                    self.parameter_value_sq.c.entity_id,
                    self.wide_relationship_sq.c.id.label("relationship_id"),
                    self.wide_relationship_sq.c.object_id_list,
                    self.wide_relationship_sq.c.object_name_list,
                    self.parameter_definition_sq.c.id.label("parameter_id"),
                    self.parameter_definition_sq.c.name.label("parameter_name"),
                    self.parameter_value_sq.c.alternative_id,
                    self.alternative_sq.c.name.label("alternative_name"),
                    self.parameter_value_sq.c.value,
                )
                .filter(self.parameter_definition_sq.c.id == self.parameter_value_sq.c.parameter_definition_id)
                .filter(self.parameter_value_sq.c.relationship_id == self.wide_relationship_sq.c.id)
                .filter(self.parameter_definition_sq.c.relationship_class_id == self.wide_relationship_class_sq.c.id)
                .filter(self.parameter_value_sq.c.alternative_id == self.alternative_sq.c.id)
                .subquery()
            )
        return self._relationship_parameter_value_sq

    @property
    def ext_parameter_definition_tag_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT
                pdt.parameter_definition_id,
                pt.id AS parameter_tag_id,
                pt.tag AS parameter_tag
            FROM parameter_definition_tag as pdt, parameter_tag AS pt
            WHERE pdt.parameter_tag_id = pt.id

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._ext_parameter_definition_tag_sq is None:
            self._ext_parameter_definition_tag_sq = (
                self.query(
                    self.parameter_definition_sq.c.id.label("parameter_definition_id"),
                    self.parameter_definition_tag_sq.c.parameter_tag_id.label("parameter_tag_id"),
                    self.parameter_tag_sq.c.tag.label("parameter_tag"),
                )
                .outerjoin(
                    self.parameter_definition_tag_sq,
                    self.parameter_definition_tag_sq.c.parameter_definition_id == self.parameter_definition_sq.c.id,
                )
                .outerjoin(
                    self.parameter_tag_sq,
                    self.parameter_tag_sq.c.id == self.parameter_definition_tag_sq.c.parameter_tag_id,
                )
                .subquery()
            )
        return self._ext_parameter_definition_tag_sq

    @property
    def wide_parameter_definition_tag_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT
                parameter_definition_id,
                GROUP_CONCAT(parameter_tag_id) AS parameter_tag_id_list,
                GROUP_CONCAT(parameter_tag) AS parameter_tag_list
            FROM (
                SELECT
                    pdt.parameter_definition_id,
                    pt.id AS parameter_tag_id,
                    pt.tag AS parameter_tag
                FROM parameter_definition_tag as pdt, parameter_tag AS pt
                WHERE pdt.parameter_tag_id = pt.id
            )
            GROUP BY parameter_definition_id

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._wide_parameter_definition_tag_sq is None:
            self._wide_parameter_definition_tag_sq = (
                self.query(
                    self.ext_parameter_definition_tag_sq.c.parameter_definition_id.label("id"),
                    func.group_concat(self.ext_parameter_definition_tag_sq.c.parameter_tag_id).label(
                        "parameter_tag_id_list"
                    ),
                    func.group_concat(self.ext_parameter_definition_tag_sq.c.parameter_tag).label("parameter_tag_list"),
                )
                .group_by(self.ext_parameter_definition_tag_sq.c.parameter_definition_id)
                .subquery()
            )
        return self._wide_parameter_definition_tag_sq

    @property
    def wide_parameter_value_list_sq(self):
        """A subquery of the form:

        .. code-block:: sql

            SELECT
                id,
                name,
                GROUP_CONCAT(value) AS value_list
            FROM (
                SELECT id, name, value
                FROM parameter_value_list
                ORDER BY id, value_index
            )
            GROUP BY id

        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._wide_parameter_value_list_sq is None:
            self._wide_parameter_value_list_sq = (
                self.query(
                    self.parameter_value_list_sq.c.id,
                    self.parameter_value_list_sq.c.name,
                    func.group_concat(self.parameter_value_list_sq.c.value_index, ";").label("value_index_list"),
                    func.group_concat(self.parameter_value_list_sq.c.value, ";").label("value_list"),
                ).group_by(self.parameter_value_list_sq.c.id, self.parameter_value_list_sq.c.name)
            ).subquery()
        return self._wide_parameter_value_list_sq

    @property
    def ext_feature_sq(self):
        """
        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._ext_feature_sq is None:
            self._ext_feature_sq = (
                self.query(
                    self.feature_sq.c.id.label("id"),
                    self.entity_class_sq.c.id.label("entity_class_id"),
                    self.entity_class_sq.c.name.label("entity_class_name"),
                    self.feature_sq.c.parameter_definition_id.label("parameter_definition_id"),
                    self.parameter_definition_sq.c.name.label("parameter_definition_name"),
                    self.feature_sq.c.parameter_value_list_id.label("parameter_value_list_id"),
                    self.wide_parameter_value_list_sq.c.name.label("parameter_value_list_name"),
                    self.feature_sq.c.description.label("description"),
                )
                .filter(self.feature_sq.c.parameter_definition_id == self.parameter_definition_sq.c.id)
                .filter(self.feature_sq.c.parameter_value_list_id == self.wide_parameter_value_list_sq.c.id)
                .filter(self.parameter_definition_sq.c.entity_class_id == self.entity_class_sq.c.id)
                .subquery()
            )
        return self._ext_feature_sq

    @property
    def ext_tool_feature_sq(self):
        """
        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._ext_tool_feature_sq is None:
            self._ext_tool_feature_sq = (
                self.query(
                    self.tool_feature_sq.c.id.label("id"),
                    self.tool_feature_sq.c.tool_id.label("tool_id"),
                    self.tool_sq.c.name.label("tool_name"),
                    self.tool_feature_sq.c.feature_id.label("feature_id"),
                    self.ext_feature_sq.c.entity_class_id.label("entity_class_id"),
                    self.ext_feature_sq.c.entity_class_name.label("entity_class_name"),
                    self.ext_feature_sq.c.parameter_definition_id.label("parameter_definition_id"),
                    self.ext_feature_sq.c.parameter_definition_name.label("parameter_definition_name"),
                    self.tool_feature_sq.c.parameter_value_list_id.label("parameter_value_list_id"),
                    self.ext_feature_sq.c.parameter_value_list_name.label("parameter_value_list_name"),
                    self.tool_feature_sq.c.required.label("required"),
                )
                .filter(self.tool_feature_sq.c.tool_id == self.tool_sq.c.id)
                .filter(self.tool_feature_sq.c.feature_id == self.ext_feature_sq.c.id)
                .filter(self.tool_feature_sq.c.parameter_value_list_id == self.ext_feature_sq.c.parameter_value_list_id)
                .subquery()
            )
        return self._ext_tool_feature_sq

    @property
    def ext_tool_feature_method_sq(self):
        """
        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._ext_tool_feature_method_sq is None:
            self._ext_tool_feature_method_sq = (
                self.query(
                    self.tool_feature_method_sq.c.id,
                    self.ext_tool_feature_sq.c.id.label("tool_feature_id"),
                    self.ext_tool_feature_sq.c.tool_id,
                    self.ext_tool_feature_sq.c.tool_name,
                    self.ext_tool_feature_sq.c.feature_id,
                    self.ext_tool_feature_sq.c.entity_class_id,
                    self.ext_tool_feature_sq.c.entity_class_name,
                    self.ext_tool_feature_sq.c.parameter_definition_id,
                    self.ext_tool_feature_sq.c.parameter_definition_name,
                    self.tool_feature_method_sq.c.parameter_value_list_id,
                    self.ext_tool_feature_sq.c.parameter_value_list_name,
                    self.tool_feature_method_sq.c.method_index,
                    self.parameter_value_list_sq.c.value.label("method"),
                )
                .filter(self.tool_feature_method_sq.c.tool_feature_id == self.ext_tool_feature_sq.c.id)
                .filter(
                    self.tool_feature_method_sq.c.parameter_value_list_id
                    == self.ext_tool_feature_sq.c.parameter_value_list_id
                )
                .filter(self.tool_feature_method_sq.c.parameter_value_list_id == self.parameter_value_list_sq.c.id)
                .filter(self.tool_feature_method_sq.c.method_index == self.parameter_value_list_sq.c.value_index)
                .subquery()
            )
        return self._ext_tool_feature_method_sq

    @property
    def ext_parameter_value_metadata_sq(self):
        """
        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._ext_parameter_value_metadata_sq is None:
            self._ext_parameter_value_metadata_sq = (
                self.query(
                    self.parameter_value_metadata_sq.c.id,
                    self.parameter_value_metadata_sq.c.parameter_value_id,
                    self.entity_sq.c.name.label("entity_name"),
                    self.parameter_definition_sq.c.name.label("parameter_name"),
                    self.alternative_sq.c.name.label("alternative_name"),
                    self.metadata_sq.c.name.label("metadata_name"),
                    self.metadata_sq.c.value.label("metadata_value"),
                )
                .filter(self.parameter_value_metadata_sq.c.parameter_value_id == self.parameter_value_sq.c.id)
                .filter(self.parameter_value_sq.c.parameter_definition_id == self.parameter_definition_sq.c.id)
                .filter(self.parameter_value_sq.c.entity_id == self.entity_sq.c.id)
                .filter(self.parameter_value_sq.c.alternative_id == self.alternative_sq.c.id)
                .filter(self.parameter_value_metadata_sq.c.metadata_id == self.metadata_sq.c.id)
                .subquery()
            )
        return self._ext_parameter_value_metadata_sq

    @property
    def ext_entity_metadata_sq(self):
        """
        :type: :class:`~sqlalchemy.sql.expression.Alias`
        """
        if self._ext_entity_metadata_sq is None:
            self._ext_entity_metadata_sq = (
                self.query(
                    self.entity_metadata_sq.c.id,
                    self.entity_metadata_sq.c.entity_id,
                    self.entity_sq.c.name.label("entity_name"),
                    self.metadata_sq.c.name.label("metadata_name"),
                    self.metadata_sq.c.value.label("metadata_value"),
                )
                .filter(self.entity_metadata_sq.c.entity_id == self.entity_sq.c.id)
                .filter(self.entity_metadata_sq.c.metadata_id == self.metadata_sq.c.id)
                .subquery()
            )
        return self._ext_entity_metadata_sq

    def override_entity_sq_maker(self, method):
        """
        Overrides the function that creates the ``entity_sq`` property.

        Args:
            method (Callable): a function that accepts a :class:`DatabaseMappingBase` as its argument and
                returns entity subquery as an :class:`Alias` object
        """
        self._make_entity_sq = MethodType(method, self)
        self._clear_subqueries("entity")

    def override_entity_class_sq_maker(self, method):
        """
        Overrides the function that creates the ``entity_class_sq`` property.

        Args:
            method (Callable): a function that accepts a :class:`DatabaseMappingBase` as its argument and
                returns entity class subquery as an :class:`Alias` object
        """
        self._make_entity_class_sq = MethodType(method, self)
        self._clear_subqueries("entity_class")

    def override_parameter_definition_sq_maker(self, method):
        """
        Overrides the function that creates the ``parameter_definition_sq`` property.

        Args:
            method (Callable): a function that accepts a :class:`DatabaseMappingBase` as its argument and
                returns parameter definition subquery as an :class:`Alias` object
        """
        self._make_parameter_definition_sq = MethodType(method, self)
        self._clear_subqueries("parameter_definition")

    def override_parameter_value_sq_maker(self, method):
        """
        Overrides the function that creates the ``parameter_value_sq`` property.

        Args:
            method (Callable): a function that accepts a :class:`DatabaseMappingBase` as its argument and
                returns parameter value subquery as an :class:`Alias` object
        """
        self._make_parameter_value_sq = MethodType(method, self)
        self._clear_subqueries("parameter_value")

    def _make_entity_sq(self):
        """
        Creates a subquery for entities.

        Returns:
            Alias: an entity subquery
        """
        return self._subquery("entity")

    def _make_entity_class_sq(self):
        """
        Creates a subquery for entity classes.

        Returns:
            Alias: an entity class subquery
        """
        return self._subquery("entity_class")

    def _make_parameter_definition_sq(self):
        """
        Creates a subquery for parameter definitions.

        Returns:
            Alias: a parameter definition subquery
        """
        par_def_sq = self._subquery("parameter_definition")

        object_class_case = case(
            [(self.entity_class_sq.c.type_id == self.object_class_type, par_def_sq.c.entity_class_id)], else_=None
        )
        rel_class_case = case(
            [(self.entity_class_sq.c.type_id == self.relationship_class_type, par_def_sq.c.entity_class_id)], else_=None
        )

        return (
            self.query(
                par_def_sq.c.id.label("id"),
                par_def_sq.c.name.label("name"),
                par_def_sq.c.description.label("description"),
                par_def_sq.c.data_type.label("data_type"),
                par_def_sq.c.entity_class_id,
                label("object_class_id", object_class_case),
                label("relationship_class_id", rel_class_case),
                par_def_sq.c.default_value.label("default_value"),
                par_def_sq.c.commit_id.label("commit_id"),
                par_def_sq.c.parameter_value_list_id.label("parameter_value_list_id"),
            )
            .join(self.entity_class_sq, self.entity_class_sq.c.id == par_def_sq.c.entity_class_id)
            .subquery()
        )

    def _make_parameter_value_sq(self):
        """
        Creates a subquery for parameter values.

        Returns:
            Alias: a parameter value subquery
        """
        par_val_sq = self._subquery("parameter_value")

        object_class_case = case(
            [(self.entity_class_sq.c.type_id == self.object_class_type, par_val_sq.c.entity_class_id)], else_=None
        )
        rel_class_case = case(
            [(self.entity_class_sq.c.type_id == self.relationship_class_type, par_val_sq.c.entity_class_id)], else_=None
        )
        object_entity_case = case(
            [(self.entity_sq.c.type_id == self.object_entity_type, par_val_sq.c.entity_id)], else_=None
        )
        rel_entity_case = case(
            [(self.entity_sq.c.type_id == self.relationship_entity_type, par_val_sq.c.entity_id)], else_=None
        )
        return (
            self.query(
                par_val_sq.c.id.label("id"),
                par_val_sq.c.parameter_definition_id,
                par_val_sq.c.entity_class_id,
                par_val_sq.c.entity_id,
                label("object_class_id", object_class_case),
                label("relationship_class_id", rel_class_case),
                label("object_id", object_entity_case),
                label("relationship_id", rel_entity_case),
                par_val_sq.c.value.label("value"),
                par_val_sq.c.commit_id.label("commit_id"),
                par_val_sq.c.alternative_id,
            )
            .join(self.entity_sq, self.entity_sq.c.id == par_val_sq.c.entity_id)
            .join(self.entity_class_sq, self.entity_class_sq.c.id == par_val_sq.c.entity_class_id)
            .subquery()
        )

    def _reset_mapping(self):
        """Delete all records from all tables but don't drop the tables.
        Useful for writing tests
        """
        self.query(self.Alternative).delete(synchronize_session=False)
        self.connection.execute("INSERT INTO alternative VALUES (1, 'Base', 'Base alternative', null)")
        self.query(self.Scenario).delete(synchronize_session=False)
        self.query(self.ScenarioAlternative).delete(synchronize_session=False)
        self.query(self.EntityClass).delete(synchronize_session=False)
        self.query(self.Entity).delete(synchronize_session=False)
        self.query(self.Object).delete(synchronize_session=False)
        self.query(self.ObjectClass).delete(synchronize_session=False)
        self.query(self.RelationshipEntityClass).delete(synchronize_session=False)
        self.query(self.RelationshipClass).delete(synchronize_session=False)
        self.query(self.Relationship).delete(synchronize_session=False)
        self.query(self.RelationshipEntity).delete(synchronize_session=False)
        self.query(self.EntityGroup).delete(synchronize_session=False)
        self.query(self.ParameterDefinition).delete(synchronize_session=False)
        self.query(self.ParameterValue).delete(synchronize_session=False)
        self.query(self.ParameterTag).delete(synchronize_session=False)
        self.query(self.ParameterDefinitionTag).delete(synchronize_session=False)
        self.query(self.ParameterValueList).delete(synchronize_session=False)
        self.query(self.Feature).delete(synchronize_session=False)
        self.query(self.Tool).delete(synchronize_session=False)
        self.query(self.ToolFeature).delete(synchronize_session=False)
        self.query(self.ToolFeatureMethod).delete(synchronize_session=False)
        self.query(self.Metadata).delete(synchronize_session=False)
        self.query(self.ParameterValueMetadata).delete(synchronize_session=False)
        self.query(self.EntityMetadata).delete(synchronize_session=False)
        self.query(self.Commit).delete(synchronize_session=False)
