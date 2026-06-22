# Telegram Railway Bot V18 — status recreate on countdown steps

Changement V18 :
- Le scheduler ne se contente plus d'éditer le message principal aux paliers.
- Quand le texte du statut change automatiquement, le bot supprime l'ancien message principal et en publie un nouveau.
- Résultat : l'heure Telegram visible du message se met bien à jour.
- Les votes continuent d'éditer instantanément le message existant pour éviter le spam entre deux paliers.

Déploiement :
1. Remplacer le code sur Railway.
2. Garder les mêmes variables d'environnement.
3. Redéployer.

Note : Telegram affiche toujours l'heure originale sur un message édité. Pour afficher une nouvelle heure, il faut publier un nouveau message, ce que fait désormais le scheduler aux paliers.
