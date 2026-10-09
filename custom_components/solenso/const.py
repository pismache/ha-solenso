"""Constantes de l'intégration Solenso."""

from datetime import timedelta

DOMAIN = "solenso"
MANUFACTURER = "Solenso"

BASE_URL = "https://monitor.solenso.net/platform/api/gateway"
HOYMILES_URL = "https://neapi.hoymiles.com"

CONF_STATIONS = "stations"
CONF_SID = "sid"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

# Liste des appareils (micro-onduleurs, DTU) : elle change rarement.
DEVICES_REFRESH_INTERVAL = timedelta(hours=6)

# Au-delà de ce délai sans nouvelle remontée, la puissance instantanée est
# considérée comme nulle (onduleurs éteints la nuit, DTU hors ligne...).
STALE_DATA_DELAY = timedelta(minutes=60)

# Les mesures par onduleur arrivent par pas de 15 minutes : au-delà de 45 minutes
# sans nouveau point, l'onduleur est considéré comme endormi.
MICRO_STALE_DELAY = timedelta(minutes=45)
