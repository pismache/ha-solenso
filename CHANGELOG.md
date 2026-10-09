# Journal des versions

## 0.4.2 — 2026-10-09

- La carte est ajoutée automatiquement aux **ressources** des tableaux de bord (comme le fait HACS) : elle reste disponible après un rechargement de page. Une ressource ajoutée à la main est reprise, sans doublon. Les tableaux de bord en YAML gardent l'ancien mode de chargement.
- La ressource est retirée quand l'intégration est supprimée.

## 0.4.1 — 2026-10-09

- La carte est déclarée dès le démarrage de Home Assistant, même si le cloud Solenso ne répond pas encore : plus d'« Erreur de configuration » à la place de la carte après un redémarrage.

## 0.4.0 — 2026-10-09

- La carte place les panneaux comme sur le toit, d'après la page « Agencement » de Solenso ; un bloc par toiture. Position exposée en attributs `layout_row`, `layout_column` et `layout_array` sur la puissance de chaque micro-onduleur.
- La carte est rechargée par le navigateur dès qu'elle change (empreinte du fichier dans son adresse).

## 0.3.0 — 2026-10-09

- Carte « Panneau solaire » livrée avec l'intégration et chargée automatiquement : un panneau par micro-onduleur, éclairé selon sa production, avec la puissance et une plaque jour / mois / total.
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
