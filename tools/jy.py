#!/usr/bin/env python3
"""Bot helper. Reads keys from ../.secrets (or tools/.secrets).
  python3 tools/jy.py export YYYY-MM-DD           -> calendar-day JSON + assumed ends for open feed/sleep
  python3 tools/jy.py export-week YYYY-MM-DD      -> week ending that Sunday [Mon 00:00, next Mon 00:00)
  python3 tools/jy.py summary YYYY-MM-DD FILE.md  -> upsert daily into SUMMARY_KEY.days
  python3 tools/jy.py summary-week YYYY-MM-DD FILE.md -> upsert weekly into SUMMARY_KEY.weeks (Sunday date)
  python3 tools/jy.py backup / restore
"""
import json,sys,os,time,urllib.request,urllib.parse,datetime as dt,subprocess,copy
UA={"User-Agent":"curl/8.5.0"}
_sec=os.path.join(os.path.dirname(__file__),'..','.secrets')
if not os.path.exists(_sec): _sec=os.path.join(os.path.dirname(__file__),'.secrets')
SEC=dict(l.strip().split('=',1) for l in open(_sec) if '=' in l and not l.startswith('#'))
def read(k):
    t=urllib.request.urlopen(urllib.request.Request(f"https://textdb.online/{k}?t={int(time.time()*1000)}",headers=UA),timeout=20).read().decode().strip()
    return json.loads(t) if t else {}
def write(k,obj):
    data=urllib.parse.urlencode({'key':k,'value':json.dumps(obj,ensure_ascii=False)}).encode()
    r=json.loads(urllib.request.urlopen(urllib.request.Request("https://api.textdb.online/update/",data,headers=UA),timeout=20).read())
    assert r.get('status')==1,r
def summary(date,text,keep=120):
    dt.date.fromisoformat(date)
    cur=read(SEC['SUMMARY_KEY']) or {}
    days=dict(cur.get('days') or {})
    if cur.get('text') and cur.get('date'): days.setdefault(cur['date'],{'text':cur['text'],'updated':cur.get('updated')})
    days[date]={'text':text,'updated':dt.datetime.now().isoformat(timespec='seconds')}
    days={d:days[d] for d in sorted(days)[-keep:]}
    write(SEC['SUMMARY_KEY'],{'v':2,'days':days,'weeks':cur.get('weeks') or {},'updated':dt.datetime.now().isoformat(timespec='seconds')})
def summary_week(sunday,text,keep=52):
    sun=dt.date.fromisoformat(sunday)
    if sun.weekday()!=6: raise SystemExit(f'summary-week date must be a Sunday, got {sunday} weekday={sun.weekday()}')
    cur=read(SEC['SUMMARY_KEY']) or {}
    weeks=dict(cur.get('weeks') or {})
    weeks[sunday]={'text':text,'updated':dt.datetime.now().isoformat(timespec='seconds')}
    weeks={d:weeks[d] for d in sorted(weeks)[-keep:]}
    days=dict(cur.get('days') or {})
    if cur.get('text') and cur.get('date'): days.setdefault(cur['date'],{'text':cur['text'],'updated':cur.get('updated')})
    write(SEC['SUMMARY_KEY'],{'v':2,'days':days,'weeks':weeks,'updated':dt.datetime.now().isoformat(timespec='seconds')})
def merged():
    m={}
    for k in ('DAD_KEY','MOM_KEY'):
        for r in (read(SEC[k]).get('records') or {}).values():
            if r['id'] not in m or r['updated_at']>m[r['id']]['updated_at']: m[r['id']]=r
    return sorted((r for r in m.values() if not r.get('deleted')),key=lambda r:r['ts'])
def _parse(s):
    if not s: return None
    return dt.datetime.fromisoformat(s[:16] if 'T' in s else s+'T00:00')
def _is_timed(r):
    """Sleep or breast feed — duration events that may cross midnight."""
    if r['type']=='sleep': return True
    return r['type']=='feed' and (r.get('data') or {}).get('kind')=='breast'
def _event_end(r, st, assume_end=None):
    """Actual or assumed end datetime. assume_end used only when still open (no end_ts / minutes)."""
    if r.get('end_ts'):
        return _parse(r['end_ts']), False
    if r['type']=='feed' and (r.get('data') or {}).get('minutes') is not None:
        return st+dt.timedelta(minutes=int(r['data']['minutes'])), False
    if assume_end is not None and st < assume_end:
        return assume_end, True
    return None, False
