import re

GIBBERISH_RE = re.compile(r'^[a-z]{3,6}\s+[a-z]{3,6}$', re.I)
REPEATED_RE = re.compile(r'(.)\1{2,}', re.I)


def name_suspicion_score(full_name: str, has_username: bool, has_photo: bool = True) -> int:
    score = 0
    name = (full_name or '').strip()
    if not has_username:
        score += 10
    if not has_photo:
        score += 10
    if REPEATED_RE.search(name):
        score += 15
    if GIBBERISH_RE.match(name) and not looks_like_real_name(name):
        score += 20
    if len(name.replace(' ', '')) <= 4:
        score += 10
    return score


def looks_like_real_name(name: str) -> bool:
    common = {'anna','maria','john','alex','sara','natalia','paul','marie','lucas','emma'}
    parts = {p.casefold() for p in name.split()}
    return bool(parts & common)
