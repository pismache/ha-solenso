"""Réglages communs des tests."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def night():
    """Par défaut le soleil est couché : les tests ne dépendent pas de l'heure à laquelle ils tournent."""
    with patch("custom_components.solenso.coordinator.is_daylight", return_value=False) as mock:
        yield mock


@pytest.fixture
def daylight(night):
    """Soleil haut : une mesure figée doit être suspecte."""
    night.return_value = True
    return night
