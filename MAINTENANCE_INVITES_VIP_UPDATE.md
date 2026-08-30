# Maintenance / invitations / publications multi-groupes

## Message groupe fermé

Quand `Aucune ouverture` est sélectionné, ou quand l'automatisation est OFF et qu'aucune session manuelle n'est ouverte, les deux groupes principaux restent fermés et affichent :

```
🔴 GROUPE FERMÉ

Aucune ouverture n’est prévue ce soir.

Merci de revenir demain.
```

Le message contient `🎁 Partager le groupe`.

Le bouton ouvre le bot en privé avec le contexte du groupe cliqué. Le membre reçoit son lien personnel unique. Un utilisateur ne conserve qu'un seul lien actif à la fois ; son score est global A+B et est conservé si le groupe associé devient indisponible.

## Classement invitations

- Validation d'une invitation après 5 minutes.
- Notification privée à chaque invitation validée avec score et rang actualisés.
- TOP 3 = accès VIP, remise/contact manuel admin.
- TOP 10 publié deux fois par session :
  1. après la justice populaire ;
  2. vers 75 % de la fenêtre d'ouverture.
- Les marqueurs sont liés au `active_session_id`, donc un redémarrage/failover ne republie pas le même TOP inutilement.

## Publications quand les groupes sont fermés

Les permissions fermées concernent les membres, pas le bot. Les publications manuelles suivantes proposent désormais :

- Groupe A
- Groupe B
- Les 2 groupes

Fonctions concernées :

- VIP
- Crowdfunding
- Publicités
- Règles
- Invitations

Cela fonctionne même si le groupe est fermé. Les envois automatiques restent liés à la session ouverte afin de ne pas spammer les deux groupes sans choix explicite.
