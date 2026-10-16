# Journal des versions

## 0.6.0 — 2026-10-16

- **Rattrapage des mesures envoyées en différé.** Quand la passerelle DTU perd Internet, elle renvoie ses mesures plus tard ; le cloud ne les remontait pas en temps réel et la Production cumulée s'arrêtait au moment de la coupure. La journée de la veille est désormais relue toutes les heures d'après les mesures par onduleur, et l'énergie manquante est ajoutée au compteur, une seule fois. Les mesures par onduleur servent aussi de second avis sur la production du jour.
- **Plus de faux 0 W en plein jour.** Quand les remontées s'arrêtent alors que le soleil est haut (plus de 10°), la puissance de la centrale et les mesures instantanées des onduleurs (puissance, tension et courant panneau) passent indisponibles au lieu de 0. La nuit, elles restent à 0 comme avant. Les productions (jour, mois, année, total, cumulée) restent lisibles.

## 0.5.0 — 2026-10-11

- Nouveau capteur **Production cumulée** pour le tableau Énergie : il suit la production heure par heure, au lieu de la « Production totale » que le cloud ne recalcule qu'une fois par nuit (toute la production de la veille apparaissait d'un bloc vers 2 h). Compteur toujours croissant, sans à-coup à minuit, qui rattrape la production manquée pendant un redémarrage ou une coupure du cloud.
- README : le tableau Énergie doit désormais utiliser la Production cumulée.

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
