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
Unit tests for ``alternative_value_filter`` module.

:author: Antti Soininen (VTT)
:date:   21.8.2020
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from sqlalchemy.engine.url import URL
from spinedb_api import (
    apply_alternative_filter_to_parameter_value_sq,
    apply_scenario_filter_to_parameter_value_sq,
    create_new_spine_database,
    DatabaseMapping,
    DiffDatabaseMapping,
    import_alternatives,
    import_object_classes,
    import_object_parameter_values,
    import_object_parameters,
    import_objects,
    import_relationship_classes,
    import_relationship_parameter_values,
    import_relationship_parameters,
    import_relationships,
    import_scenario_alternatives,
    import_scenarios,
)


class TestAlternativeValueFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp_dir = TemporaryDirectory()
        cls._db_url = URL("sqlite", database=Path(cls._temp_dir.name, "test_scenario_filter_mapping.sqlite").as_posix())

    def setUp(self):
        create_new_spine_database(self._db_url)
        self._out_map = DiffDatabaseMapping(self._db_url)
        self._db_map = DatabaseMapping(self._db_url)
        self._diff_db_map = DiffDatabaseMapping(self._db_url)

    def tearDown(self):
        self._out_map.connection.close()
        self._db_map.connection.close()
        self._diff_db_map.connection.close()

    def test_alternative_filter_without_scenarios_or_alternatives(self):
        self._build_data_without_scenarios_or_alternatives()
        self._out_map.commit_session("Add test data")
        for db_map in [self._db_map, self._diff_db_map]:
            apply_alternative_filter_to_parameter_value_sq(db_map, [])
            parameters = db_map.query(db_map.parameter_value_sq).all()
            self.assertEqual(parameters, [])

    def test_alternative_filter_without_scenarios_or_alternatives_uncommitted_data(self):
        self._build_data_without_scenarios_or_alternatives()
        apply_alternative_filter_to_parameter_value_sq(self._out_map, alternatives=[])
        parameters = self._out_map.query(self._out_map.parameter_value_sq).all()
        self.assertEqual(parameters, [])
        self._out_map.rollback_session()

    def _build_data_without_scenarios_or_alternatives(self):
        import_object_classes(self._out_map, ["object_class"])
        import_objects(self._out_map, [("object_class", "object")])
        import_object_parameters(self._out_map, [("object_class", "parameter")])
        import_object_parameter_values(self._out_map, [("object_class", "object", "parameter", 23.0)])

    def test_scenario_filter(self):
        self._build_data_with_single_scenario()
        self._out_map.commit_session("Add test data")
        for db_map in [self._db_map, self._diff_db_map]:
            apply_scenario_filter_to_parameter_value_sq(db_map, "scenario")
            parameters = db_map.query(db_map.parameter_value_sq).all()
            self.assertEqual(len(parameters), 1)
            self.assertEqual(parameters[0].value, "23.0")

    def test_scenario_filter_uncommitted_data(self):
        self._build_data_with_single_scenario()
        apply_scenario_filter_to_parameter_value_sq(self._out_map, "scenario")
        parameters = self._out_map.query(self._out_map.parameter_value_sq).all()
        self.assertEqual(len(parameters), 1)
        self.assertEqual(parameters[0].value, "23.0")
        self._out_map.rollback_session()

    def test_alternative_filter(self):
        self._build_data_with_single_scenario()
        self._out_map.commit_session("Add test data")
        for db_map in [self._db_map, self._diff_db_map]:
            apply_alternative_filter_to_parameter_value_sq(db_map, ["alternative"])
            parameters = db_map.query(db_map.parameter_value_sq).all()
            self.assertEqual(len(parameters), 1)
            self.assertEqual(parameters[0].value, "23.0")

    def test_alternative_filter_uncommitted_data(self):
        self._build_data_with_single_scenario()
        apply_alternative_filter_to_parameter_value_sq(self._out_map, ["alternative"])
        parameters = self._out_map.query(self._out_map.parameter_value_sq).all()
        self.assertEqual(len(parameters), 1)
        self.assertEqual(parameters[0].value, "23.0")
        self._out_map.rollback_session()

    def _build_data_with_single_scenario(self):
        import_alternatives(self._out_map, ["alternative"])
        import_object_classes(self._out_map, ["object_class"])
        import_objects(self._out_map, [("object_class", "object")])
        import_object_parameters(self._out_map, [("object_class", "parameter")])
        import_object_parameter_values(self._out_map, [("object_class", "object", "parameter", -1.0)])
        import_object_parameter_values(self._out_map, [("object_class", "object", "parameter", 23.0, "alternative")])
        import_scenarios(self._out_map, [("scenario", True)])
        import_scenario_alternatives(self._out_map, [("scenario", "alternative")])

    def test_scenario_filter_works_for_object_parameter_value_sq(self):
        self._build_data_with_single_scenario()
        self._out_map.commit_session("Add test data")
        for db_map in [self._db_map, self._diff_db_map]:
            apply_scenario_filter_to_parameter_value_sq(db_map, "scenario")
            parameters = db_map.query(db_map.object_parameter_value_sq).all()
            self.assertEqual(len(parameters), 1)
            self.assertEqual(parameters[0].value, "23.0")

    def test_scenario_filter_works_for_relationship_parameter_value_sq(self):
        self._build_data_with_single_scenario()
        import_relationship_classes(self._out_map, [("relationship_class", ["object_class"])])
        import_relationship_parameters(self._out_map, [("relationship_class", "relationship_parameter")])
        import_relationships(self._out_map, [("relationship_class", ["object"])])
        import_relationship_parameter_values(
            self._out_map, [("relationship_class", ["object"], "relationship_parameter", -1)]
        )
        import_relationship_parameter_values(
            self._out_map, [("relationship_class", ["object"], "relationship_parameter", 23.0, "alternative")]
        )
        self._out_map.commit_session("Add test data")
        for db_map in [self._db_map, self._diff_db_map]:
            apply_scenario_filter_to_parameter_value_sq(db_map, "scenario")
            parameters = db_map.query(db_map.relationship_parameter_value_sq).all()
            self.assertEqual(len(parameters), 1)
            self.assertEqual(parameters[0].value, "23.0")

    def test_scenario_filter_selects_highest_ranked_alternative(self):
        import_alternatives(self._out_map, ["alternative3"])
        import_alternatives(self._out_map, ["alternative1"])
        import_alternatives(self._out_map, ["alternative2"])
        import_object_classes(self._out_map, ["object_class"])
        import_objects(self._out_map, [("object_class", "object")])
        import_object_parameters(self._out_map, [("object_class", "parameter")])
        import_object_parameter_values(self._out_map, [("object_class", "object", "parameter", -1.0)])
        import_object_parameter_values(self._out_map, [("object_class", "object", "parameter", 10.0, "alternative1")])
        import_object_parameter_values(self._out_map, [("object_class", "object", "parameter", 2000.0, "alternative2")])
        import_object_parameter_values(self._out_map, [("object_class", "object", "parameter", 300.0, "alternative3")])
        import_scenarios(self._out_map, [("scenario", True)])
        import_scenario_alternatives(
            self._out_map,
            [
                ("scenario", "alternative2"),
                ("scenario", "alternative3", "alternative2"),
                ("scenario", "alternative1", "alternative3"),
            ],
        )
        self._out_map.commit_session("Add test data")
        for db_map in [self._db_map, self._diff_db_map]:
            apply_scenario_filter_to_parameter_value_sq(db_map, "scenario")
            parameters = db_map.query(db_map.parameter_value_sq).all()
            self.assertEqual(len(parameters), 1)
            self.assertEqual(parameters[0].value, "2000.0")

    def test_scenario_filter_selects_highest_ranked_alternative_of_active_scenario(self):
        import_alternatives(self._out_map, ["alternative3"])
        import_alternatives(self._out_map, ["alternative1"])
        import_alternatives(self._out_map, ["alternative2"])
        import_alternatives(self._out_map, ["non_active_alternative"])
        import_object_classes(self._out_map, ["object_class"])
        import_objects(self._out_map, [("object_class", "object")])
        import_object_parameters(self._out_map, [("object_class", "parameter")])
        import_object_parameter_values(self._out_map, [("object_class", "object", "parameter", -1.0)])
        import_object_parameter_values(self._out_map, [("object_class", "object", "parameter", 10.0, "alternative1")])
        import_object_parameter_values(self._out_map, [("object_class", "object", "parameter", 2000.0, "alternative2")])
        import_object_parameter_values(self._out_map, [("object_class", "object", "parameter", 300.0, "alternative3")])
        import_scenarios(self._out_map, [("scenario", True)])
        import_scenarios(self._out_map, [("non_active_scenario", False)])
        import_scenario_alternatives(
            self._out_map,
            [
                ("scenario", "alternative2"),
                ("scenario", "alternative3", "alternative2"),
                ("scenario", "alternative1", "alternative3"),
            ],
        )
        import_scenario_alternatives(
            self._out_map,
            [
                ("non_active_scenario", "non_active_alternative"),
                ("scenario", "alternative2", "non_active_alternative"),
                ("scenario", "alternative3", "alternative2"),
                ("scenario", "alternative1", "alternative3"),
            ],
        )
        self._out_map.commit_session("Add test data")
        for db_map in [self._db_map, self._diff_db_map]:
            apply_scenario_filter_to_parameter_value_sq(db_map, "scenario")
            parameters = db_map.query(db_map.parameter_value_sq).all()
            self.assertEqual(len(parameters), 1)
            self.assertEqual(parameters[0].value, "2000.0")

    def test_scenario_filter_for_multiple_objects_and_parameters(self):
        import_alternatives(self._out_map, ["alternative"])
        import_object_classes(self._out_map, ["object_class"])
        import_objects(self._out_map, [("object_class", "object1")])
        import_objects(self._out_map, [("object_class", "object2")])
        import_object_parameters(self._out_map, [("object_class", "parameter1")])
        import_object_parameters(self._out_map, [("object_class", "parameter2")])
        import_object_parameter_values(self._out_map, [("object_class", "object1", "parameter1", -1.0)])
        import_object_parameter_values(self._out_map, [("object_class", "object1", "parameter1", 10.0, "alternative")])
        import_object_parameter_values(self._out_map, [("object_class", "object1", "parameter2", -1.0)])
        import_object_parameter_values(self._out_map, [("object_class", "object1", "parameter2", 11.0, "alternative")])
        import_object_parameter_values(self._out_map, [("object_class", "object2", "parameter1", -2.0)])
        import_object_parameter_values(self._out_map, [("object_class", "object2", "parameter1", 20.0, "alternative")])
        import_object_parameter_values(self._out_map, [("object_class", "object2", "parameter2", -2.0)])
        import_object_parameter_values(self._out_map, [("object_class", "object2", "parameter2", 22.0, "alternative")])
        import_scenarios(self._out_map, [("scenario", True)])
        import_scenario_alternatives(self._out_map, [("scenario", "alternative")])
        self._out_map.commit_session("Add test data")
        for db_map in [self._db_map, self._diff_db_map]:
            apply_scenario_filter_to_parameter_value_sq(db_map, "scenario")
            parameters = db_map.query(db_map.parameter_value_sq).all()
            self.assertEqual(len(parameters), 4)
            object_names = {o.id: o.name for o in db_map.query(db_map.object_sq).all()}
            alternative_names = {a.id: a.name for a in db_map.query(db_map.alternative_sq).all()}
            parameter_names = {d.id: d.name for d in db_map.query(db_map.parameter_definition_sq).all()}
            datamined_values = dict()
            for parameter in parameters:
                self.assertEqual(alternative_names[parameter.alternative_id], "alternative")
                parameter_values = datamined_values.setdefault(object_names[parameter.object_id], dict())
                parameter_values[parameter_names[parameter.parameter_definition_id]] = parameter.value
            self.assertEqual(
                datamined_values,
                {
                    "object1": {"parameter1": "10.0", "parameter2": "11.0"},
                    "object2": {"parameter1": "20.0", "parameter2": "22.0"},
                },
            )


if __name__ == '__main__':
    unittest.main()
