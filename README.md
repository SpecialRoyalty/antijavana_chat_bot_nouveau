# Bot Telegram Railway Python V5 — Corrections cahier des charges

Corrections principales :

- Panel admin en boutons pour objectif, horaires, modération, crowdfunding, publicités, nettoyage, grâce.
- Message principal unique édité au lieu d’être recréé.
- Vote : actualisation immédiate ; si objectif atteint, le message affiche Objectif atteint et ouvre si on est dans le créneau.
- Compte à rebours actualisé par le scheduler dans le même message.
- Nettoyage : session active ou tous les messages suivis, rapport des échecs, alerte si médias non supprimés.
- Crowdfunding : texte + image + bouton Je participe + PV + montant + capture + validation admin + barre de progression.
- Publicités : plusieurs pubs texte/image, liste, envoi aléatoire quand groupe ouvert.
- Grâce présidentielle/ministérielle : compte les personnes concernées et demande confirmation.
- Ouverture manuelle en Auto OFF : sécurité 2h + demande admin + fermeture si pas de réponse.
- VIP : message groupe avec 3 boutons, clic en PV, paiement/capture/validation.

Important : Telegram ne permet au bot de supprimer que les messages qu’il a vus depuis qu’il tourne et uniquement si le bot est admin avec le droit Supprimer les messages.

## Variables Railway

BOT_TOKEN=
DATABASE_URL=
ADMIN_IDS=5296696302
TRUSTED_IDS=296696302
MAIN_GROUP_ID=-100...
PASS_SOIREE_GROUP_ID=
PASS_TOTAL_GROUP_ID=
VIP_JAVANA_GROUP_ID=
LOG_GROUP_ID=
PUBLIC_BOT_USERNAME=
DEFAULT_VOTE_GOAL=120
DEFAULT_TIME_SLOT=22:30-00:45
AUTO_SCHEDULE_ENABLED=true
TIMEZONE=Europe/Paris
PAYPAL_TEXT=
REVOLUT_TEXT=
CRYPTO_TEXT=
