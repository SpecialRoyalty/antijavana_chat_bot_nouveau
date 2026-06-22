# Telegram Railway Bot — V14 Countdown Status

V14 ajoute la logique complète du message d'état après objectif atteint.

## Nouveau comportement

- Objectif non atteint : message rouge avec votes manquants.
- Objectif atteint avant ouverture : message jaune `OBJECTIF ATTEINT` + compte à rebours jusqu'à l'ouverture.
- Objectif atteint pendant la plage : ouverture immédiate.
- Ouverture : message vert avec fermeture prévue.
- Santé du bot : dernière/prochaine mise à jour du message statut.

## Rythme affiché

Le scheduler tourne chaque minute, mais le texte affiché reste stable :

- au-dessus d'1h : affichage à l'heure / avec minutes selon état ;
- sous 1h : moins de 1h, puis 30 min, 10 min, 5 min, 2 min, 1 min ;
- vote = actualisation immédiate.



## V16
- Pass Soirée Gratuit : exclusions ajoutées. Impossible si Pass Total, VIP JAVANA ou Pass Soirée déjà acheté/réservé pour la session.
- Compte à rebours objectif atteint : actualisation forcée aux paliers horaires via marqueur discret `Actualisation : HH:00`, puis minute par minute dans la dernière heure.


## V17 scheduler fix
- Correction critique APScheduler: les jobs async sont maintenant planifiés directement avec args=[bot], plus via lambda.
- Le message statut est recalculé toutes les minutes et édité quand le texte change.
- Le compte à rebours objectif atteint affiche Dernière actualisation par palier horaire/dernière heure.
