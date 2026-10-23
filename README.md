# 嘉越成长记（宗嘉越成长记录 PWA）

Static PWA (Chinese UI) on GitHub Pages + data in textdb.online. No server, no accounts.

- Page: https://zongxianghe-code.github.io/jiayue-tracker/ (repo `zongxianghe-code/jiayue-tracker`, Pages from `main` `/`)
- Source deployed = `site/` (this folder's `site/` is the git repo that is pushed).
- Keys / family link: `.secrets` (chmod 600, never committed). The family link carries the three textdb keys in the URL hash `#d=…&m=…&s=…`; the app stores them in localStorage.

## Data model
Three textdb docs (each `https://textdb.online/<key>` read, `POST https://api.textdb.online/update/` key+value write — full overwrite):
- `DAD_KEY` – written only by devices set to 爸爸; `MOM_KEY` – only by 妈妈 devices. `{v,author,updated,records:{id:{id,type,ts,end_ts,data,who,by,created_at,updated_at,deleted?}}}`
  Each write = fresh read of own doc immediately before, merge pending local changes, write. App merges both docs by id, newest `updated_at` wins; deletes are tombstones. Editing the other parent's record writes an override copy (same id) into your own doc.
- `SUMMARY_KEY` – written only by the bot: `{v:2,days:{'YYYY-MM-DD':{text(markdown, tables ok),updated}},updated}` (last 120 days; v1 `{date,text}` auto-migrated); shown on the 小结 tab.
- Types: growth{weight g,length cm,hc cm}, feed{kind breast|bottle_bm|formula, side L|R|B, minutes, ml}, solid{food,amount,reaction}, sleep(ts,end_ts; open = sleeping), diaper{kind}, vaccine{name,dose}, checkup{hospital}, milestone{event}; all may have note. `ts` = local time `YYYY-MM-DDTHH:MM` (Asia/Shanghai).
- Sync: poll every 5 s while visible + on visibilitychange/online; offline edits queue in localStorage.

## Day window (calendar day Asia/Shanghai)
A summary **day D** covers **[D 00:00, D+1 00:00)**. Morning job publishes yesterday's calendar day.
- **Point events** (diaper, bottle, growth, …): belong to D if `ts` ∈ [D 00:00, D+1 00:00).
- **Sleep / breast feed** (timed): included on D if the interval **overlaps** the window (started before D+1 00:00 and ended after D 00:00, or still open and started before D+1 00:00).
- **Midnight split**: duration on D is the intersection with [D 00:00, D+1 00:00). Export sets clipped `duration_min` plus `clip_start` / `clip_end`. Pre-midnight minutes count on the start day; post-midnight minutes count on the next day.
- Open feed/sleep (no `end_ts` / no `minutes`): for day D's portion only, assume ended at D+1 00:00 (`assumed_end: true` / `end_assumed` ISO) — **not written to live textdb**. Summary text should note 「未点结束，按当天24点估算」.
- App UI 「今日」 also uses calendar midnight.

## Week window
`export-week YYYY-MM-DD` — date must be a **Sunday**. Week = **[that Mon 00:00, next Mon 00:00)** (Mon–Sun).
Weekly summaries stored in SUMMARY_KEY as `weeks: {"YYYY-MM-DD": {text, updated}}` (Sunday date), alongside `days`.

## Bot (daily ~ morning, weekly optional)
    python3 tools/jy.py export 2026-10-17 > /tmp/day.json
    python3 tools/jy.py summary 2026-10-17 summary.md
    python3 tools/jy.py export-week 2026-10-18 > /tmp/week.json   # Sunday
    python3 tools/jy.py summary-week 2026-10-18 week.md

## Redeploy
    cd site && git add -A && git commit -m update && git push   # Pages rebuilds in ~1 min
Bump `C='jy-vN'` in `site/sw.js` when changing cached files.

## Growth reference data (not fabricated)
- WHO Child Growth Standards 2006, boys, weight/length/head-circumference-for-age LMS 0–24 months: CDC NCHS files `WHO-Boys-*-Percentiles.csv` (ftp.cdc.gov/pub/Health_Statistics/NCHS/growthcharts/), copies in `ref/`.
- Fenton TR, Kim JH. BMC Pediatrics 2013;13:59 — boys LMS by gestational day (23–50 wk weight, 24–50 wk length/HC), from the R package growthcleanr 2.2.1 (CRAN archive, `inst/extdata/fentlms_forz.csv.gz`, sex 0 = male), copy `ref/fenton_lms.csv`. Note: the Fenton data is copyrighted by the University of Calgary (free for individual/clinical use; contact tfenton@ucalgary.ca); later growthcleanr versions dropped the file.
- Percentiles P3/10/50/90/97 computed from LMS (z = ±1.8808, ±1.2816, 0) → `site/ref.json` (Fenton x = PMA weeks, WHO x = corrected months, weight in g).
- Vaccine list: China National Immunization Program (2025 DTaP adjustment: 2/4/6/18 months + 6 y DT), reference only.

## Backup / keep-alive / restore
textdb.online deletes docs not accessed or updated for 30 days. Private repo `zongxianghe-code/jiayue-data` (cloned at `data-backup/`, gitignored):
    python3 tools/jy.py backup    # reads all 3 docs (the read keeps them alive), saves <name>/<name>_YYYY-MM-DD.json + latest.json for non-empty docs, commits+pushes only if changed
    python3 tools/jy.py restore   # for each doc: if live is EMPTY and latest backup has data, write backup back; never overwrites non-empty live data
Run backup daily (e.g. right after the 8:00 summary).
