import re

def display_user(u) -> str:
    if getattr(u, 'username', None):
        return '@' + u.username
    name = ' '.join(x for x in [getattr(u,'first_name',None), getattr(u,'last_name',None)] if x).strip()
    return name or 'Utilisateur'

def anonymize(username_or_name: str) -> str:
    s = username_or_name or 'unknown'
    if s.startswith('@'): s=s[1:]
    if len(s)<=2: return '@' + s[0] + '*'
    return '@' + s[:2] + '*'*(max(3,len(s)-2))

def looks_random_name(name: str) -> bool:
    n = re.sub(r'[^a-zA-Z]', '', name or '').lower()
    if len(n) < 5: return False
    if re.search(r'(.)\1\1', n): return True
    vowels = sum(c in 'aeiouy' for c in n)
    ratio = vowels / max(1,len(n))
    if ratio < .18 or ratio > .75: return True
    if re.search(r'(qwer|asdf|hjkl|zxcv|fghj|jkjk|hghg|jdjd|kdjd)', n): return True
    return False
