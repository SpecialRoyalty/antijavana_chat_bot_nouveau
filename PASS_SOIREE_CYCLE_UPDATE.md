# Pass soirée payant — cycle V3.2

## Règle commerciale

L'heure de référence est l'heure à laquelle la preuve de paiement est reçue par le bot (`proof_received_at`).

- preuve reçue entre **06:00 et 23:59** : le lien est envoyé dès validation admin ; expiration au prochain **06:00** ;
- preuve reçue entre **00:00 et 05:59** : le lien est libéré à **12:00** le même jour si le paiement est déjà validé ; expiration à **06:00 le lendemain** ;
- si l'admin valide après l'heure de libération, le lien part immédiatement ;
- si la validation arrive tellement tard que l'échéance prévue est déjà passée, l'achat n'est jamais perdu : le lien part immédiatement et l'expiration est repoussée au prochain 06:00.

Le Pass soirée payant ne dépend plus de l'ouverture du groupe principal.

## Expiration réellement vérifiée

Le scheduler contrôle les accès échus toutes les 5 minutes.

Un accès ne passe à `expired` que lorsque :

1. son lien d'invitation est révoqué ou déjà inutilisable ;
2. Telegram confirme que l'utilisateur n'est plus membre du groupe Pass soirée.

Si le membre est encore présent, le bot effectue `ban` puis `unban`, puis vérifie son statut. En cas d'erreur Telegram ou de droit manquant, l'accès reste `active` et sera retenté au passage suivant.

Le rapport admin distingue : membres réellement retirés, déjà absents et échecs à retenter.

## Relance Pass Total

Après expiration confirmée, l'utilisateur reçoit en privé une proposition Pass Total avec le prix actuellement configuré dans le panel. S'il possède déjà un Pass Total actif, il reçoit seulement la confirmation de fin du Pass soirée.

## Test quotidien VIP

Le test quotidien est lancé à **11:50**. Pour Pass soirée il vérifie :

- bot administrateur ;
- droit de créer des invitations ;
- droit de bannir/retirer des membres ;
- création puis révocation d'un lien à usage unique.

## Base existante

La colonne `vip_orders.proof_received_at` est ajoutée automatiquement au démarrage sur PostgreSQL via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Les anciennes commandes sans cette valeur utilisent `created_at` comme repli.
