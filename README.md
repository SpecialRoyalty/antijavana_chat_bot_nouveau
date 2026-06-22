# Telegram Railway Bot V13

Correctif flux privés + logique countdown.

## Corrections V13

- Crowdfunding : le montant envoyé en privé déclenche maintenant toujours les moyens de paiement, même pour un utilisateur non-admin.
- Crowdfunding : la capture envoyée ensuite part aux admins pour validation.
- VIP : la capture envoyée après paiement part aux admins pour validation, même si l'utilisateur est un compte de test non-admin.
- Handler privé corrigé : le router admin ne bloque plus les parcours utilisateur.
- Message d'objectif atteint : quand le quota est atteint avant l'ouverture, le message doit afficher `Objectif atteint` + compte à rebours jusqu'à l'heure officielle.

## Proposition countdown validée

- Si objectif non atteint : message fermé classique + votes manquants.
- Dès que l'objectif est atteint : actualisation immédiate du message.
- Avant l'ouverture : compte à rebours dans le même message.
- Plus d'1h restante : affichage heure/minutes, tick scheduler chaque minute mais message édité seulement si contenu change.
- Moins d'1h : affichage précis.
- Derniers rappels : 10 min, 5 min, 2 min, 1 min.
- À l'heure d'ouverture : ouverture automatique si AUTO ON + objectif atteint.

## Notes Telegram

Le bot ne peut pas démarrer une conversation privée avec quelqu'un qui ne l'a jamais ouvert. Les boutons publics VIP/Crowdfunding utilisent donc un deep-link vers le bot si nécessaire.
