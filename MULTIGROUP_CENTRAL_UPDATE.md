# ANTIJAVANA — architecture multi-groupes centrale

## Principe

- 1 bot Telegram.
- 2 groupes principaux : Groupe A et Groupe B.
- 1 seul groupe sélectionné le soir : A, B ou AUCUN.
- Les VIP Pass soirée / Pass total / VIP JAVANA sont communs aux deux groupes.
- 1 base PostgreSQL centrale.

## Validation des chats

Quand le bot est ajouté dans un chat inconnu, il l'enregistre en `pending` et envoie aux `ADMIN_IDS` :

- Groupe A
- Groupe B
- Pass soirée
- Pass total
- VIP JAVANA
- Logs
- Refuser

Avant validation, aucune modération ni automatisation n'est exécutée dans ce chat. Les rôles sont liés au `chat_id`, pas au nom Telegram.

## Soirée A/B/AUCUN

Le panel `🌙 Groupe ce soir` impose un seul état :

- Groupe A : A est le groupe de session, B est fermé et redirige vers A.
- Groupe B : inverse.
- Aucune ouverture : A et B fermés, aucune automatisation de session.

Une bascule pendant une session conserve le même `active_session_id`.

## Modération et sanctions globales

Les règles, Name Ban, Mot ban/interdit, Hash-ban et fingerprints sont communs.

`/pedo` : blacklist globale + ban A + B + VIP communs. Un ban/mute Telegram manuel dans un chat validé est persisté puis propagé globalement. Les boucles de synchronisation sont protégées.

La justice est différente : elle fait un kick/nettoyage global A+B, sans créer un ban permanent.

## Anti-repost

`⚙️ Paramètres > ♻️ Anti repost` : ON/OFF global.

Quand ON, un média déjà publié dans A ou B est supprimé sans bannir l'utilisateur. Vérifications : `file_unique_id`, SHA256, puis fingerprint perceptuel vidéo lorsque nécessaire.

## Invitations

- Un seul lien actif par propriétaire.
- Le premier groupe depuis lequel la personne demande son lien fixe A ou B.
- Recliquage depuis l'autre groupe = même lien, pas un second lien.
- Une personne invitée ne peut donner qu'un seul point globalement.
- Validation après 5 minutes de présence.
- Notification privée à chaque point : score + classement en direct.
- TOP 10 envoyé une fois par session après la justice.
- TOP 3 = accès VIP, contact manuel par les admins.
- Si le groupe du lien devient réellement indisponible, le lien est révoqué/libéré et le score est conservé.

## Crowdfunding / pubs / règles / broadcast / Pass gratuit

Ils utilisent le groupe actif. Si aucun groupe n'est actif, ils ne publient rien. Les campagnes centrales ne sont pas supprimées par une panne de groupe.

`Broadcast groupe` cible le groupe actif. `Broadcast privé` reste commun à toutes les personnes ayant démarré le bot.

Les Pass soirée/gratuits ne sont pas libérés à 23h si aucune vraie session n'est ouverte.

## Santé et VIP

`🧪 Test infra` contrôle accès, statut admin et droits nécessaires. `🧪 Test réel VIP` envoie puis supprime un message dans chacun des trois VIP communs.

Un groupe actif n'est déclaré `unavailable` qu'après plusieurs échecs consécutifs. Un état `degraded` reste utilisable pour éviter qu'un 502 Telegram isolé provoque un faux failover.
