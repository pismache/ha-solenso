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
# journée de la veille est relue à cet intervalle et réécrite dans les statistiques.
PREVIOUS_DAY_REFRESH_INTERVAL = timedelta(hours=1)

# Statistiques de production : après un long arrêt de Home Assistant, au plus ce
# nombre de journées est relu pour combler le trou.
CATCH_UP_MAX_DAYS = 31

# Reprise de l'historique au premier lancement : au plus un an, arrêt après une
# semaine sans aucune mesure, une requête par seconde pour ménager le cloud.
BACKFILL_MAX_DAYS = 365
BACKFILL_EMPTY_DAYS = 7
BACKFILL_REQUEST_DELAY = 1.0
