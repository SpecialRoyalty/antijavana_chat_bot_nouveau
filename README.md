# ANTIJAVANA CHAT — Multi-groupes central

Bot Aiogram/PostgreSQL pour piloter deux groupes principaux avec les mêmes VIP et une modération globale.

## Architecture

- **1 bot**
- **Groupe A + Groupe B**
- **un seul groupe actif par soirée**, ou `AUCUN`
- **VIP communs** : Pass soirée, Pass total, VIP JAVANA
- **1 DB centrale** conservant les Hash-ban/fingerprints existants

## Mise en route

1. Déploie le code avec `BOT_TOKEN`, `DATABASE_URL`, `ADMIN_IDS`.
2. Tu peux fournir les IDs existants dans `MAIN_GROUP_A_ID`, `MAIN_GROUP_B_ID` et les trois IDs VIP pour bootstrap.
3. Sinon ajoute le bot admin dans chaque chat : les `ADMIN_IDS` recevront une demande de validation.
4. Dans le panel : `🧩 Groupes / VIP` puis `🧪 Test infra`.
5. Lance `🧪 Test réel VIP` pour vérifier envoi + suppression dans les trois VIP.
6. Choisis `🌙 Groupe ce soir` : A, B ou aucune ouverture.

## Fonctions centrales

- Hash-ban global : ID Telegram + SHA256 + fingerprint perceptuel vidéo.
- `/pedo` global A+B+VIP.
- bans/mutes manuels synchronisés et persistants.
- justice globale A+B mais sans ban permanent.
- Anti-repost global ON/OFF.
- crowdfunding, pubs, règles et broadcast dirigés vers le groupe actif.
- Pass gratuit / Pass soirée communs aux mêmes VIP.
- invitations globales : lien unique, score live, TOP 10 après justice, TOP 3 VIP avec contact manuel.
- santé multi-chat et failover avec protection contre les pannes Telegram transitoires.

## Aucune ouverture

Si `🌑 Aucune ouverture` est sélectionné, les deux groupes restent fermés. Le scheduler continue pour la maintenance/sécurité mais aucune diffusion de session n'est lancée et les Pass soirée/gratuits ne sont pas libérés à 23h.

## Migration

Voir `MIGRATION.md` et `scripts/merge_legacy_database.py` pour fusionner la seconde ancienne DB sans perdre les Hash-ban/fingerprints.

## Railway

Commande :

```text
python -m app.main
```

Les nouvelles tables sont créées automatiquement au démarrage. Fais néanmoins un backup DB avant le premier déploiement multi-groupes.
