# Telegram Railway Bot V22 — Free Pass deep-link fix

Changements V22 :

- Le bouton public **🎟 Réserver gratuitement** ouvre maintenant directement le bot en privé via `t.me/BOT?start=freepass`.
- La réservation est finalisée en privé, ce qui garantit que le bot pourra envoyer le lien à 23h.
- Si toutes les places sont prises, le message groupe devient :

```text
🔥 PASS SOIRÉE OFFERT

Offre complète pour ce soir.

Rendez-vous à la prochaine session.
```

sans bouton.

- Les bénéficiaires du Pass Soirée gratuit suivent les mêmes règles que le Pass Soirée payant : lien à 23h ou immédiat entre 23h et 05h, puis retrait à 05h.
- `PUBLIC_BOT_USERNAME` doit être configuré pour que le bouton ouvre le bot directement.

Variables utiles :

```env
PUBLIC_BOT_USERNAME=TonBotSansArobase
PASS_SOIREE_GROUP_ID=-100...
```
