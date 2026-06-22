from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

def now_tz(tz:str): return datetime.now(ZoneInfo(tz))
def day_key(tz:str): return now_tz(tz).strftime('%Y%m%d')
def parse_slot(slot:str):
    a,b=slot.split('-')
    sh,sm=map(int,a.split(':')); eh,em=map(int,b.split(':'))
    return (sh,sm),(eh,em)
def slot_times(slot:str,tz:str, ref:datetime|None=None):
    n=ref or now_tz(tz)
    (sh,sm),(eh,em)=parse_slot(slot)
    start=n.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end=n.replace(hour=eh, minute=em, second=0, microsecond=0)
    if end <= start: end += timedelta(days=1)
    if n > end: start += timedelta(days=1); end += timedelta(days=1)
    return start,end
def in_slot(slot:str,tz:str):
    n=now_tz(tz); start,end=slot_times(slot,tz,n)
    if n < start and (start-n)>timedelta(hours=12):
        start-=timedelta(days=1); end-=timedelta(days=1)
    return start <= n <= end
def next_open_text(slot:str,tz:str):
    start,end=slot_times(slot,tz)
    delta=start-now_tz(tz)
    if delta.total_seconds()<0: return 'maintenant'
    mins=int(delta.total_seconds()//60); h=mins//60; m=mins%60
    return f'{h}h {m}min' if h else f'{m}min'
def mid_time(slot:str,tz:str):
    s,e=slot_times(slot,tz); return s+(e-s)/2
