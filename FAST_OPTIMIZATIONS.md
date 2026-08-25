# Optimisations de vitesse appliquées

Base utilisée : version avec Anti publication immédiate + Anti repost + Hash-ban perceptuel.

## Chemin chaud des messages

- Cache local 10 s pour les réglages `Setting` avec invalidation immédiate après `set_value`.
- `init_defaults()` : une lecture et un commit groupés au démarrage.
- `last_seen` / profil utilisateur : écriture au maximum toutes les 30 s si le profil n'a pas changé.
- Cache `a déjà envoyé un média` pour éviter une lecture `users` à chaque message texte.
- Cache des heures d'arrivée pour l'anti-publication immédiate.
- Règles `ban`, `forbidden` et `nameban` mises en cache 60 s et pré-tokenisées. Le cache est invalidé immédiatement lorsqu'un admin ajoute une règle.
- Tracking `TrackedMessage` via `INSERT ... ON CONFLICT DO NOTHING` au lieu de `SELECT` puis `INSERT`.
- Votes via `INSERT ... ON CONFLICT DO NOTHING`.

## Hash-ban / vidéos

- Blacklist ID/SHA mise en cache 30 s.
- Fingerprints vidéo bannis mis en cache 30 s.
- Pipeline média réorganisé :
  1. vérification `file_unique_id` sans téléchargement ;
  2. vérification anti-repost ID ;
  3. un seul téléchargement Telegram ;
  4. SHA256 ;
  5. arrêt immédiat si SHA banni / repost exact ;
  6. FFmpeg seulement si nécessaire ;
  7. réutilisation du même fichier temporaire pour l'enregistrement des hashes.
- Le calcul SHA256 et FFmpeg/PIL sont sortis de la boucle asyncio via `asyncio.to_thread`.
- FFmpeg reste volontairement limité à 1 analyse simultanée pour ne pas saturer Railway.

## Nettoyages / API Telegram

- Nettoyage de session en parallèle limité à 4 suppressions, sans garder de transaction PostgreSQL ouverte pendant les appels Telegram.
- Anti publication immédiate : même optimisation.
- `/pedo` : suppression des anciens messages hors transaction DB, puis mise à jour groupée.
- `/clean` : suppressions parallèles limitées.
- Un message déjà absent de Telegram est considéré comme nettoyé dans les nettoyages principaux.
- Notifications admins parallélisées.
- Broadcast privé : les mises à jour DB sont regroupées en une transaction à la fin au lieu d'un commit par destinataire.
- Santé : un seul `getMe()` pour vérifier tous les groupes.
- Message d'état inchangé : pas d'édition Telegram inutile à chaque minute ; vérification forcée toutes les 5 minutes.

## PostgreSQL

Index complémentaires créés automatiquement avec `IF NOT EXISTS` :

- fingerprint vidéo exact ;
- tracking `(chat_id, user_id, deleted)` ;
- tracking `(chat_id, session_id, deleted)`.

## Optimisations volontairement non appliquées

- `justice.py` n'a pas été supprimé : dans cette version il est réellement utilisé par le scheduler et le panneau admin.
- `pool_pre_ping=True` est conservé pour la stabilité Railway/PostgreSQL.
- La concurrence FFmpeg n'a pas été augmentée agressivement.
- Les caches de réglages ont un TTL au lieu d'être permanents afin de rester compatibles avec une éventuelle seconde instance du bot.

## Vérification

Tous les fichiers Python passent `compileall`.
Un benchmark réel de latence Telegram/PostgreSQL nécessite le déploiement Railway ; il n'est pas simulé dans cette archive.
