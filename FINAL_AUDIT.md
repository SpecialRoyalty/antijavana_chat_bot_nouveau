# Audit final — Multi-groupes central

## Vérifications statiques effectuées

- Tous les fichiers Python de `app/` et `scripts/` passent `compileall`.
- Tous les imports internes `app.*` ont été vérifiés statiquement : aucun module/nom interne manquant.
- Les anciens modules morts `services/messages.py` et `services/session_manager.py`, qui dépendaient d'anciens modèles inexistants, ont été retirés.
- Les références opérationnelles directes à `MAIN_GROUP_ID` ont été éliminées : cet ID n'est plus qu'un bootstrap de compatibilité.
- Les VIP opérationnels sont résolus via `managed_chats` ; un ancien ID d'environnement remplacé dans le panel ne redevient pas actif au redémarrage.

## Cas fonctionnels couverts

- Nouveau chat : `PENDING` jusqu'à validation ADMIN_ID.
- Rôles uniques : Groupe A, Groupe B, Pass soirée, Pass total, VIP JAVANA, Logs.
- Sélecteur soirée : A / B / AUCUN.
- Un groupe `DEGRADED` reste utilisable pendant les essais ; `UNAVAILABLE` seulement après plusieurs échecs.
- Failover : session suspendue, liens d'invitation du groupe tombé libérés, score conservé.
- Remplacement d'un groupe validé : ancien groupe fermé et ses liens personnels révoqués.
- Modération / Hash-ban / `/pedo` / ban / mute globaux.
- Justice A+B sans créer de ban global permanent ; retraits ratés mis en attente.
- Anti-repost global ON/OFF : ID + SHA + fingerprint perceptuel vidéo, suppression sans ban.
- Invitations : un lien par propriétaire, un crédit par invité global, validation 5 min, score/rang DM, TOP 10 après justice, TOP 3 VIP manuel.
- Banni global : son lien d'invitation personnel est révoqué sans effacer son score historique.
- Crowdfunding / pubs / règles / broadcast groupe / pubs VIP / Pass gratuit : groupe actif.
- AUCUNE ouverture : aucune diffusion de session et aucun Pass soirée/gratuit libéré à 23h.
- Si une session ouvre après 23h, les Pass soirée/gratuits restés en attente sont libérés à l'ouverture réelle.
- VIP communs : même destination quel que soit A/B.
- Test infrastructure : accès + admin + permissions.
- Test réel VIP : envoi puis suppression d'un message dans chacun des VIP.

## Migration

`DATABASE_URL` peut rester l'une des anciennes DB. `scripts/merge_legacy_database.py` fusionne la seconde base sans suppression, avec priorité à la sécurité (`banned = A OR B`). Voir `MIGRATION.md`.

## Limite de l'audit local

L'environnement de génération n'a pas accès au réseau/PyPI/Telegram, donc aucun appel réel à l'API Telegram ou PostgreSQL Railway n'a été exécuté ici. Les tests réels prévus dans le panel (`🧪 Test infra`, `🧪 Test réel VIP`) servent précisément de validation après déploiement.
