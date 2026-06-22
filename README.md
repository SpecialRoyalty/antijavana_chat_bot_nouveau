# Telegram Railway Bot V8 — corrections test

Corrections principales:
- Justice populaire: exclut bot/admin/trusted, max 1 fois par session, preview + validation, plus de timeout callback.
- Hash ban: ajout anticipé en privé, détection par `file_unique_id` + SHA256 téléchargé pour tests plus fiables.
- VIP: boutons du groupe en deep-link vers le bot privé; menu privé avec panier, changement d'offres, checkout, prix configurables.
- Crowdfunding: gestion jusqu'à 2 campagnes, campagne active, texte/image/objectif, publication maintenant, barre de progression.
- Name ban: contrôle au join.
- Logs d'erreur conservés en base.

Variables importantes:
- PUBLIC_BOT_USERNAME doit être rempli sans @ pour que les boutons VIP/Crowdfunding ouvrent directement le bot en privé.
- Le bot doit être admin du groupe principal et des groupes VIP avec droits suppression/ban/restriction/invitations.

Note Telegram:
- Un bot ne peut pas forcer une discussion privée silencieusement si l'utilisateur ne l'a jamais démarré. Le deep-link ouvre directement le bot avec l'offre sélectionnée.
