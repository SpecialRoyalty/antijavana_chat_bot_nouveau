def closed_text(votes: int, target: int, opening: str = '22h30') -> str:
    missing = max(target - votes, 0)
    return f"🔴 GROUPE FERMÉ\n\nOuverture prévue à {opening}.\n\nObjectif :\n{votes} / {target} votes\n\nIl manque encore {missing} votes."


def maintenance_text() -> str:
    return "🔴 MAINTENANCE\n\nLe système est en maintenance ce soir.\n\nAucune ouverture prévue."


def open_text() -> str:
    return "🟢 GROUPE OUVERT\n\nVous pouvez envoyer vos médias <3"


def justice_text() -> str:
    return "⚖️ JUSTICE POPULAIRE\n\nLe groupe est bloqué pendant 5 minutes.\n\nDes membres profitent du groupe sans participer."


def vip_ad_text() -> str:
    return "💎 ACCÈS VIP\n\nChoisissez une offre pour obtenir plus d'informations."
