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

# En plein jour, une puissance qui ne remonte plus n'est pas une puissance nulle :
# les capteurs « instantanés » passent alors indisponibles au lieu d'afficher 0.
# Au-dessous de cette hauteur du soleil (degrés), un panneau qui ne produit pas est normal.
DAYLIGHT_ELEVATION = 10.0

# La DTU peut renvoyer ses mesures en différé (coupure Internet chez soi) : la
# journée de la veille est relue à cet intervalle pour rattraper l'énergie manquée.
PREVIOUS_DAY_REFRESH_INTERVAL = timedelta(hours=1)

# En dessous de cet écart (Wh), une différence entre sources est un arrondi, pas un rattrapage.
CATCH_UP_MIN_WH = 10.0
