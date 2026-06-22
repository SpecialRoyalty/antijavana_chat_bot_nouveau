from __future__ import annotations
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

def now_tz(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))

def parse_slot(slot: str):
    a,b = slot.split("-")
    ah,am = map(int,a.split(":")); bh,bm = map(int,b.split(":"))
    return time(ah,am), time(bh,bm)

def next_open_close(slot: str, tz: str):
    n = now_tz(tz)
    start_t,end_t = parse_slot(slot)
    start = datetime.combine(n.date(), start_t, tzinfo=ZoneInfo(tz))
    end = datetime.combine(n.date(), end_t, tzinfo=ZoneInfo(tz))
    if end <= start:
        end += timedelta(days=1)
    if n > end:
        start += timedelta(days=1); end += timedelta(days=1)
    return start,end

def in_slot(slot: str, tz: str) -> bool:
    n = now_tz(tz)
    s,e = next_open_close(slot,tz)
    if n < s and (s-n) > timedelta(hours=20):
        s -= timedelta(days=1); e -= timedelta(days=1)
    return s <= n <= e

def day_key(tz: str) -> str:
    return now_tz(tz).strftime("%Y%m%d")

def human_delta(dt: datetime, tz: str) -> str:
    d = dt - now_tz(tz)
    secs = max(0, int(d.total_seconds()))
    h = secs // 3600; m = (secs % 3600)//60
    if h: return f"{h}h {m}min"
    return f"{m}min"
