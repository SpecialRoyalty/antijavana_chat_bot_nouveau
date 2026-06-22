from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.config import get_settings

settings = get_settings()


def closed_text(votes: int, target: int, opening: str = '22h30') -> str:
    missing = max(target - votes, 0)
    return (
        '🔴 GROUPE FERMÉ\n\n'
        f'Ouverture prévue à {opening}.\n\n'
        'Objectif :\n'
        f'{votes} / {target} votes\n\n'
        f'Il manque encore {missing} votes.'
    )


def open_text() -> str:
    return '🟢 GROUPE OUVERT\n\nVous pouvez envoyer vos médias <3'


def maintenance_text() -> str:
    return '🔴 MAINTENANCE\n\nLe système est en maintenance ce soir.\n\nAucune ouverture prévue.'


def justice_text() -> str:
    return '⚖️ JUSTICE POPULAIRE\n\nLe groupe est bloqué pendant 5 minutes.\n\nDes membres profitent du groupe sans participer.'
