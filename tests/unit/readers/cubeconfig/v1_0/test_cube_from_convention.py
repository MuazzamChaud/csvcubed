from pathlib import Path
import json
import os
import pandas as pd
from tempfile import TemporaryDirectory
from typing import List

import pytest

from csvcubed.models.cube.columns import SuppressedCsvColumn
from csvcubed.readers.cubeconfig.v1.configdeserialiser import get_deserialiser
from csvcubed.models.csvcubedexception import UnsupportedColumnDefinitionException


from csvcubed.models.cube.cube import Cube
from csvcubed.models.cube.qb.catalog import CatalogMetadata
from csvcubed.models.cube.qb.components.observedvalue import (
    QbMultiMeasureObservationValue,
)
from csvcubed.cli.build import build as cli_build
from csvcubed.definitions import APP_ROOT_DIR_PATH
from csvcubed.models.cube.qb import QbColumn
from csvcubed.models.cube.qb.components import (
    NewQbMeasure,
    NewQbUnit,
    NewQbDimension,
    NewQbCodeList,
    QbMultiMeasureDimension,
    QbMultiUnits,
    NewQbConcept,
)
from csvcubed.utils.iterables import first
from tests.unit.test_baseunit import get_test_cases_dir

TEST_CASE_DIR = get_test_cases_dir().absolute() / "readers" / "cube-config" / "v1.0"
SCHEMA_PATH_FILE = APP_ROOT_DIR_PATH / "schema" / "cube-config" / "v1_0" / "schema.json"


def test_01_build_convention_ok():
    """
    Valid Cube from Data using Convention (no config json)
    """
    test_data_path = Path(
        os.path.join(TEST_CASE_DIR, "cube_data_convention_ok.csv")
    ).resolve()

    print(f"test_case_data: {test_data_path}")
    with TemporaryDirectory() as temp_dir_path:
        temp_dir = Path(temp_dir_path)
        output = temp_dir / "out"
        csv = Path(TEST_CASE_DIR, "cube_data_convention_ok.csv")
        cube, validation_errors = cli_build(
            output_directory=output,
            csv_path=csv,
            fail_when_validation_error_occurs=False,
            validation_errors_file_name="validation_errors.json",
        )

    assert isinstance(cube, Cube)
    assert isinstance(validation_errors, List)
    assert isinstance(cube.columns, list)
    for column in cube.columns:
        assert isinstance(column, QbColumn)

    col_dim_0 = cube.columns[0]
    assert isinstance(col_dim_0.structural_definition, NewQbDimension)
    assert isinstance(col_dim_0.structural_definition.code_list, NewQbCodeList)
    assert isinstance(
        col_dim_0.structural_definition.code_list.metadata, CatalogMetadata
    )
    assert isinstance(col_dim_0.structural_definition.code_list.concepts, list)
    assert isinstance(
        col_dim_0.structural_definition.code_list.concepts[0], NewQbConcept
    )

    col_dim_1 = cube.columns[1]
    assert isinstance(col_dim_1.structural_definition, NewQbDimension)
    assert isinstance(
        col_dim_1.structural_definition.code_list.metadata, CatalogMetadata
    )
    assert isinstance(col_dim_1.structural_definition.code_list.concepts, list)
    assert isinstance(
        col_dim_1.structural_definition.code_list.concepts[0], NewQbConcept
    )

    col_observation = cube.columns[2]
    assert isinstance(
        col_observation.structural_definition, QbMultiMeasureObservationValue
    )
    assert col_observation.structural_definition.unit is None
    assert col_observation.structural_definition.data_type == "decimal"

    col_measure = cube.columns[3]
    assert isinstance(col_measure.structural_definition, QbMultiMeasureDimension)
    assert isinstance(col_measure.structural_definition.measures, list)
    assert isinstance(col_measure.structural_definition.measures[0], NewQbMeasure)

    col_unit = cube.columns[4]
    assert isinstance(col_unit.structural_definition, QbMultiUnits)
    assert isinstance(col_unit.structural_definition.units, list)
    assert isinstance(col_unit.structural_definition.units[0], NewQbUnit)

    col_attribute = cube.columns[5]
    assert isinstance(col_attribute.structural_definition, NewQbDimension)
    assert isinstance(col_attribute.structural_definition.code_list, NewQbCodeList)
    assert isinstance(col_attribute.structural_definition.code_list.concepts, list)
    assert isinstance(
        col_attribute.structural_definition.code_list.concepts[0], NewQbConcept
    )


