######################################################################################################################
# Copyright (C) 2017 - 2020 Spine project consortium
# This file is part of Spine Database API.
# Spine Database API is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser
# General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
Provides functions to apply filtering based on scenario or alternatives to parameter value subqueries.

:author: Antti Soininen (VTT)
:date:   21.8.2020
"""
from functools import partial
from sqlalchemy import desc, func
from .exception import SpineDBAPIError


def apply_scenario_filter_to_parameter_value_sq(db_map, scenario):
    """
    Replaces parameter value subquery properties in ``db_map`` such that they return only values of given scenario.
    Args:
        db_map (DatabaseMappingBase): a database map to alter
        scenario (str or int): scenario name or id
    """
    state = _ScenarioFilterState(db_map, scenario)
    filtering = partial(_make_scenario_filtered_parameter_value_sq, state=state)
    db_map.override_parameter_value_sq_maker(filtering)


def apply_alternative_filter_to_parameter_value_sq(db_map, alternatives):
    """
    Replaces parameter value subquery properties in ``db_map`` such that they return only values of given alternatives.

    Args:
        db_map (DatabaseMappingBase): a database map to alter
        alternatives (Iterable of str or int, optional): alternative names or ids;
    """
    state = _AlternativeFilterState(db_map, alternatives)
    filtering = partial(_make_alternative_filtered_parameter_value_sq, state=state)
    db_map.override_parameter_value_sq_maker(filtering)


class _ScenarioFilterState:
    """
    Internal state for :func:`_make_scenario_filtered_parameter_value_sq`

    Attributes:
        original_parameter_value_sq (Alias): previous ``parameter_value_sq``
        scenario (int): id of active scenario
    """

    def __init__(self, db_map, scenario):
        """
        Args:
            db_map (DatabaseMappingBase): database the state applies to
            scenario (str or int): scenario name or ids
        """
        self.original_parameter_value_sq = db_map.parameter_value_sq
        self.scenario = self._scenario_id(db_map, scenario)

    @staticmethod
    def _scenario_id(db_map, scenario):
        """
        Finds id for given scenario and checks its existence.

        Args:
            db_map (DatabaseMappingBase): a database map
            scenario (str or int): scenario name or id

        Returns:
            int: scenario's id
        """
        if isinstance(scenario, str):
            scenario_id = db_map.query(db_map.scenario_sq.c.id).filter(db_map.scenario_sq.c.name == scenario).scalar()
            if scenario_id is None:
                raise SpineDBAPIError(f"Scenario '{scenario}' not found")
            return scenario_id
        id_in_db = db_map.query(db_map.scenario_sq.c.id).filter(db_map.scenario_sq.c.id == scenario).scalar()
        if id_in_db is None:
            raise SpineDBAPIError(f"Scenario id {scenario} not found")
        return scenario


class _AlternativeFilterState:
    """
    Internal state for :func:`_make_alternative_filtered_parameter_value_sq`

    Attributes:
        original_parameter_value_sq (Alias): previous ``parameter_value_sq``
        alternatives (Iterable of int): ids of alternatives overriding the active scenario
    """

    def __init__(self, db_map, alternatives):
        """
        Args:
            db_map (DatabaseMappingBase): database the state applies to
            alternatives (Iterable of str or int): alternative names of ids;
        """
        self.original_parameter_value_sq = db_map.parameter_value_sq
        self.alternatives = self._alternative_ids(db_map, alternatives) if alternatives is not None else None

    @staticmethod
    def _alternative_ids(db_map, alternatives):
        """
        Finds ids for given alternatives.

        Args:
            db_map (DatabaseMappingBase): a database map
            alternatives (Iterable): alternative names or ids

        Returns:
            list of int: alternative ids
        """
        alternative_names = [name for name in alternatives if isinstance(name, str)]
        ids_from_db = (
            db_map.query(db_map.alternative_sq.c.id, db_map.alternative_sq.c.name)
            .filter(db_map.in_(db_map.alternative_sq.c.name, alternative_names))
            .all()
        )
        names_in_db = [i.name for i in ids_from_db]
        if len(alternative_names) != len(names_in_db):
            missing_names = tuple(name for name in alternative_names if name not in names_in_db)
            raise SpineDBAPIError(f"Alternative(s) {missing_names} not found")
        ids = [i.id for i in ids_from_db]
        alternative_ids = [id_ for id_ in alternatives if isinstance(id_, int)]
        ids_from_db = (
            db_map.query(db_map.alternative_sq.c.id)
            .filter(db_map.in_(db_map.alternative_sq.c.id, alternative_ids))
            .all()
        )
        ids_in_db = [i.id for i in ids_from_db]
        if len(alternative_ids) != len(ids_from_db):
            missing_ids = tuple(i for i in alternative_ids if i not in ids_in_db)
            raise SpineDBAPIError(f"Alternative id(s) {missing_ids} not found")
        ids += ids_in_db
        return ids


def _make_scenario_filtered_parameter_value_sq(db_map, state):
    """
    Returns a scenario filtering subquery similar to :func:`DatabaseMappingBase.parameter_value_sq`.

    This function can be used as replacement for parameter value subquery maker in :class:`DatabaseMappingBase`.

    Args:
        db_map (DatabaseMappingBase): a database map
        state (_ScenarioFilterState): a state bound to ``db_map``

    Returns:
        Alias: a subquery for parameter value filtered by selected scenario
    """
    ext_parameter_value_sq = (
        db_map.query(
            state.original_parameter_value_sq,
            func.row_number()
            .over(
                partition_by=[
                    state.original_parameter_value_sq.c.parameter_definition_id,
                    state.original_parameter_value_sq.c.entity_id,
                ],
                order_by=desc(db_map.scenario_alternative_sq.c.rank),
            )
            .label("max_rank_row_number"),
        )
        .filter(state.original_parameter_value_sq.c.alternative_id == db_map.scenario_alternative_sq.c.alternative_id)
        .filter(db_map.scenario_alternative_sq.c.scenario_id == state.scenario)
    ).subquery()
    return db_map.query(ext_parameter_value_sq).filter(ext_parameter_value_sq.c.max_rank_row_number == 1).subquery()


def _make_alternative_filtered_parameter_value_sq(db_map, state):
    """
    Returns an alternative filtering subquery similar to :func:`DatabaseMappingBase.parameter_value_sq`.

    This function can be used as replacement for parameter value subquery maker in :class:`DatabaseMappingBase`.

    Args:
        db_map (DatabaseMappingBase): a database map
        state (_AlternativeFilterState): a state bound to ``db_map``

    Returns:
        Alias: a subquery for parameter value filtered by selected alternatives
    """
    subquery = state.original_parameter_value_sq
    return db_map.query(subquery).filter(db_map.in_(subquery.c.alternative_id, state.alternatives)).subquery()