def _annotate(r, ws=None, we=None, day_end=None):
    """Add duration_min / running / end_assumed / clip_start / clip_end.
    When ws/we given (day window [ws, we)), clip duration to the intersection.
    Assumed end only for export; never written to textdb.
    day_end kept as alias for we (week export compat)."""
    if we is None and day_end is not None: we=day_end
    r=copy.deepcopy(r)
    if not _is_timed(r):
        return r
    st=_parse(r['ts'])
    if st is None:
        return r
    end, assumed=_event_end(r, st, assume_end=we)
    if end is None:
        r['running']=True
        return r
    if assumed:
        r['running']=True
        r['end_assumed']=end.isoformat(timespec='minutes')
        r['assumed_end']=True
    if ws is not None and we is not None:
        clip_start=max(st, ws)
        clip_end=min(end, we)
        if clip_start>=clip_end:
            r['duration_min']=0
            return r
        r['duration_min']=max(0,int((clip_end-clip_start).total_seconds()//60))
        r['clip_start']=clip_start.isoformat(timespec='minutes')
        r['clip_end']=clip_end.isoformat(timespec='minutes')
    else:
        r['duration_min']=max(0,int((end-st).total_seconds()//60))
    return r
def _overlaps(r, ws, we):
    """True if record belongs on day window: overlaps [ws, we).
    Timed (sleep/breast): started before we and ended after ws (open → assume end=we).
    Point events: ts in [ws, we)."""
    st=_parse(r['ts'])
    if st is None: return False
    if not _is_timed(r):
        return ws<=st<we
    end, _=_event_end(r, st, assume_end=we)
    if end is None:
        return st<we  # open with no assume window — include if started before we
    return st<we and end>ws
def _baby(day0):
    days=(day0-dt.date(2026,7,4)).days; pma=32*7+4+days
    return {"name":"宗嘉越","sex":"male","birth_date":"2026-07-04","ga_at_birth":"32+4","birth_weight_g":1800,
            "age_days":days,"pma":f"{pma//7}+{pma%7}","corrected_age_days":days-52}
def export(d):
    """Day D = [D 00:00, D+1 00:00) Asia/Shanghai.
    Include a record if it overlaps the window (sleep/breast: started before D+1 00:00 and
    ended after D 00:00, or still open and started before D+1 00:00; other types: ts in window).
    For sleep/breast, duration_min is clipped to the intersection; clip_start/clip_end set.
    Open feed/sleep: assumed end = D+1 00:00 for day D's portion only (assumed_end, not written to live data).
    Midnight-crossing sleep/feed is split: pre-midnight minutes on start day, post-midnight on next day.
    """
    R=merged()
    day0=dt.date.fromisoformat(d)
    ws=dt.datetime.combine(day0,dt.time(0,0))
    we=ws+dt.timedelta(days=1)
    recs=[]
    for r in R:
        if not _overlaps(r, ws, we): continue
        recs.append(_annotate(r, ws=ws, we=we))
    pick=lambda ts,n:[r for r in R if r['type'] in ts][-n:]
    return {"date":d,"timezone":"Asia/Shanghai",
            "window_start":ws.isoformat(timespec='minutes'),"window_end":we.isoformat(timespec='minutes'),
            "window_rule":"calendar day [D 00:00, D+1 00:00); include if overlaps window; sleep/breast duration clipped to intersection (clip_start/clip_end); open feed/sleep assumed end=window_end for this day only (assumed_end, not written to live data)",
            "baby":_baby(day0),
            "records":recs,"recent_growth":pick({'growth'},12),"recent_vaccine_checkup_milestone":pick({'vaccine','checkup','milestone'},20)}
def export_week(sunday):
    """Week ending Sunday = [Mon 00:00, next Mon 00:00) containing that Sunday."""
    sun=dt.date.fromisoformat(sunday)
    if sun.weekday()!=6: raise SystemExit(f'export-week date must be a Sunday, got {sunday}')
    mon=sun-dt.timedelta(days=6)
    next_mon=sun+dt.timedelta(days=1)
    ws=dt.datetime.combine(mon,dt.time(0,0))
    we=dt.datetime.combine(next_mon,dt.time(0,0))
    R=merged()
    # Per-day exports already clip at midnight; flatten for week-level lists
    day_exports={d:export(d) for d in [(mon+dt.timedelta(days=i)).isoformat() for i in range(7)]}
    all_recs=[]
    by_day={}
    for d,ex in day_exports.items():
        by_day[d]=ex['records']
        all_recs.extend(ex['records'])
    growth=[r for r in R if r['type']=='growth' and _parse(r['ts']) and ws<=_parse(r['ts'])<we]
    growth_before=[r for r in R if r['type']=='growth' and _parse(r['ts']) and _parse(r['ts'])<ws]
    first_g=growth[0] if growth else (growth_before[-1] if growth_before else None)
    last_g=growth[-1] if growth else first_g
    def gw(r,k):
        return (r.get('data') or {}).get(k) if r else None
    return {"week_ending":sunday,"week_start":mon.isoformat(),"timezone":"Asia/Shanghai",
            "window_start":ws.isoformat(timespec='minutes'),"window_end":we.isoformat(timespec='minutes'),
            "window_rule":"week ending Sunday = [Mon 00:00, next Mon 00:00); per-day midnight-clipped sleep/breast; open feed/sleep assumed end at each day end for that day's portion only",
            "baby":_baby(sun),
            "days":day_exports,
            "records":all_recs,
            "growth_change":{"first":first_g,"last":last_g,
                "weight_g":(None if gw(first_g,'weight') is None or gw(last_g,'weight') is None else gw(last_g,'weight')-gw(first_g,'weight')),
                "length_cm":(None if gw(first_g,'length') is None or gw(last_g,'length') is None else round(gw(last_g,'length')-gw(first_g,'length'),1)),
                "hc_cm":(None if gw(first_g,'hc') is None or gw(last_g,'hc') is None else round(gw(last_g,'hc')-gw(first_g,'hc'),1))},
            "recent_growth":[r for r in R if r['type']=='growth'][-12:]}

BK=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','data-backup')
NAMES={'DAD_KEY':'dad','MOM_KEY':'mom','SUMMARY_KEY':'summary'}
def _git(*a): return subprocess.run(['git','-C',BK,*a],capture_output=True,text=True)
def _ensure_repo():
    if not os.path.isdir(os.path.join(BK,'.git')):
        r=subprocess.run(['gh','repo','clone','zongxianghe-code/jiayue-data',BK],capture_output=True,text=True)
        if r.returncode: raise SystemExit('clone failed: '+r.stderr)
    _git('pull','-q','--rebase')
def _raw(k):
    return urllib.request.urlopen(urllib.request.Request(f"https://textdb.online/{k}?t={int(time.time()*1000)}",headers=UA),timeout=20).read().decode().strip()
def _empty(t):
    if not t: return True
    try: o=json.loads(t)
    except Exception: return False
    return not o or (isinstance(o,dict) and not o.get('records') and not o.get('text') and not o.get('days') and not o.get('weeks'))
def backup():
    _ensure_repo(); today=dt.date.today().isoformat(); saved=[]
    for k,n in NAMES.items():
        t=_raw(SEC[k])
        if _empty(t): print(n,'empty live doc, not saved'); continue
        d=os.path.join(BK,n); os.makedirs(d,exist_ok=True)
        for f in (f'{n}_{today}.json','latest.json'): open(os.path.join(d,f),'w',encoding='utf-8').write(t)
        saved.append(n)
    _git('add','-A')
    if not _git('status','--porcelain').stdout.strip(): print('unchanged, no commit'); return
    _git('-c','user.name=zongxianghe-code','-c','user.email=bot@users.noreply.github.com','commit','-qm',f'backup {dt.datetime.now():%Y-%m-%d %H:%M}')
    r=_git('push','-q'); print('pushed' if r.returncode==0 else 'push failed: '+r.stderr, saved)
def restore():
    _ensure_repo()
    for k,n in NAMES.items():
        live=_raw(SEC[k]); p=os.path.join(BK,n,'latest.json')
        if not _empty(live): print(n,'live has data, untouched'); continue
        if not os.path.exists(p) or _empty(open(p,encoding='utf-8').read()): print(n,'no backup data'); continue
        write(SEC[k],json.loads(open(p,encoding='utf-8').read())); print(n,'restored from backup')

if __name__=='__main__':
    c=sys.argv[1]
    if c=='export': print(json.dumps(export(sys.argv[2]),ensure_ascii=False,indent=1))
    elif c=='export-week': print(json.dumps(export_week(sys.argv[2]),ensure_ascii=False,indent=1))
    elif c=='summary': summary(sys.argv[2],open(sys.argv[3],encoding='utf-8').read()); print('ok')
    elif c=='summary-week': summary_week(sys.argv[2],open(sys.argv[3],encoding='utf-8').read()); print('ok')
    elif c=='backup': backup()
    elif c=='restore': restore()
    else: raise SystemExit('usage: export|export-week|summary|summary-week|backup|restore')
