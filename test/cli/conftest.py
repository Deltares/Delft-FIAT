from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

import fiat.cli.main as cli_main


@pytest.fixture
def run_patches(mocker: MockerFixture) -> Mock:
    """Patch the run command dependencies and expose the mocks."""
    # Mock the logger
    logger = mocker.Mock()
    setup_log = mocker.patch("fiat.cli.main.setup_default_log", return_value=logger)

    # Mock return the loglevel
    loglevel = mocker.patch("fiat.cli.main.check_loglevel", return_value=2)

    # Mock the models
    geom_model = mocker.Mock(name="GeomModel")
    grid_model = mocker.Mock(name="GridModel")
    mocker.patch.dict(
        cli_main._models,
        {cli_main.GEOM: geom_model, cli_main.GRID: grid_model},
    )

    # Return the mocked object
    return mocker.Mock(
        logger=logger,
        setup_log=setup_log,
        loglevel=loglevel,
        geom_model=geom_model,
        grid_model=grid_model,
    )