def test_conventional_column_ordering_correct():
    """
    Ensure that the ordering of columns is as in the CSV.
    """

    with TemporaryDirectory() as t:
        temp_dir = Path(t)

        cube_config = {"columns": {"Amount": {"type": "observations"}}}
        # Defining the configured column in the middle of conventional columns to test ordering.
        data = pd.DataFrame(
            {
                "Dimension 1": ["A", "B", "C"],
                "Amount": [1.0, 2.0, 3.0],
                "Dimension 2": ["D", "E", "F"],
            }
        )

        data_file_path = temp_dir / "data.csv"
        config_file_path = temp_dir / "config.json"

        with open(config_file_path, "w+") as config_file:
            json.dump(cube_config, config_file, indent=4)

        data.to_csv(str(data_file_path), index=False)

        deserialiser = get_deserialiser(SCHEMA_PATH_FILE, 1)

        cube, _, _ = deserialiser(data_file_path, config_file_path)

        column_titles_in_order = [c.csv_column_title for c in cube.columns]
        assert column_titles_in_order == list(data.columns)


def test_colums_suppress():
    """
    The columns with false (i.e. "column_name": false) in the qube config json should be suppressed (i.e. skiped).
    """
    with TemporaryDirectory() as t:
        temp_dir = Path(t)

        cube_config = {"columns": {"Amount": {"type": "observations"}, "Rate": False}}
        data = pd.DataFrame(
            {
                "Dimension": ["A", "B", "C"],
                "Amount": [1.0, 2.0, 3.0],
                "Rate": [2.0, 3.0, 4.0],
            }
        )

        data_file_path = temp_dir / "data.csv"
        config_file_path = temp_dir / "config.json"

        with open(config_file_path, "w+") as config_file:
            json.dump(cube_config, config_file, indent=4)

        data.to_csv(str(data_file_path), index=False)

        deserialiser = get_deserialiser(SCHEMA_PATH_FILE, 3)

        cube, _, _ = deserialiser(data_file_path, config_file_path)
        columns: List[str] = [c.csv_column_title for c in cube.columns]

        assert "Amount" in columns
        assert "Rate" in columns

        rate_column = first(cube.columns, lambda c: c.csv_column_title == "Rate")
        assert isinstance(rate_column, SuppressedCsvColumn)


def test_unsupported_col_definition_exception():
    """
    When a column is definited using an unsupported type, the UnsupportedColumnDefinitionException should be raised.
    """
    with TemporaryDirectory() as t:
        temp_dir = Path(t)

        cube_config = {"columns": {"Amount": {"type": "observations"}, "Rate": 2}}
        data = pd.DataFrame(
            {
                "Dimension": ["A", "B", "C"],
                "Amount": [1.0, 2.0, 3.0],
                "Rate": [2.0, 3.0, 4.0],
            }
        )

        data_file_path = temp_dir / "data.csv"
        config_file_path = temp_dir / "config.json"

        with open(config_file_path, "w+") as config_file:
            json.dump(cube_config, config_file, indent=4)

        data.to_csv(str(data_file_path), index=False)

        deserialiser = get_deserialiser(SCHEMA_PATH_FILE, 3)

        with pytest.raises(UnsupportedColumnDefinitionException) as msg:
            _, _, _ = deserialiser(data_file_path, config_file_path)
            assert f"The definition for column with name Rate is not supported." in str(
                msg
            )


if __name__ == "__main__":
    pytest.main()
