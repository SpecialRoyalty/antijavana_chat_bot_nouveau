# Correctifs VIP / multi-groupes

## Diagnostic confirmé

1. Les copies vers les VIP étaient suivies avec le même `session_id` que les messages du groupe principal. `cleanup_session()` supprimait ensuite tout ce `session_id`, sans limiter la requête aux groupes principaux. Résultat : les médias copiés dans les VIP disparaissaient à la fermeture.
2. La validation VIP affichait toujours « Action exécutée » même si la création ou l'envoi du lien échouait. Les accès passaient en `failed` sans retour admin utile.
3. Un VIP marqué temporairement `unavailable` pouvait empêcher `_group_for_offer()` de retrouver le groupe et donc empêcher les liens/copies.
4. Le handler du groupe inactif supprimait le message avant `moderate_message()`. Les règles globales (notamment anti-lien) n'étaient donc pas appliquées dans l'autre groupe.
5. L'anti-repost est bien global A+B dans le modèle actuel : `MediaHash` n'est pas scindé par chat et la recherche ne filtre pas sur le groupe. Le court-circuit du groupe inactif a été supprimé afin que le contrôle soit réellement exécuté dans A comme B.

## Correctifs

- Nettoyage de session limité strictement aux groupes principaux A/B. Les copies VIP ne sont plus supprimées à la fermeture.
- Repost médias vers les 3 VIP configurable par `Repost VIP ON/OFF`, activé par défaut.
- Copie VIP tentée sur les rôles VIP configurés même si un ancien health-check les a marqués `unavailable`; les erreurs réelles sont journalisées.
- Test réel des liens VIP : création puis révocation d'un lien à usage unique pour Pass soirée, Pass Total et VIP JAVANA.
- Test automatique quotidien à 12:10 (timezone du bot), avec rapport envoyé aux admins.
- Retry toutes les 10 minutes des liens Pass Total / JAVANA acceptés mais non livrés après une panne temporaire.
- Les accès restent `pending` en cas d'échec au lieu d'être définitivement perdus.
- Un accès ne passe `active` qu'après l'envoi privé réussi du lien.
- Le Pass soirée recalcule son expiration au moment réel d'envoi du lien afin de survivre à une soirée annulée/reportée.
- Le résultat réel de la validation VIP est affiché à l'admin.
- Modération sécurité exécutée sur les deux groupes : anti-lien, hash-ban, anti-repost, mots interdits, etc. Le groupe inactif est rejeté seulement après ces contrôles.
- Anti-repost : portée globale A+B confirmée. Un média accepté et enregistré dans A est reconnu dans A ou B ensuite.
- Broadcast Pass Total : utilisateurs avec `VipAccess(total, active)`.
- Broadcast Pass soirée : utilisateurs ayant un accès soirée `pending/active/expired`, en excluant ceux qui ont actuellement un Pass Total actif.

## Tests admin

Dans `💎 VIP` :
- `🔁 Repost médias VIP ON/OFF`
- `🔗 Tester les liens VIP`
- `🩺 Vérifier diffusion`

Dans `🧪 Test infra`, le test réel VIP vérifie maintenant :
- accès au chat
- droits admin
- envoi/suppression d'un message test
- création/révocation d'un lien d'invitation
