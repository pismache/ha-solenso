"""Constantes de l'intégration Solenso."""

from datetime import timedelta

DOMAIN = "solenso"
MANUFACTURER = "Solenso"

BASE_URL = "https://monitor.solenso.net/platform/api/gateway"

CONF_STATIONS = "stations"
CONF_SID = "sid"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

# Au-delà de ce délai sans nouvelle remontée, la puissance instantanée est
# considérée comme nulle (onduleurs éteints la nuit, DTU hors ligne...).
STALE_DATA_DELAY = timedelta(minutes=60)
