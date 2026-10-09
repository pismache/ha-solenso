# Journal des versions

## 0.3.0 — 2026-10-09

- Carte « Panneau solaire » livrée avec l'intégration et chargée automatiquement : un panneau par micro-onduleur, éclairé selon sa production, avec la puissance et une plaque jour / mois / total.
- Disposition réelle des panneaux reprise de la page « Agencement » de Solenso (position exposée en attributs `layout_*`).
- Éditeur visuel de la carte (centrale, colonnes, puissance crête, affichage des watts).
- Rattachement des appareils compatible avec les prochaines versions de Home Assistant (`via_device` déprécié).

## 0.2.0 — 2026-10-09

- Un appareil par micro-onduleur : puissance, production du jour, tension et courant panneau, température, tension et fréquence réseau, dernière remontée.
- Appareil DTU avec un capteur « Connexion au cloud ».
- Onduleurs endormis : puissance, tension et courant à 0, production du jour conservée jusqu'à minuit.
- Une panne des données par onduleur ne bloque plus les capteurs de la centrale.
- Icône de l'intégration.

## 0.1.0 — 2026-10-09

- Première version : configuration par l'interface, détection automatique des centrales, puissance et productions jour / mois / année / totale, reconnexion automatique.
