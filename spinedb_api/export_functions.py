######################################################################################################################
# Copyright (C) 2017 - 2018 Spine project consortium
# This file is part of Spine Toolbox.
# Spine Toolbox is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option)
# any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
Functions for exporting data into a Spine database using entity names as references.

:author: M. Marin (KTH)
:date:   1.4.2020
"""

from .parameter_value import from_database


def export_data(
    db_map,
    object_classes=True,
    relationship_classes=True,
    parameter_value_lists=True,
    object_parameters=True,
    relationship_parameters=True,
    objects=True,
    relationships=True,
    object_parameter_values=True,
    relationship_parameter_values=True,
):
    data = dict()
    if object_classes:
        data["object_classes"] = export_object_classes(db_map)
    if relationship_classes:
        data["relationship_classes"] = export_relationship_classes(db_map)
    if parameter_value_lists:
        data["parameter_value_lists"] = export_parameter_value_lists(db_map)
    if object_parameters:
        data["object_parameters"] = export_object_parameters(db_map)
    if relationship_parameters:
        data["relationship_parameters"] = export_relationship_parameters(db_map)
    if objects:
        data["objects"] = export_objects(db_map)
    if relationships:
        data["relationships"] = export_relationships(db_map)
    if object_parameter_values:
        data["object_parameter_values"] = export_object_parameter_values(db_map)
    if relationship_parameter_values:
        data["relationship_parameter_values"] = export_relationship_parameter_values(db_map)
    return data


def export_object_classes(db_map):
    return sorted(x.name for x in db_map.query(db_map.object_class_sq))


def export_objects(db_map):
    return sorted((x.class_name, x.name) for x in db_map.query(db_map.ext_object_sq))


def export_relationship_classes(db_map):
    return sorted(
        (x.name, x.object_class_name_list.split(",")) for x in db_map.query(db_map.wide_relationship_class_sq)
    )


def export_parameter_value_lists(db_map):
    return sorted((x.name, x.value_list.split(",")) for x in db_map.query(db_map.wide_parameter_value_list_sq))


def export_object_parameters(db_map):
    return sorted(
        (x.object_class_name, x.parameter_name, from_database(x.default_value), x.value_list_name)
        for x in db_map.query(db_map.object_parameter_definition_sq)
    )


def export_relationship_parameters(db_map):
    return sorted(
        (x.relationship_class_name, x.parameter_name, from_database(x.default_value), x.value_list_name)
        for x in db_map.query(db_map.relationship_parameter_definition_sq)
    )


def export_relationships(db_map):
    return sorted((x.class_name, x.object_name_list.split(",")) for x in db_map.query(db_map.wide_relationship_sq))


def export_object_parameter_values(db_map):
    return sorted(
        (x.object_class_name, x.object_name, x.parameter_name, from_database(x.value))
        for x in db_map.query(db_map.object_parameter_value_sq)
    )


def export_relationship_parameter_values(db_map):
    return sorted(
        (x.relationship_class_name, x.object_name_list.split(","), x.parameter_name, from_database(x.value))
        for x in db_map.query(db_map.relationship_parameter_value_sq)
    )