#############################################################################
# Copyright (C) 2017 - 2018 VTT Technical Research Centre of Finland
#
# This file is part of Spine Database API.
#
# Spine Spine Database API is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#############################################################################

"""
Classes to handle the Spine database object relational mapping.

:author: Manuel Marin (KTH)
:date:   11.8.2018
"""

import time
import logging
import json
import warnings
from .database_mapping import DatabaseMapping
from sqlalchemy import (
    MetaData,
    Table,
    Column,
    Integer,
    String,
    func,
    or_,
    and_,
    event,
    inspect,
)
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.exc import NoSuchTableError, DBAPIError
from sqlalchemy.sql.schema import (
    UniqueConstraint,
    PrimaryKeyConstraint,
    ForeignKeyConstraint,
    CheckConstraint,
)
from .exception import SpineDBAPIError, SpineTableNotFoundError, SpineIntegrityError
from .helpers import custom_generate_relationship, attr_dict
from ._check_diff_database_mapping import _CheckDiffDatabaseMapping
from datetime import datetime, timezone


# TODO: improve docstrings


class _AddDiffDatabaseMapping(_CheckDiffDatabaseMapping):
    def __init__(self, db_url, username=None, create_all=True, upgrade=False):
        """Initialize class."""
        super().__init__(
            db_url, username=username, create_all=create_all, upgrade=upgrade
        )

    def next_id_with_lock(self):
        """A 'next_id' item to use for adding new items."""
        next_id = self.session.query(self.NextId).one_or_none()
        if next_id:
            next_id.user = self.username
            next_id.date = datetime.now(timezone.utc)
        else:
            next_id = self.NextId(user=self.username, date=datetime.now(timezone.utc))
            self.session.add(next_id)
        try:
            # TODO: This flush is supposed to lock the database, so no one can steal our ids.... does it work?
            self.session.flush()
            return next_id
        except DBAPIError as e:
            # TODO: Find a way to try this again, or wait till the database is unlocked
            # Maybe listen for an event?
            self.session.rollback()
            raise SpineDBAPIError("Unable to get next id: {}".format(e.orig.args))

    def add_object_class(self, **kwargs):
        return self.add_object_classes(kwargs, strict=True)[0].one_or_none()

    def add_object(self, **kwargs):
        return self.add_objects(kwargs, strict=True)[0].one_or_none()

    def add_wide_relationship_class(self, **kwargs):
        return self.add_wide_relationship_classes(kwargs, strict=True)[0].one_or_none()

    def add_wide_relationship(self, **kwargs):
        return self.add_wide_relationships(kwargs, strict=True)[0].one_or_none()

    def add_parameter(self, **kwargs):
        return self.add_parameters(kwargs, strict=True)[0].one_or_none()

    def add_parameter_value(self, **kwargs):
        return self.add_parameter_values(kwargs, strict=True)[0].one_or_none()

    def get_or_add_object_class(self, **kwargs):
        return self.add_object_classes(kwargs, return_dups=True)[0].one_or_none()

    def get_or_add_object(self, **kwargs):
        return self.add_objects(kwargs, return_dups=True)[0].one_or_none()

    def get_or_add_parameter(self, **kwargs):
        return self.add_parameters(kwargs, return_dups=True)[0].one_or_none()

    def add_object_classes(self, *kwargs_list, strict=False, return_dups=False):
        """Add object classes to database.

        Args:
            kwargs_list (iter): list of dictionaries which correspond to the instances to add
            strict (bool): if True SpineIntegrityError are raised. Otherwise
                they are catched and returned as a log
            return_dups (bool): if True, duplicates are also returned

        Returns:
            object_classes (list): added instances
            intgr_error_log (list): list of integrity error messages
        """
        checked_kwargs_list, intgr_error_log = self.check_object_classes_for_insert(
            *kwargs_list, strict=strict
        )
        id_list = self._add_object_classes(*checked_kwargs_list)
        if return_dups:
            id_list.update(set(x.id for x in intgr_error_log if x.id))
        new_item_list = self.object_class_list(id_list=id_list)
        return new_item_list, intgr_error_log

    def _add_object_classes(self, *kwargs_list):
        """Add object classes to database without testing classes for integrity

        Args:
            kwargs_list (iter): list of dictionaries which correspond to the instances to add
            strict (bool): if True SpineIntegrityError are raised. Otherwise
                they are catched and returned as a log

        Returns:
            id_list (set): added instances' ids
        """
        next_id = self.next_id_with_lock()
        if next_id.object_class_id:
            id = next_id.object_class_id
        else:
            max_id = self.session.query(func.max(self.ObjectClass.id)).scalar()
            id = max_id + 1 if max_id else 1
        try:
            item_list = list()
            id_list = set(range(id, id + len(kwargs_list)))
            for kwargs in kwargs_list:
                kwargs["id"] = id
                item_list.append(kwargs)
                id += 1
            self.session.bulk_insert_mappings(self.DiffObjectClass, item_list)
            next_id.object_class_id = id
            self.session.commit()
            self.new_item_id["object_class"].update(id_list)
            return id_list
        except DBAPIError as e:
            self.session.rollback()
            msg = "DBAPIError while inserting object classes: {}".format(e.orig.args)
            raise SpineDBAPIError(msg)

    def add_objects(self, *kwargs_list, strict=False, return_dups=False):
        """Add objects to database.

        Args:
            kwargs_list (iter): list of dictionaries which correspond to the instances to add
            strict (bool): if True SpineIntegrityError are raised. Otherwise
                they are catched and returned as a log
            return_dups (bool): if True, duplicates are also returned

        Returns:
            objects (list): added instances
            intgr_error_log (list): list of integrity error messages
        """
        checked_kwargs_list, intgr_error_log = self.check_objects_for_insert(
            *kwargs_list, strict=strict
        )
        id_list = self._add_objects(*checked_kwargs_list)
        if return_dups:
            id_list.update(set(x.id for x in intgr_error_log if x.id))
        new_item_list = self.object_list(id_list=id_list)
        return new_item_list, intgr_error_log

    def _add_objects(self, *kwargs_list):
        """Add objects to database without checking integrity

        Args:
            kwargs_list (iter): list of dictionaries which correspond to the instances to add

        Returns:
            id_list (set): added instances' ids
        """
        next_id = self.next_id_with_lock()
        if next_id.object_id:
            id = next_id.object_id
        else:
            max_id = self.session.query(func.max(self.Object.id)).scalar()
            id = max_id + 1 if max_id else 1
        try:
            item_list = list()
            id_list = set(range(id, id + len(kwargs_list)))
            for kwargs in kwargs_list:
                kwargs["id"] = id
                item_list.append(kwargs)
                id += 1
            self.session.bulk_insert_mappings(self.DiffObject, item_list)
            next_id.object_id = id
            self.session.commit()
            self.new_item_id["object"].update(id_list)
            return id_list
        except DBAPIError as e:
            self.session.rollback()
            msg = "DBAPIError while inserting objects: {}".format(e.orig.args)
            raise SpineDBAPIError(msg)

    def add_wide_relationship_classes(
        self, *wide_kwargs_list, strict=False, return_dups=False
    ):
        """Add relationship classes to database.

        Args:
            wide_kwargs_list (iter): list of dictionaries which correspond to the instances to add
            strict (bool): if True SpineIntegrityError are raised. Otherwise
                they are catched and returned as a log
            return_dups (bool): if True, duplicates are also returned

        Returns:
            wide_relationship_classes (list): added instances
            intgr_error_log (list): list of integrity error messages
        """
        checked_wide_kwargs_list, intgr_error_log = self.check_wide_relationship_classes_for_insert(
            *wide_kwargs_list, strict=strict
        )
        id_list = self._add_wide_relationship_classes(*checked_wide_kwargs_list)
        if return_dups:
            id_list.update(set(x.id for x in intgr_error_log if x.id))
        new_item_list = self.wide_relationship_class_list(id_list=id_list)
        return new_item_list, intgr_error_log

    def _add_wide_relationship_classes(self, *wide_kwargs_list):
        """Add relationship classes to database without integrity check

        Args:
            wide_kwargs_list (iter): list of dictionaries which correspond to the instances to add
            strict (bool): if True SpineIntegrityError are raised. Otherwise
                they are catched and returned as a log

        Returns:
            id_list (set): added instances' ids
        """
        next_id = self.next_id_with_lock()
        if next_id.relationship_class_id:
            id = next_id.relationship_class_id
        else:
            max_id = self.session.query(func.max(self.RelationshipClass.id)).scalar()
            id = max_id + 1 if max_id else 1
        try:
            item_list = list()
            id_list = set(range(id, id + len(wide_kwargs_list)))
            for wide_kwargs in wide_kwargs_list:
                for dimension, object_class_id in enumerate(
                    wide_kwargs["object_class_id_list"]
                ):
                    narrow_kwargs = {
                        "id": id,
                        "dimension": dimension,
                        "object_class_id": object_class_id,
                        "name": wide_kwargs["name"],
                    }
                    item_list.append(narrow_kwargs)
                id += 1
            self.session.bulk_insert_mappings(self.DiffRelationshipClass, item_list)
            next_id.relationship_class_id = id
            self.session.commit()
            self.new_item_id["relationship_class"].update(id_list)
            return id_list
        except DBAPIError as e:
            self.session.rollback()
            msg = "DBAPIError while inserting relationship classes: {}".format(
                e.orig.args
            )
            raise SpineDBAPIError(msg)

    def add_wide_relationships(
        self, *wide_kwargs_list, strict=False, return_dups=False
    ):
        """Add relationships to database.

        Args:
            wide_kwargs_list (iter): list of dictionaries which correspond to the instances to add
            strict (bool): if True SpineIntegrityError are raised. Otherwise
                they are catched and returned as a log
            return_dups (bool): if True, duplicates are also returned

        Returns:
            wide_relationships (list): added instances
            intgr_error_log (list): list of integrity error messages
        """
        checked_wide_kwargs_list, intgr_error_log = self.check_wide_relationships_for_insert(
            *wide_kwargs_list, strict=strict
        )
        id_list = self._add_wide_relationships(*checked_wide_kwargs_list)
        if return_dups:
            id_list.update(set(x.id for x in intgr_error_log if x.id))
        new_item_list = self.wide_relationship_list(id_list=id_list)
        return new_item_list, intgr_error_log

    def _add_wide_relationships(self, *wide_kwargs_list):
        """Add relationships to database without integrity

        Args:
            wide_kwargs_list (iter): list of dictionaries which correspond to the instances to add

        Returns:
            id_list (set): added instances' ids
        """
        next_id = self.next_id_with_lock()
        if next_id.relationship_id:
            id = next_id.relationship_id
        else:
            max_id = self.session.query(func.max(self.Relationship.id)).scalar()
            id = max_id + 1 if max_id else 1
        try:
            item_list = list()
            id_list = set(range(id, id + len(wide_kwargs_list)))
            for wide_kwargs in wide_kwargs_list:
                for dimension, object_id in enumerate(wide_kwargs["object_id_list"]):
                    narrow_kwargs = {
                        "id": id,
                        "class_id": wide_kwargs["class_id"],
                        "dimension": dimension,
                        "object_id": object_id,
                        "name": wide_kwargs["name"],
                    }
                    item_list.append(narrow_kwargs)
                id += 1
            self.session.bulk_insert_mappings(self.DiffRelationship, item_list)
            next_id.relationship_id = id
            self.session.commit()
            self.new_item_id["relationship"].update(id_list)
            return id_list
        except DBAPIError as e:
            self.session.rollback()
            msg = "DBAPIError while inserting relationships: {}".format(e.orig.args)
            raise SpineDBAPIError(msg)

    def add_parameter_definitions(self, *kwargs_list, strict=False, return_dups=False):
        """Add parameter to database.

        Args:
            kwargs_list (iter): list of dictionaries which correspond to the instances to add
            strict (bool): if True SpineIntegrityError are raised. Otherwise
                they are catched and returned as a log
            return_dups (bool): if True, duplicates are also returned

        Returns:
            parameters (list): added instances
            intgr_error_log (list): list of integrity error messages
        """
        checked_kwargs_list, intgr_error_log = self.check_parameter_definitions_for_insert(
            *kwargs_list, strict=strict
        )
        id_list = self._add_parameters(*checked_kwargs_list)
        if return_dups:
            id_list.update(set(x.id for x in intgr_error_log if x.id))
        new_item_list = self.parameter_list(id_list=id_list)
        return new_item_list, intgr_error_log

    def _add_parameters(self, *kwargs_list):
        """Add parameter to database without integrity check

        Args:
            kwargs_list (iter): list of dictionaries which correspond to the instances to add

        Returns:
            id_list (set): added instances' ids
        """
        next_id = self.next_id_with_lock()
        if next_id.parameter_definition_id:
            id = next_id.parameter_definition_id
        else:
            max_id = self.session.query(func.max(self.ParameterDefinition.id)).scalar()
            id = max_id + 1 if max_id else 1
        try:
            item_list = list()
            id_list = set(range(id, id + len(kwargs_list)))
            for kwargs in kwargs_list:
                kwargs["id"] = id
                item_list.append(kwargs)
                id += 1
            self.session.bulk_insert_mappings(self.DiffParameterDefinition, item_list)
            next_id.parameter_definition_id = id
            self.session.commit()
            self.new_item_id["parameter_definition"].update(id_list)
            return id_list
        except DBAPIError as e:
            self.session.rollback()
            msg = "DBAPIError while inserting parameters: {}".format(e.orig.args)
            raise SpineDBAPIError(msg)

    def add_parameters(self, *kwargs_list, strict=False, return_dups=False):
        warnings.warn(
            "add_parameters is deprecated, use add_parameter_definitions instead",
            DeprecationWarning,
        )
        return self.add_parameter_definitions(
            *kwargs_list, strict=False, return_dups=False
        )

    def add_parameter_values(self, *kwargs_list, strict=False, return_dups=False):
        """Add parameter value to database.

        Args:
            kwargs_list (iter): list of dictionaries which correspond to the instances to add
            strict (bool): if True SpineIntegrityError are raised. Otherwise
                they are catched and returned as a log
            return_dups (bool): if True, duplicates are also returned

        Returns:
            parameter_values (list): added instances
            intgr_error_log (list): list of integrity error messages
        """
        # FIXME: this should be removed once the 'parameter_definition_id' comes in the kwargs
        for kwargs in kwargs_list:
            kwargs["parameter_definition_id"] = kwargs["parameter_id"]
        checked_kwargs_list, intgr_error_log = self.check_parameter_values_for_insert(
            *kwargs_list, strict=strict
        )
        id_list = self._add_parameter_values(*checked_kwargs_list)
        if return_dups:
            id_list.update(set(x.id for x in intgr_error_log if x.id))
        new_item_list = self.parameter_value_list(id_list=id_list)
        return new_item_list, intgr_error_log

    def _add_parameter_values(self, *kwargs_list):
        """Add parameter value to database.

        Returns:
            id_list (set): added instances' ids
        """
        next_id = self.next_id_with_lock()
        if next_id.parameter_value_id:
            id = next_id.parameter_value_id
        else:
            max_id = self.session.query(func.max(self.ParameterValue.id)).scalar()
            id = max_id + 1 if max_id else 1
        try:
            item_list = list()
            id_list = set(range(id, id + len(kwargs_list)))
            for kwargs in kwargs_list:
                kwargs["id"] = id
                item_list.append(kwargs)
                id += 1
            self.session.bulk_insert_mappings(self.DiffParameterValue, item_list)
            next_id.parameter_value_id = id
            self.session.commit()
            self.new_item_id["parameter_value"].update(id_list)
            return id_list
        except DBAPIError as e:
            self.session.rollback()
            msg = "DBAPIError while inserting parameter values: {}".format(e.orig.args)
            raise SpineDBAPIError(msg)

    def add_parameter_tags(self, *kwargs_list, strict=False, return_dups=False):
        """Add parameter tags to database.

        Args:
            kwargs_list (iter): list of dictionaries which correspond to the instances to add
            strict (bool): if True SpineIntegrityError are raised. Otherwise
                they are catched and returned as a log
            return_dups (bool): if True, duplicates are also returned

        Returns:
            parameter_tags (list): added instances
            intgr_error_log (list): list of integrity error messages
        """
        checked_kwargs_list, intgr_error_log = self.check_parameter_tags_for_insert(
            *kwargs_list, strict=strict
        )
        id_list = self._add_parameter_tags(*checked_kwargs_list)
        if return_dups:
            id_list.update(set(x.id for x in intgr_error_log if x.id))
        new_item_list = self.parameter_tag_list(id_list=id_list)
        return new_item_list, intgr_error_log

    def _add_parameter_tags(self, *kwargs_list):
        """Add parameter tags to database.

        Returns:
            id_list (set): added instances' ids
        """
        next_id = self.next_id_with_lock()
        if next_id.parameter_tag_id:
            id = next_id.parameter_tag_id
        else:
            max_id = self.session.query(func.max(self.ParameterTag.id)).scalar()
            id = max_id + 1 if max_id else 1
        try:
            item_list = list()
            id_list = set(range(id, id + len(kwargs_list)))
            for kwargs in kwargs_list:
                kwargs["id"] = id
                item_list.append(kwargs)
                id += 1
            self.session.bulk_insert_mappings(self.DiffParameterTag, item_list)
            next_id.parameter_tag_id = id
            self.session.commit()
            self.new_item_id["parameter_tag"].update(id_list)
            return id_list
        except DBAPIError as e:
            self.session.rollback()
            msg = "DBAPIError while inserting parameter tags: {}".format(e.orig.args)
            raise SpineDBAPIError(msg)

    def add_parameter_definition_tags(
        self, *kwargs_list, strict=False, return_dups=False
    ):
        """Add parameter definition tags to database.

        Args:
            kwargs_list (iter): list of dictionaries which correspond to the instances to add
            strict (bool): if True SpineIntegrityError are raised. Otherwise
                they are catched and returned as a log
            return_dups (bool): if True, duplicates are also returned

        Returns:
            parameter_definition_tags (list): added instances
            intgr_error_log (list): list of integrity error messages
        """
        checked_kwargs_list, intgr_error_log = self.check_parameter_definition_tags_for_insert(
            *kwargs_list, strict=strict
        )
        id_list = self._add_parameter_definition_tags(*checked_kwargs_list)
        if return_dups:
            id_list.update(set(x.id for x in intgr_error_log if x.id))
        new_item_list = self.parameter_definition_tag_list(id_list=id_list)
        return new_item_list, intgr_error_log

    def _add_parameter_definition_tags(self, *kwargs_list):
        """Add parameter definition tags to database.

        Returns:
            id_list (set): added instances' ids
        """
        next_id = self.next_id_with_lock()
        if next_id.parameter_definition_tag_id:
            id = next_id.parameter_definition_tag_id
        else:
            max_id = self.session.query(
                func.max(self.ParameterDefinitionTag.id)
            ).scalar()
            id = max_id + 1 if max_id else 1
        try:
            item_list = list()
            id_list = set(range(id, id + len(kwargs_list)))
            for kwargs in kwargs_list:
                kwargs["id"] = id
                item_list.append(kwargs)
                id += 1
            self.session.bulk_insert_mappings(
                self.DiffParameterDefinitionTag, item_list
            )
            next_id.parameter_definition_tag_id = id
            self.session.commit()
            self.new_item_id["parameter_definition_tag"].update(id_list)
            return id_list
        except DBAPIError as e:
            self.session.rollback()
            msg = "DBAPIError while inserting parameter definition tags: {}".format(
                e.orig.args
            )
            raise SpineDBAPIError(msg)

    def add_wide_parameter_value_lists(
        self, *wide_kwargs_list, strict=False, return_dups=False
    ):
        """Add wide parameter value_lists to database.

        Args:
            wide_kwargs_list (iter): list of dictionaries which correspond to the instances to add
            strict (bool): if True SpineIntegrityError are raised. Otherwise
                they are catched and returned as a log
            return_dups (bool): if True, duplicates are also returned

        Returns:
            parameter_value_lists (list): added instances
            intgr_error_log (list): list of integrity error messages
        """
        checked_wide_kwargs_list, intgr_error_log = self.check_wide_parameter_value_lists_for_insert(
            *wide_kwargs_list, strict=strict
        )
        id_list = self._add_wide_parameter_value_lists(*checked_wide_kwargs_list)
        if return_dups:
            id_list.update(set(x.id for x in intgr_error_log if x.id))
        new_item_list = self.wide_parameter_value_list_list(id_list=id_list)
        return new_item_list, intgr_error_log

    def _add_wide_parameter_value_lists(self, *wide_kwargs_list):
        """Add wide parameter value_lists to database.

        Returns:
            id_list (set): added instances' ids
        """
        next_id = self.next_id_with_lock()
        if next_id.parameter_value_list_id:
            id = next_id.parameter_value_list_id
        else:
            max_id = self.session.query(func.max(self.ParameterValueList.id)).scalar()
            id = max_id + 1 if max_id else 1
        try:
            item_list = list()
            id_list = set(range(id, id + len(wide_kwargs_list)))
            for wide_kwargs in wide_kwargs_list:
                for k, value in enumerate(wide_kwargs["value_list"]):
                    narrow_kwargs = {
                        "id": id,
                        "name": wide_kwargs["name"],
                        "value_index": k,
                        "value": value,
                    }
                    item_list.append(narrow_kwargs)
                id += 1
            self.session.bulk_insert_mappings(self.DiffParameterValueList, item_list)
            next_id.parameter_value_list_id = id
            self.session.commit()
            self.new_item_id["parameter_value_list"].update(id_list)
            return id_list
        except DBAPIError as e:
            self.session.rollback()
            msg = "DBAPIError while inserting parameter value lists: {}".format(
                e.orig.args
            )
            raise SpineDBAPIError(msg)