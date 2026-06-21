# Telegram Railway Bot — Python V1

Stack: Python 3.12, Aiogram 3, PostgreSQL, SQLAlchemy async, APScheduler, Railway.

## Déploiement Railway
1. Créer un bot via BotFather et récupérer `BOT_TOKEN`.
2. Créer un projet Railway avec PostgreSQL.
3. Ajouter les variables de `.env.example`.
4. Déployer ce repo GitHub sur Railway.
5. Ajouter le bot admin dans les groupes Telegram requis.

## Démarrage local
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

## État
Base V1 structurée : admin panel, horaires, votes, modération, trusted commands, santé, sessions, VIP, invitations, suspects, hash média. Les fonctions critiques sont isolées dans `app/services/` pour continuer proprement.
