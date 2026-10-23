#!/usr/bin/env python3
"""Generate & optionally publish daily summary markdown from export()."""
import sys,datetime as dt
sys.path.insert(0,'.'); import jy
WD='一二三四五六日'
def hm(m):
    m=int(m or 0)
    if m<0: m=0
    return f"{m//60}小时{m%60}分" if m>=60 and m%60 else (f"{m//60}小时" if m>=60 else f"{m}分")
def age_line(baby,d):
    day0=dt.date.fromisoformat(d); cw,cd=divmod(max(0,baby['corrected_age_days']),7)
    return f"**{day0.month}月{day0.day}日（周{WD[day0.weekday()]}）** · 出生第{baby['age_days']}天 · 矫正{cw}周+{cd}天"
def night_min(r):
    a=dt.datetime.fromisoformat(r.get('clip_start') or r['ts'])
    end=r.get('clip_end') or r.get('end_assumed') or r.get('end_ts')
    if not end: return 0
    b=dt.datetime.fromisoformat(end); total=0; cur=a
    while cur<b:
        day=cur.date()
        lo=max(cur,dt.datetime.combine(day,dt.time(19,0))); hi=min(b,dt.datetime.combine(day+dt.timedelta(days=1),dt.time(0,0)))
        if lo<hi: total+=int((hi-lo).total_seconds()//60)
        lo=max(cur,dt.datetime.combine(day,dt.time(0,0))); hi=min(b,dt.datetime.combine(day,dt.time(7,0)))
        if lo<hi: total+=int((hi-lo).total_seconds()//60)
        cur=dt.datetime.combine(day+dt.timedelta(days=1),dt.time(0,0))
    return total
def gen(d):
    e=jy.export(d); R=e['records']; baby=e['baby']
    feeds=[r for r in R if r['type']=='feed']
    breast=[r for r in feeds if r['data'].get('kind')=='breast']
    formula=[r for r in feeds if r['data'].get('kind') in ('formula','bottle_bm')]
    sleeps=[r for r in R if r['type']=='sleep']
    diapers=[r for r in R if r['type']=='diaper']
    exs=[r for r in R if r['type']=='exercise']
    supps=[r for r in R if r['type']=='supp']
    growth=[r for r in R if r['type']=='growth']
    assumed=[r for r in R if r.get('assumed_end')]
    lines=[age_line(baby,d),'']
    bmin=sum(r.get('duration_min') or 0 for r in breast)
    fml=sum(r['data'].get('ml') or 0 for r in formula)
    times=sorted(r['ts'] for r in feeds)
    gaps=[int((dt.datetime.fromisoformat(b)-dt.datetime.fromisoformat(a)).total_seconds()//60) for a,b in zip(times,times[1:])]
    avg=round(sum(gaps)/len(gaps)) if gaps else None
    longest=max(gaps) if gaps else None
    long_s=None
    if longest is not None:
        i=gaps.index(longest); a,b=times[i],times[i+1]
        long_s=f"{a[11:16]}→{('次日' if a[:10]!=b[:10] else '')+b[11:16]}"
    if not feeds: kind_s='无'
    elif breast and not formula: kind_s='全亲喂'
    elif formula and not breast: kind_s='全配方'
    else: kind_s=f"{len(breast)}亲喂+{len(formula)}瓶喂"
    ass_b=[r for r in breast if r.get('assumed_end')]
    ass_note=f"（其中{len(ass_b)}次未点结束，按当天24点估算）" if ass_b else ''
    lines += ['### 喂养','| 项目 | 数值 |','|---|---|',
        f"| 次数 | {len(feeds)}次（{kind_s}）{ass_note} |",
        f"| 亲喂总时长 | {('约'+hm(bmin)) if breast else '未记录'} |",
        f"| 配方奶 | {(str(fml)+'ml') if formula else '未记录'} |"]
    if avg is not None:
        lines += [f"| 平均间隔 | 约{hm(avg)}（按开奶时间） |", f"| 最长间隔 | 约{hm(longest)}（{long_s}） |"]
    lines.append('')
    smin=sum(r.get('duration_min') or 0 for r in sleeps)
    nmin=sum(night_min(r) for r in sleeps); dmin=max(0,smin-nmin)
    ass_s=[r for r in sleeps if r.get('assumed_end')]
    sleep_extra=('；'+'；'.join(f"{r['ts'][11:16]}起未点结束，按当天24点估算" for r in ass_s)) if ass_s else ''
    lines += ['### 睡眠','| 项目 | 数值 |','|---|---|']
    if sleeps:
        lines += [f"| 总时长 | 约{hm(smin)}（{len(sleeps)}段{sleep_extra}） |",
                  f"| 夜间 | 约{hm(nmin)} |", f"| 白天 | 约{hm(dmin)} |"]
        longest_s=max(sleeps, key=lambda r:r.get('duration_min') or 0)
        a=longest_s.get('clip_start') or longest_s['ts']
        b=longest_s.get('clip_end') or longest_s.get('end_assumed') or longest_s.get('end_ts')
        as_=a[11:16]
        bs=(('次日' if b and b[:10]!=a[:10] else '')+(b[11:16] if b else '未结束'))
        lines += [f"| 最长一觉 | 约{hm(longest_s.get('duration_min'))}（{as_}→{bs}） |",
                  f"| 次数 | {len(sleeps)}段"+(f"（含{len(ass_s)}段按24点估算）" if ass_s else "")+" |"]
    else: lines.append("| 总时长 | 未记录 |")
    lines.append('')
    wet=sum(1 for r in diapers if r['data'].get('kind') in ('wet','both'))
    dirty=sum(1 for r in diapers if r['data'].get('kind') in ('dirty','both'))
    both=sum(1 for r in diapers if r['data'].get('kind')=='both')
    diap=f"小便{wet}次，大便{dirty}次"+(f"（其中{both}次尿+便）" if both else "") if diapers else "未记录"
    items=[]
    for r in exs:
        items += list(r['data'].get('items') or [])
        k=r['data'].get('kind')
        if k=='tummy': items.append('趴卧')
        elif k=='passive': items.append('被动操/抚触')
        elif k=='other' and r['data'].get('name'): items.append(r['data']['name'])
    seen=set(); ex_s=[]
    for x in items:
        if x and x not in seen: seen.add(x); ex_s.append(x)
    def supp_line(k,label):
        g=[r for r in supps if r['data'].get('which')==k]
        if not g: return f"| {label} | ✗ 未记录 |"
        r=sorted(g,key=lambda x:x['ts'])[-1]
        return f"| {label} | ✓ {r['ts'][11:16]} {r['data'].get('dose') or ''} |"
    lines += ['### 尿布 / 运动 / 补剂','| 项目 | 情况 |','|---|---|',
        f"| 尿布 | {diap} |", f"| 运动 | {'、'.join(ex_s) if ex_s else '未记录'} |",
        supp_line('AD','AD'), supp_line('D','D'), supp_line('iron','铁'), '']
    if growth:
        lines += ['### 生长','| 项目 | 数值 |','|---|---|']
        g=growth[-1]; dd=g['data']
        if dd.get('weight'):
            note=f"（{dd['note']}）" if dd.get('note') else ''
            lines += [f"| 体重 | {dd['weight']}g（{g['ts'][11:16]}）{note} |",
                      f"| 较出生 | +{dd['weight']-1800}g（出生1800g） |",
                      f"| 平均日增 | 约{round((dd['weight']-1800)/max(1,baby['age_days']))}g/天（{baby['age_days']}天） |"]
        if dd.get('length'): lines.append(f"| 身长 | {dd['length']}cm |")
        if dd.get('hc'): lines.append(f"| 头围 | {dd['hc']}cm |")
        lines.append('')
    tips=[]
    for r in assumed:
        if r['type']=='sleep': tips.append(f"{r['ts'][11:16]}起的睡眠未点「醒了」，小结按当天24点估算；点一下结束会更准。")
        if r['type']=='feed': tips.append(f"{r['ts'][11:16]}起的亲喂未点「喂完」，小结按当天24点估算。")
    tips.append(f"矫正约{baby['corrected_age_days']//7}–{baby['corrected_age_days']//7+1}周时，常见喂养间隔大约2–3小时；趴卧短时、清醒、有人看护；早产儿继续仰卧安全睡。")
    if not all(any(r['data'].get('which')==k for r in supps) for k in ('AD','D','iron')):
        tips.append("补剂吃完顺手在首页点AD、D、铁，避免漏吃或重复吃。")
    tips.append("具体评估以体检医生为准。")
    lines += ['### 建议']+[f"{i}. {t}" for i,t in enumerate(tips,1)]+['','*仅供参考，不替代医生意见。*','']
    return '\n'.join(lines)
if __name__=='__main__':
    dates=sys.argv[1:] or ['2026-10-17','2026-10-18','2026-10-19']
    stamp=dt.datetime.now().strftime('%Y%m%d%H%M'); pub=[]
    for d in dates:
        text=gen(d); path=f"../summaries/{stamp}-嘉越日报-{d}.md"
        open(path,'w').write(text); jy.summary(d,text); pub.append(path)
        print('===',d,'==='); print(text); print()
    print('published',pub)
