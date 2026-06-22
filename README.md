# Telegram Railway Bot V2 — Core fonctionnel

Stack : Python 3.12, Aiogram 3, PostgreSQL, SQLAlchemy async, APScheduler.

## Important
Ce ZIP contient une base fonctionnelle robuste pour le cœur : message unique, vote, ouverture/fermeture, panel admin, nettoyage, modération principale, santé bot, mode partiel VIP. Les modules lourds du cahier des charges sont structurés et prêts à compléter.

## Déploiement Railway
1. Créer un bot via BotFather.
2. Créer un projet Railway avec PostgreSQL.
3. Ajouter les variables `.env.example`.
4. Déployer ce repo.
5. Ajouter le bot admin du groupe principal.
6. Mettre `MAIN_GROUP_ID=-100...`.

## Variables minimales
```env
BOT_TOKEN=xxx
DATABASE_URL=postgresql+asyncpg://...
ADMIN_IDS=123456789
TRUSTED_IDS=123456789,987654321
MAIN_GROUP_ID=-1001234567890
```

Les groupes VIP peuvent rester vides. Le bot passe en fonctionnement partiel.

## Comportement corrigé
- Un seul message statut : édition prioritaire, recréation uniquement si disparu.
- Les groupes optionnels vides ne font pas planter le démarrage.
- Bouton vote : ajoute le vote, édite le même message.
- Groupe fermé : supprime les messages random.
- Panel admin en privé : `/start`.
- Santé bot : vérifie DB, Telegram, groupes configurés, prochain horaire.

## Notes
Telegram ne permet pas de relire toute l'historique d'un groupe comme une base de données. Le bot ne peut supprimer de façon fiable que les messages qu'il a vus et stockés depuis son lancement.
