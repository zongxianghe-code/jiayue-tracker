#!/usr/bin/env python3
"""Bot helper. Reads keys from ../.secrets.
  python3 tools/jy.py export YYYY-MM-DD      -> JSON: baby ages + that day's merged records (7am–7am window) + recent growth/vaccine/checkup/milestones
  python3 tools/jy.py summary YYYY-MM-DD FILE.md  -> upserts daily summary into SUMMARY_KEY history
  python3 tools/jy.py backup / restore       -> private repo zongxianghe-code/jiayue-data
"""
import json,sys,os,time,urllib.request,urllib.parse,datetime as dt,subprocess
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
    write(SEC['SUMMARY_KEY'],{'v':2,'days':days,'updated':dt.datetime.now().isoformat(timespec='seconds')})
def merged():
    m={}
    for k in ('DAD_KEY','MOM_KEY'):
        for r in (read(SEC[k]).get('records') or {}).values():
            if r['id'] not in m or r['updated_at']>m[r['id']]['updated_at']: m[r['id']]=r
    return sorted((r for r in m.values() if not r.get('deleted')),key=lambda r:r['ts'])
def _parse(s):
    if not s: return None
    return dt.datetime.fromisoformat(s[:16] if 'T' in s else s+'T00:00')
def export(d):
    """Day D = [D 07:00, D+1 07:00) Asia/Shanghai (naive local times as stored).
    Rule: a record belongs to the day where its start (ts) falls.
    Sleep/feed spanning 07:00 stays on the day it started (no duration clip).
    Running sleep/feed included iff start is in the window.
    Morning job ~07:45 publishes yesterday's window (yesterday 07:00 → today 07:00).
    Example: feed at 06:30 on calendar D+1 belongs to day D.
    """
    R=merged()
    day0=dt.date.fromisoformat(d)
    ws=dt.datetime.combine(day0,dt.time(7,0))
    we=ws+dt.timedelta(days=1)
    for r in R:
        if r['type']=='feed' and r.get('data',{}).get('kind')=='breast':
            dd=r['data']
            if r.get('end_ts'): r['duration_min']=int((_parse(r['end_ts'])-_parse(r['ts'])).total_seconds()//60)
            elif dd.get('minutes'): r['duration_min']=dd['minutes']
            elif not dd.get('side'): r['running']=True
        if r['type']=='sleep':
            if r.get('end_ts'): r['duration_min']=int((_parse(r['end_ts'])-_parse(r['ts'])).total_seconds()//60)
            else: r['running']=True
    recs=[r for r in R if (st:=_parse(r['ts'])) is not None and ws<=st<we]
    days=(day0-dt.date(2026,7,4)).days; pma=32*7+4+days
    pick=lambda ts,n:[r for r in R if r['type'] in ts][-n:]
    return {"date":d,"timezone":"Asia/Shanghai",
            "window_start":ws.isoformat(timespec='minutes'),"window_end":we.isoformat(timespec='minutes'),
            "window_rule":"include if ts (start) in [window_start, window_end); spanning events stay on start day; no duration clip",
            "baby":{"name":"宗嘉越","sex":"male","birth_date":"2026-07-04","ga_at_birth":"32+4","birth_weight_g":1800,
            "age_days":days,"pma":f"{pma//7}+{pma%7}","corrected_age_days":days-52},
            "records":recs,"recent_growth":pick({'growth'},12),"recent_vaccine_checkup_milestone":pick({'vaccine','checkup','milestone'},20)}

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
    return not o or (isinstance(o,dict) and not o.get('records') and not o.get('text') and not o.get('days'))
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
    elif c=='summary': summary(sys.argv[2],open(sys.argv[3],encoding='utf-8').read()); print('ok')
    elif c=='backup': backup()
    elif c=='restore': restore()
    else: raise SystemExit('usage: export|summary|backup|restore')
