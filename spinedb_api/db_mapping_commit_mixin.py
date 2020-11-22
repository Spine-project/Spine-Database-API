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

"""
Provides :class:`.QuickDatabaseMappingBase`.

:author: Manuel Marin (KTH)
:date:   11.8.2018
"""

from datetime import datetime, timezone
from .exception import SpineDBAPIError


class DatabaseMappingCommitMixin:
    """Provides methods to commit or rollback pending changes onto a Spine database.
    Unlike Diff..., there's no "staging area", i.e., all changes are applied directly on the 'original' tables.
    So no regrets. But it's much faster than maintaining the staging area and diff tables,
    so ideal for, e.g., Spine Toolbox's Importer that operates 'in one go'.
    """

    def __init__(self, *args, **kwargs):
        """Initialize class."""
        super().__init__(*args, **kwargs)
        self._transaction = None

    def has_pending_changes(self):
        return self._transaction is not None and self._transaction.is_active

    def _checked_execute(self, stmt, items):
        # Starts new transaction if needed, then execute.
        if not items:
            return
        if not self.has_pending_changes():
            self._start_new_transaction()
        self.connection.execute(stmt, items)

    def _start_new_transaction(self):
        self._transaction = self.connection.begin()
        user = self.username
        date = datetime.now(timezone.utc)
        ins = self._metadata.tables["commit"].insert().values(user=user, date=date, comment="")
        self._commit_id = self.connection.execute(ins).inserted_primary_key[0]

    def commit_session(self, comment):
        if not self.has_pending_changes():
            raise SpineDBAPIError("Nothing to commit.")
        commit = self._metadata.tables["commit"]
        user = self.username
        date = datetime.now(timezone.utc)
        upd = commit.update().where(commit.c.id == self._commit_id).values(user=user, date=date, comment=comment)
        self.connection.execute(upd)
        self._transaction.commit()

    def rollback_session(self):
        if not self.has_pending_changes():
            raise SpineDBAPIError("Nothing to rollback.")
        self._transaction.rollback()
