# Telegram Railway Bot V4

Version Python/Aiogram pour Railway + PostgreSQL.

## Déploiement Railway

1. Créer un bot via BotFather.
2. Créer PostgreSQL sur Railway.
3. Ajouter les variables d'environnement depuis `.env.example`.
4. `DATABASE_URL` peut rester celui de Railway (`postgresql://...`), le code le convertit en async automatiquement.
5. Ajouter le bot admin du groupe principal avec droits : supprimer, bannir, restreindre, gérer liens, modifier permissions.
6. Lancer le service Railway.

## Variables minimales

```env
BOT_TOKEN=...
DATABASE_URL=...
ADMIN_IDS=123456789
TRUSTED_IDS=
MAIN_GROUP_ID=-100...
TIMEZONE=Europe/Paris
```

Les groupes VIP peuvent être vides : fonctionnement partiel.

## État honnête V4

Cette version implémente le coeur opérationnel :
- message statut unique édité ;
- votes ;
- auto ON/OFF ;
- ouverture/fermeture ;
- nettoyage des messages suivis ;
- panel admin branché ;
- santé ;
- modération de base ;
- trusted commands ;
- VIP/paiement admin ;
- crowdfunding avec capture et validation ;
- rediffusion copyMessage vers Pass soirée/Pass total ;
- scheduler ;
- anti-raccordement pirate ;
- rapports ;
- tracking erreurs.

Limites Telegram importantes :
- un bot ne peut pas relire tout l'historique passé. Il nettoie les messages qu'il voit depuis son lancement.
- retirer tous les membres d'un groupe nécessite qu'ils soient connus par le bot via événements ou commandes ; Telegram ne fournit pas une liste complète via Bot API.
- pHash réel image/vidéo nécessite téléchargement et traitement média ; cette V4 utilise `file_unique_id` Telegram pour une détection exacte. Le moteur perceptuel doit être ajouté avec Pillow/OpenCV si nécessaire.


## V7 additions
- Publicités: liste en boutons, gestion par pub, activation/désactivation, suppression.
- Une pub = texte + image optionnelle. Si aucune image: texte seul.
- VIP: texte principal configurable + image principale configurable.
- VIP: textes détaillés des 3 offres configurables depuis le panel.
