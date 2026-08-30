# Migration depuis les deux anciennes bases

## Recommandation

Ne repars pas d'une base vide. Choisis l'une des deux bases existantes (par exemple la DB du Groupe A) comme `DATABASE_URL` centrale. Le démarrage du nouveau code créera uniquement les nouvelles tables manquantes avec `CREATE TABLE IF NOT EXISTS` via SQLAlchemy.

Ensuite fusionne la seconde DB :

```bash
DATABASE_URL="postgresql://CENTRALE" \
BOT_TOKEN="..." \
ADMIN_IDS="123" \
LEGACY_DATABASE_URL_B="postgresql://ANCIENNE_B" \
python scripts/merge_legacy_database.py
```

Le script ne supprime rien et fusionne en priorité :

- `media_hashes` (`banned = A OR B`)
- `video_fingerprints` (`banned = A OR B`)
- `users`
- `word_rules`
- `private_subscribers`
- anciens drapeaux `is_banned` / `is_restricted` vers les sanctions globales

Les historiques de paiement/commandes/sessions de la seconde DB ne sont volontairement pas recopiés automatiquement pour éviter des collisions d'IDs. Garde la DB B en lecture seule comme archive.

Avant la migration : fais un backup Railway des deux bases.
