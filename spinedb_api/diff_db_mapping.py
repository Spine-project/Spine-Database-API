######################################################################################################################
# Copyright (C) 2017-2021 Spine project consortium
# This file is part of Spine Database API.
# Spine Database API is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser
# General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
Provides :class:`DiffDatabaseMapping`.

:author: Manuel Marin (KTH)
:date:   11.8.2018
"""

from sqlalchemy.sql.expression import bindparam
from sqlalchemy.exc import DBAPIError
from .db_mapping_query_mixin import DatabaseMappingQueryMixin
from .db_mapping_check_mixin import DatabaseMappingCheckMixin
from .db_mapping_add_mixin import DatabaseMappingAddMixin
from .db_mapping_update_mixin import DatabaseMappingUpdateMixin
from .diff_db_mapping_remove_mixin import DiffDatabaseMappingRemoveMixin
from .diff_db_mapping_commit_mixin import DiffDatabaseMappingCommitMixin
from .diff_db_mapping_base import DiffDatabaseMappingBase
from .filters.tools import apply_filter_stack, load_filters
from .exception import SpineDBAPIError


class DiffDatabaseMapping(
    DatabaseMappingQueryMixin,
    DatabaseMappingCheckMixin,
    DatabaseMappingAddMixin,
    DatabaseMappingUpdateMixin,
    DiffDatabaseMappingRemoveMixin,
    DiffDatabaseMappingCommitMixin,
    DiffDatabaseMappingBase,
):
    """A read-write database mapping.

    Provides methods to *stage* any number of changes (namely, ``INSERT``, ``UPDATE`` and ``REMOVE`` operations)
    over a Spine database, as well as to commit or rollback the batch of changes.

    For convenience, querying this mapping return results *as if* all the staged changes were already committed.

    :param str db_url: A database URL in RFC-1738 format pointing to the database to be mapped.
    :param str username: A user name. If ``None``, it gets replaced by the string ``"anon"``.
    :param bool upgrade: Whether or not the db at the given URL should be upgraded to the most recent version.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._filter_configs is not None:
            stack = load_filters(self._filter_configs)
            apply_filter_stack(self, stack)

    def _add_items(self, tablename, *items, return_items=False):
        items_to_add, ids = self._items_and_ids(tablename, *items)
        for tablename_ in self._do_add_items(tablename, *items_to_add):
            self.added_item_id[tablename_].update(ids)
            self._clear_subqueries(tablename_)
        return items_to_add if return_items else ids

    def _readd_items(self, tablename, *items):
        ids = set(x["id"] for x in items)
        for tablename_ in self._do_add_items(tablename, *items):
            self.added_item_id[tablename_].update(ids)
            self._clear_subqueries(tablename_)

    def _get_table_for_insert(self, tablename):
        return self._diff_table(tablename)

    def _get_items_for_update_and_insert(self, tablename, checked_items):
        """Return lists of items for update and insert.
        Items in the diff table should be updated, whereas items in the original table
        should be marked as dirty and inserted into the corresponding diff table."""
        items_for_update = list()
        items_for_insert = list()
        dirty_ids = set()
        updated_ids = set()
        id_field = self.table_ids.get(tablename, "id")
        for item in checked_items:
            id_ = item[id_field]
            updated_ids.add(id_)
            if id_ in self.added_item_id[tablename] | self.updated_item_id[tablename]:
                items_for_update.append(item)
            else:
                items_for_insert.append(item)
                dirty_ids.add(id_)
        return items_for_update, items_for_insert, dirty_ids, updated_ids

    def _update_items(self, tablename, *items):
        """Update items without checking integrity."""
        real_tablename = {
            "object_class": "entity_class",
            "relationship_class": "entity_class",
            "object": "entity",
            "relationship": "entity",
        }.get(tablename, tablename)
        items = self._items_with_type_id(tablename, *items)
        try:
            items_for_update, items_for_insert, dirty_ids, updated_ids = self._get_items_for_update_and_insert(
                real_tablename, items
            )
            self._do_update_items(real_tablename, items_for_update, items_for_insert)
            self._mark_as_dirty(real_tablename, dirty_ids)
            self.updated_item_id[real_tablename].update(dirty_ids)
            return updated_ids
        except DBAPIError as e:
            msg = f"DBAPIError while updating {tablename} items: {e.orig.args}"
            raise SpineDBAPIError(msg)

    def _do_update_items(self, tablename, items_for_update, items_for_insert):
        diff_table = self._diff_table(tablename)
        if items_for_update:
            upd = diff_table.update()
            for k in self._get_primary_key(tablename):
                upd = upd.where(getattr(diff_table.c, k) == bindparam(k))
            upd = upd.values({key: bindparam(key) for key in diff_table.columns.keys() & items_for_update[0].keys()})
            self._checked_execute(upd, items_for_update)
        ins = diff_table.insert()
        self._checked_execute(ins, items_for_insert)

    # pylint: disable=arguments-differ
    def update_wide_relationships(self, *items, check=True, strict=False, return_items=False, cache=None):
        """Update relationships."""
        if check:
            checked_items, intgr_error_log = self.check_wide_relationships_for_update(
                *items, strict=strict, cache=cache
            )
        else:
            checked_items, intgr_error_log = items, []
        updated_ids = self._update_wide_relationships(*checked_items)
        return checked_items if return_items else updated_ids, intgr_error_log

    def _update_wide_relationships(self, *items):
        """Update relationships without checking integrity."""
        items = self._items_with_type_id("relationship", *items)
        ent_items = []
        rel_ent_items = []
        for item in items:
            ent_item = item.copy()
            object_class_id_list = ent_item.pop("object_class_id_list", [])
            object_id_list = ent_item.pop("object_id_list", [])
            ent_items.append(ent_item)
            for dimension, (member_class_id, member_id) in enumerate(zip(object_class_id_list, object_id_list)):
                rel_ent_item = ent_item.copy()
                rel_ent_item["entity_class_id"] = rel_ent_item.pop("class_id", None)
                rel_ent_item["entity_id"] = rel_ent_item.pop("id", None)
                rel_ent_item["dimension"] = dimension
                rel_ent_item["member_class_id"] = member_class_id
                rel_ent_item["member_id"] = member_id
                rel_ent_items.append(rel_ent_item)
        try:
            ents_for_update, ents_for_insert, dirty_ent_ids, updated_ent_ids = self._get_items_for_update_and_insert(
                "entity", ent_items
            )
            (
                rel_ents_for_update,
                rel_ents_for_insert,
                dirty_rel_ent_ids,
                updated_rel_ent_ids,
            ) = self._get_items_for_update_and_insert("relationship_entity", rel_ent_items)
            self._do_update_items("entity", ents_for_update, ents_for_insert)
            self._mark_as_dirty("entity", dirty_ent_ids)
            self.updated_item_id["entity"].update(dirty_ent_ids)
            self._do_update_items("relationship_entity", rel_ents_for_update, rel_ents_for_insert)
            self._mark_as_dirty("relationship_entity", dirty_rel_ent_ids)
            self.updated_item_id["relationship_entity"].update(dirty_rel_ent_ids)
            return updated_ent_ids.union(updated_rel_ent_ids)
        except DBAPIError as e:
            msg = "DBAPIError while updating relationships: {}".format(e.orig.args)
            raise SpineDBAPIError(msg)
