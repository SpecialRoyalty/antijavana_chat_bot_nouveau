# Telegram Railway Bot Python V11

Version V11 avec corrections VIP / crowdfunding / pubs / justice.

## VIP V11

### Pass soirée
- Paiement validé avant 23h : le lien unique est mis en attente et envoyé automatiquement à 23h.
- Paiement validé entre 23h et 05h : le lien unique est envoyé immédiatement.
- Paiement validé après 05h : le paiement est affecté à la prochaine session, lien envoyé à 23h.
- Lien unique Telegram utilisable une seule fois.
- À 05h : l’utilisateur est retiré du groupe Pass soirée, le lien est révoqué, les médias du groupe ne sont pas supprimés.
- Relance PV après expiration.

### Pass total
- Lien unique utilisable une seule fois.
- Accès permanent.
- Pas d’expiration.

### VIP JAVANA
- Lien unique utilisable une seule fois.
- Accès permanent.
- Groupe alimenté à part.

## Crowdfunding
- Montant en PV → choix paiement → capture → validation admin.
- Validation admin met à jour le montant, la barre, et le dernier message groupe.
- Maximum 2 campagnes configurables.

## Variables paiement Railway

```env
PAYPAL_TEXT=
REVOLUT_TEXT=
CRYPTO_TEXT=
```

## Note Telegram
Le bot ne peut supprimer que les messages qu’il a vus depuis son démarrage. Pour créer les liens VIP, le bot doit être admin dans les groupes VIP avec permission d’invitation.
