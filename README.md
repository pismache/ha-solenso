# Solenso pour Home Assistant

Intégration non officielle pour les centrales photovoltaïques **Solenso** suivies sur [monitor.solenso.net](https://monitor.solenso.net) (plateforme Hoymiles en marque blanche).

## Installation

**HACS** : HACS → menu ⋮ → Dépôts personnalisés → URL de ce dépôt, catégorie *Intégration* → installer « Solenso » → redémarrer.

**Manuelle** : copier le dossier `custom_components/solenso` dans `/config/custom_components/`, puis redémarrer Home Assistant.

## Configuration

Paramètres → Appareils et services → Ajouter une intégration → **Solenso**, puis saisir l'e-mail et le mot de passe du compte monitor.solenso.net.

Les centrales du compte sont détectées automatiquement. Si ce n'est pas le cas, renseigner l'**identifiant de la centrale** : c'est le nombre après `id=` dans l'adresse de sa page (`.../station/view/detail?id=1234567`).

## Capteurs

Pour chaque centrale :

| Capteur | Unité | Remarque |
|---|---|---|
| Puissance | W | forcée à 0 si aucune remontée depuis 1 h (la nuit) |
| Production du jour | kWh | |
| Production du mois | kWh | |
| Production de l'année | kWh | |
| Production totale | kWh | **à utiliser dans le tableau Énergie** |
| Dernière remontée | horodatage | diagnostic |

### Micro-onduleurs

Chaque micro-onduleur devient un appareil (rattaché à sa passerelle DTU, elle-même rattachée à la centrale), avec :

| Capteur | Unité | Remarque |
|---|---|---|
| Puissance | W | |
| Production du jour | kWh | |
| Tension panneau / Courant panneau | V / A | par entrée PV si l'onduleur en a plusieurs |
| Température | °C | |
| Tension réseau, Fréquence réseau | V, Hz | diagnostic |
| Dernière remontée | horodatage | diagnostic |

Les mesures arrivent par pas de 15 minutes. Sans nouveau point depuis 45 minutes (la nuit), puissance, tension et courant passent à 0 et la température devient inconnue ; la production du jour reste acquise jusqu'à minuit.

La passerelle DTU expose un capteur **Connexion au cloud**.

Mise à jour toutes les 5 minutes. Le cloud Solenso ne recalcule les cumuls mois/année/total qu'en différé ; la production du jour et la puissance sont plus réactives.

## Fonctionnement

L'intégration se connecte comme la page web (mot de passe envoyé haché, jamais en clair), garde le jeton de session et se reconnecte d'elle-même quand il expire. Si le mot de passe change, Home Assistant propose de le ressaisir.
