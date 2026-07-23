#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
投放数据看板 - 数据构建脚本
用法:
  python3 build_data.py --offline                     # 用本地 main_s*.json / camp.json
  python3 build_data.py --token XXX                   # 从 Adjust API 拉数(自动定 end=昨天 UTC)
输出: data.json (看板 DATA 块)
口径(已拍板 v1.0):
  消耗=network_cost; 注册=signup_complete_events; CPI=消耗/安装; CPA=消耗/注册
  D0付费率=paying_users_d0/注册; DX ROAS=revenue_total_dX/消耗(仅成熟批次)
  自然量(Organic/Google Organic Search/unknown)不参与 ROI
"""
import json, sys, re, urllib.request, urllib.parse, datetime as dt
from collections import defaultdict

# ===== 基准模型常量 (2026-07 校准, 每月第1周随放大系数校准一起更新) =====
# D7→D75 放大系数 (13个月消耗加权, 回测平均误差6.2%)
MULT75_CH = {("Blaze","FB"):1.41,("Blaze","GG"):1.64,("Blaze","TT"):1.68,
 ("Bliss","FB"):1.61,("Bliss","GG"):1.58,("Bliss","TT"):1.12,
 ("Bondy","FB"):1.69,("Bondy","GG"):1.37,("Bondy","TT"):1.34,
 ("Chille","FB"):1.33,("Chille","GG"):1.76,("Chille","TT"):1.07,
 ("Flare","FB"):1.49,("Flare","GG"):1.74,
 ("Rush","FB"):1.49,("Rush","GG"):1.66,("Rush","TT"):1.23,
 ("Tippo","FB"):1.42,("Tippo","GG"):1.41,("Tippo","TT"):1.86}
MULT75_APP = {"Blaze":1.59,"Bliss":1.60,"Bondy":1.45,"Chille":1.57,"Flare":1.71,"Rush":1.58,"Tippo":1.47}
MULT30_APP = {"Blaze":1.37,"Bliss":1.37,"Bondy":1.31,"Chille":1.32,"Flare":1.44,"Rush":1.32,"Tippo":1.33}
R70_APP = {"Blaze":2.15,"Bliss":1.86,"Bondy":1.57,"Chille":1.42,"Flare":2.04,"Rush":1.58,"Tippo":1.92}  # D7/D0 倍率
SOP_STOP, SOP_WATCH, SOP_SCALE = 0.55, 0.8, 1.2  # 三档线系数
BENCH_VER = "2026-07 校准"
MULT45_APP = {"Blaze":1.47,"Bliss":1.48,"Bondy":1.39,"Chille":1.42,"Flare":1.56,"Rush":1.43,"Tippo":1.41}
# 回测: 用系数预测 2026-03~05 各月 D30 ROAS vs 实际 (模型产物, 月度校准时更新)
BACKTEST = {"mae": 6.2, "rows": [
 ["Blaze","2026-03",1.26,1.12],["Blaze","2026-04",1.22,1.27],["Blaze","2026-05",1.22,1.05],
 ["Bliss","2026-03",1.40,1.53],["Bliss","2026-04",1.26,1.33],["Bliss","2026-05",1.38,1.42],
 ["Bondy","2026-03",1.46,1.49],["Bondy","2026-04",1.48,1.48],["Bondy","2026-05",1.36,1.37],
 ["Chille","2026-03",0.88,0.91],["Chille","2026-04",1.14,1.13],["Chille","2026-05",1.03,1.21],
 ["Flare","2026-03",1.38,1.41],["Flare","2026-04",1.05,0.99],["Flare","2026-05",1.32,1.37],
 ["Rush","2026-03",1.08,1.00],["Rush","2026-04",1.25,1.22],["Rush","2026-05",0.90,0.82],
 ["Tippo","2026-03",0.82,0.74],["Tippo","2026-04",1.27,1.19],["Tippo","2026-05",1.31,1.52]]}

METRICS = ("network_cost,network_impressions,network_clicks,installs,"
           "signup_complete_events,paying_users_d0,retained_users_d1,retained_users_d3,"
           "retained_users_d7,revenue_total_d0,revenue_total_d1,revenue_total_d3,"
           "revenue_total_d7,revenue_total_d14,revenue_total_d30")
CAMP_METRICS = ("network_cost,installs,signup_complete_events,paying_users_d0,"
                "revenue_total_d0,revenue_total_d3,revenue_total_d7")
BASE = "https://automate.adjust.com/reports-service/report"
EXCLUDE_PARTNERS = {"Organic", "Google Organic Search", "unknown"}
CH = {"Facebook": "FB", "Google Ads": "GG", "TikTok for Business": "TT"}
EXCLUDE_APPS = {"Kita"}

def fetch(token, dims, metrics, period):
    q = urllib.parse.urlencode({"dimensions": dims, "metrics": metrics,
                                "date_period": period, "limit": "500000"})
    req = urllib.request.Request(BASE + "?" + q, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["rows"]

CAMP_HIST_METRICS = ("network_cost,revenue_total_d0,revenue_total_d1,revenue_total_d3,"
                     "revenue_total_d7,revenue_total_d14,revenue_total_d30,revenue_total_d45,revenue_total_d75")

def load(token=None):
    if token:
        end = (dt.datetime.utcnow().date() - dt.timedelta(days=1))
        start = end - dt.timedelta(days=120)
        main = []
        s = start
        while s <= end:
            e = min(s + dt.timedelta(days=34), end)
            main += fetch(token, "day,app,partner_name,country_code", METRICS, f"{s}:{e}")
            s = e + dt.timedelta(days=1)
        camp = fetch(token, "day,app,partner_name,campaign_network", CAMP_METRICS,
                     f"{end - dt.timedelta(days=29)}:{end}")
        mid = end - dt.timedelta(days=130)
        camp_hist = fetch(token, "month,app,partner_name,campaign_network", CAMP_HIST_METRICS,
                          f"{end - dt.timedelta(days=262)}:{mid}")
        camp_hist += fetch(token, "month,app,partner_name,campaign_network", CAMP_HIST_METRICS,
                           f"{mid + dt.timedelta(days=1)}:{end}")
    else:
        import glob
        main = []
        for f in sorted(glob.glob("main_s*.json")):
            main += json.load(open(f))["rows"]
        camp = json.load(open("camp.json"))["rows"]
        camp_hist = []
        for f in sorted(glob.glob("camp_hist*.json")):
            camp_hist += json.load(open(f))["rows"]
    return main, camp, camp_hist

def f(r, k): return float(r.get(k) or 0)

def D(s): return dt.date.fromisoformat(s[:10])

def build(main, camp, camp_hist=None):
    camp_hist = camp_hist or []
    for r in main: r["_d"] = D(r["day"])
    for r in camp: r["_d"] = D(r["day"])
    main = [r for r in main if r["app"] not in EXCLUDE_APPS]
    camp = [r for r in camp if r["app"] not in EXCLUDE_APPS]
    end = max(r["_d"] for r in main)
    paid = [r for r in main if r["partner_name"] not in EXCLUDE_PARTNERS]
    for r in paid: r["_ch"] = CH.get(r["partner_name"], "Other")

    def win(n_days, lag=0):  # 窗口: [end-lag-n+1, end-lag]
        e = end - dt.timedelta(days=lag); s = e - dt.timedelta(days=n_days - 1)
        return s, e

    def agg(rows, s, e, keys=None):
        out = defaultdict(lambda: defaultdict(float))
        for r in rows:
            if s <= r["_d"] <= e:
                k = tuple(r[x] for x in keys) if keys else ("_",)
                for m in ["network_cost","installs","signup_complete_events","paying_users_d0",
                          "revenue_total_d0","revenue_total_d1","revenue_total_d3","revenue_total_d7",
                          "revenue_total_d14","revenue_total_d30","network_clicks","network_impressions",
                          "retained_users_d1","retained_users_d3","retained_users_d7"]:
                    if m in r: out[k][m] += f(r, m)
        return out

    def ratio(a, b): return round(a / b, 4) if b else None

    def kpiblock(s, e):
        a = agg(paid, s, e)[("_",)]
        return {"cost": round(a["network_cost"]), "installs": int(a["installs"]),
                "signups": int(a["signup_complete_events"]),
                "cpi": ratio(a["network_cost"], a["installs"]),
                "cpa": ratio(a["network_cost"], a["signup_complete_events"]),
                "payrate": ratio(a["paying_users_d0"], a["signup_complete_events"]),
                "roas_d0": ratio(a["revenue_total_d0"], a["network_cost"])}

    s7, e7 = win(7); ps7, pe7 = win(7, 7)
    kpi = {"cur7": kpiblock(s7, e7), "prev7": kpiblock(ps7, pe7),
           "win7": [str(s7), str(e7)], "pwin7": [str(ps7), str(pe7)]}
    d7s, d7e = win(28, 7); pd7s, pd7e = win(28, 35)
    a = agg(paid, d7s, d7e)[("_",)]; b = agg(paid, pd7s, pd7e)[("_",)]
    kpi["roas_d7"] = {"cur": ratio(a["revenue_total_d7"], a["network_cost"]),
                      "prev": ratio(b["revenue_total_d7"], b["network_cost"]),
                      "win": [str(d7s), str(d7e)]}

    # 日级: 近56天 渠道消耗堆叠 + D0 ROAS
    ds, de = win(56)
    daily = []
    dd = agg(paid, ds, de, ["day"])
    by_ch = agg(paid, ds, de, ["day", "_ch"])
    d = ds
    while d <= de:
        k = (d.isoformat() + "T00:00:00",)
        # day key format check
        dk = None
        for cand in [d.isoformat(), d.isoformat() + "T00:00:00"]:
            if (cand,) in dd: dk = cand; break
        row = {"d": d.isoformat()[5:], "fb": 0, "gg": 0, "tt": 0, "other": 0, "roas": None}
        if dk:
            a = dd[(dk,)]
            row["roas"] = ratio(a["revenue_total_d0"], a["network_cost"])
            for ch in ["FB", "GG", "TT", "Other"]:
                v = by_ch.get((dk, ch), {}).get("network_cost", 0)
                row[ch.lower() if ch != "Other" else "other"] = round(v)
        daily.append(row)
        d += dt.timedelta(days=1)

    # 周度 D7 ROAS 分渠道 (成熟周: 周日 <= end-7)
    weekly = []
    wk = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for r in paid:
        monday = r["_d"] - dt.timedelta(days=r["_d"].weekday())
        if monday + dt.timedelta(days=6) <= end - dt.timedelta(days=7):
            wk[monday][r["_ch"]]["cost"] += f(r, "network_cost")
            wk[monday][r["_ch"]]["rev7"] += f(r, "revenue_total_d7")
    for monday in sorted(wk)[-10:]:
        e = {"w": monday.isoformat()[5:]}
        for ch in ["FB", "GG", "TT"]:
            c = wk[monday][ch]["cost"]
            e[ch.lower()] = round(wk[monday][ch]["rev7"] / c, 3) if c > 500 else None
        weekly.append(e)

    # App × 渠道 (各指标用各自成熟28天窗)
    def block(keys):
        w0 = agg(paid, *win(28), keys=keys)
        w3 = agg(paid, *win(28, 3), keys=keys); w7 = agg(paid, *win(28, 7), keys=keys)
        w14 = agg(paid, *win(28, 14), keys=keys); w30 = agg(paid, *win(28, 30), keys=keys)
        rows = []
        for k in sorted(w0, key=lambda x: -w0[x]["network_cost"]):
            a = w0[k]
            if a["network_cost"] < 50: continue
            r = {"k": list(k), "cost": round(a["network_cost"]), "installs": int(a["installs"]),
                 "cpi": ratio(a["network_cost"], a["installs"]),
                 "signup_rate": ratio(a["signup_complete_events"], a["installs"]),
                 "payrate": ratio(a["paying_users_d0"], a["signup_complete_events"]),
                 "roas_d0": ratio(a["revenue_total_d0"], a["network_cost"]),
                 "ret_d1": ratio(a["retained_users_d1"], a["installs"])}
            for lbl, w, m in [("roas_d3", w3, "revenue_total_d3"), ("roas_d7", w7, "revenue_total_d7"),
                              ("roas_d14", w14, "revenue_total_d14"), ("roas_d30", w30, "revenue_total_d30")]:
                x = w.get(k, {}); r[lbl] = ratio(x.get(m, 0), x.get("network_cost", 0))
            rows.append(r)
        return rows

    app_channel = block(["app", "_ch"])
    apps_tot = block(["app"])

    # 国家 top5+other
    cs, ce = win(28)
    cc = agg(paid, cs, ce, ["country_code"])
    top5 = [k[0] for k in sorted(cc, key=lambda x: -cc[x]["network_cost"])[:5]]
    def ccagg(s, e):
        raw = agg(paid, s, e, ["country_code"])
        out = defaultdict(lambda: defaultdict(float))
        for k, v in raw.items():
            g = k[0].upper() if k[0] in top5 else "其他"
            for m, val in v.items(): out[g][m] += val
        return out
    c0 = ccagg(*win(28)); c7 = ccagg(*win(28, 7)); c7p = ccagg(*win(28, 35))
    tot_cost = sum(v["network_cost"] for v in c0.values())
    countries = []
    for g in sorted(c0, key=lambda x: -c0[x]["network_cost"]):
        a = c0[g]
        if a["network_cost"] < 50: continue
        countries.append({"cc": g, "cost": round(a["network_cost"]),
                          "share": ratio(a["network_cost"], tot_cost),
                          "cpi": ratio(a["network_cost"], a["installs"]),
                          "payrate": ratio(a["paying_users_d0"], a["signup_complete_events"]),
                          "roas_d0": ratio(a["revenue_total_d0"], a["network_cost"]),
                          "roas_d7": ratio(c7.get(g, {}).get("revenue_total_d7", 0), c7.get(g, {}).get("network_cost", 0)) if c7.get(g, {}).get("network_cost", 0) >= 50 else None,
                          "roas_d7_prev": ratio(c7p.get(g, {}).get("revenue_total_d7", 0), c7p.get(g, {}).get("network_cost", 0)) if c7p.get(g, {}).get("network_cost", 0) >= 50 else None})

    # 批次回收曲线 (top4 app, 各点用各自成熟28天窗)
    curves = []
    for ap in [r["k"][0] for r in apps_tot[:4]]:
        pts = []
        for dx, m in [(0, "revenue_total_d0"), (1, "revenue_total_d1"), (3, "revenue_total_d3"),
                      (7, "revenue_total_d7"), (14, "revenue_total_d14"), (30, "revenue_total_d30")]:
            w = agg([r for r in paid if r["app"] == ap], *win(28, dx))[("_",)]
            pts.append({"x": dx, "y": ratio(w.get(m, 0), w.get("network_cost", 0))})
        curves.append({"app": ap, "pts": pts})

    # Campaign 明细 (近14天有消耗) + 投手
    for r in camp: r["_ch"] = CH.get(r["partner_name"], "Other")
    c14s, c14e = win(14)
    cagg = defaultdict(lambda: defaultdict(float))
    for r in camp:
        if r["partner_name"] in EXCLUDE_PARTNERS: continue
        k = (r["campaign_network"], r["app"], r["_ch"])
        if c14s <= r["_d"] <= c14e:
            for m in ["network_cost", "installs", "signup_complete_events", "paying_users_d0", "revenue_total_d0"]:
                cagg[k][m] += f(r, m)
            if r["_d"] == end: cagg[k]["cost_yday"] += f(r, "network_cost")
        if c14s - dt.timedelta(days=7) <= r["_d"] <= c14e - dt.timedelta(days=7):
            cagg[k]["m_cost"] += f(r, "network_cost"); cagg[k]["m_rev7"] += f(r, "revenue_total_d7")
    # 投手归属: 命名前缀解析; 子账户变体并入主名(如 Susanf03/Susanp -> Susan);
    # TT smart+ 等无前缀命名从中段 token 找人名; App 名不算投手
    app_names = {a.lower() for a in set(r["app"] for r in camp)} | {a.lower() for a in MULT75_APP}
    pref_cost = defaultdict(float)
    for k, a in cagg.items():
        m = re.match(r"^([A-Za-z]+)", (k[0] or "").strip())
        if m and m.group(1).lower() not in app_names:
            pref_cost[m.group(1).capitalize()] += a["network_cost"]
    for r in camp_hist:
        m = re.match(r"^([A-Za-z]+)", (r.get("campaign_network") or "").strip())
        if m and m.group(1).lower() not in app_names:
            pref_cost[m.group(1).capitalize()] += float(r.get("network_cost") or 0)
    persons = {p for p, c in pref_cost.items() if c >= 100}
    def canon(tok):
        p = tok.capitalize()
        cands = [b for b in persons if len(b) >= 3 and p.startswith(b)]
        return min(cands, key=len) if cands else None
    # 归属规则(复盘 skill 口径): 命名=账户前缀_产品_…_操作者, 操作者优先。
    # 含 yz→yz; 含 lio→lio; 同现=归属冲突; 其余人名须唯一命中; 多名同现且无 yz/lio→未归属
    def owner(name):
        toks = re.split(r"[_\s]+", (name or "").strip())
        alphas = [m.group(1) for t in toks for m in [re.match(r"^([A-Za-z]+)", t)] if m]
        low = [a.lower() for a in alphas]
        has_yz, has_lio = "yz" in low, "lio" in low
        if has_yz and has_lio: return "归属冲突"
        if has_yz: return "yz"
        if has_lio: return "lio"
        found = set()
        for a in alphas:
            if a.lower() in app_names: continue
            c = canon(a)
            if c: found.add(c)
        if len(found) == 1: return found.pop()
        return "未归属(多名)" if found else "未标注"
    campaigns = []
    for k, a in cagg.items():
        if a["network_cost"] < 20: continue
        d0 = ratio(a["revenue_total_d0"], a["network_cost"])
        flag = "green" if (d0 or 0) >= 0.6 and a["network_cost"] >= 80 else \
               ("red" if a["network_cost"] >= 100 and (d0 or 0) < 0.3 else "")
        campaigns.append({"name": k[0], "app": k[1], "ch": k[2], "owner": owner(k[0]),
                          "cost": round(a["network_cost"]), "yday": round(a.get("cost_yday", 0)),
                          "installs": int(a["installs"]),
                          "cpi": ratio(a["network_cost"], a["installs"]),
                          "roas_d0": d0,
                          "roas_d7": ratio(a.get("m_rev7", 0), a.get("m_cost", 0)),
                          "flag": flag})
    # ===== 基准与模型预估 =====
    def app_tgt(app):
        m75 = MULT75_APP.get(app); m30 = MULT30_APP.get(app); r70 = R70_APP.get(app)
        if not m75: return None
        t7 = 1 / m75
        return {"tgt7": round(t7, 3), "tgt0": round(t7 / r70, 3) if r70 else None,
                "tgt30": round(m30 / m75, 3) if m30 else None,
                "stop": round(t7 / r70 * SOP_STOP, 3) if r70 else None,
                "watch": round(t7 / r70 * SOP_WATCH, 3) if r70 else None,
                "scale": round(t7 / r70 * SOP_SCALE, 3) if r70 else None}
    bench_apps = {a: t for a in MULT75_APP for t in [app_tgt(a)] if t}
    w7b = agg(paid, *win(28, 7), keys=["app", "_ch"]); w0b = agg(paid, *win(28), keys=["app", "_ch"])
    bench_chs = []
    for k, a in sorted(w7b.items(), key=lambda x: -x[1]["network_cost"]):
        if a["network_cost"] < 800 or not a["installs"]: continue
        m = MULT75_CH.get(k) or MULT75_APP.get(k[0])
        if not m: continue
        cur7 = a["revenue_total_d7"] / a["network_cost"]
        rev7i = a["revenue_total_d7"] / a["installs"]
        b0 = w0b.get(k, {})
        cpi_now = b0.get("network_cost", 0) / b0["installs"] if b0.get("installs") else a["network_cost"] / a["installs"]
        allow = rev7i * m
        bench_chs.append({"app": k[0], "ch": k[1], "mult": m, "tgt7": round(1 / m, 3),
                          "cur7": round(cur7, 3), "cpi": round(cpi_now, 2), "rev7i": round(rev7i, 2),
                          "allow": round(allow, 2), "room": round(allow / cpi_now - 1, 3) if cpi_now else None,
                          "pred75": round(cur7 * m, 2), "cost28": round(b0.get("network_cost", 0))})

    # ===== 模型建议 (渠道级 + campaign 级) =====
    suggestions = []
    for b in bench_chs:
        if b["room"] is None: continue
        tag = f'{b["app"]}·{b["ch"]}'
        if b["room"] <= -0.05:
            suggestions.append({"level": "cut", "scope": "渠道", "obj": tag, "cost": b["cost28"],
                "cur": f'CPI ${b["cpi"]} / D7 ROAS {b["cur7"]}', "pred": f'预测 D75 回收 {b["pred75"]}',
                "action": f'降出价：把 CPI 压到 ${b["allow"]} 以内（当前超回本线 {abs(round(b["room"]*100))}%），压不下来则收缩预算',
                "why": f'可承受 CPI = 每安装 D7 收入 ${b["rev7i"]} × 系数 {b["mult"]}'})
        elif b["room"] >= 0.2 and b["cur7"] >= b["tgt7"]:
            cap = round(b["allow"] * 0.9, 2)
            suggestions.append({"level": "scale", "scope": "渠道", "obj": tag, "cost": b["cost28"],
                "cur": f'CPI ${b["cpi"]} / D7 ROAS {b["cur7"]}', "pred": f'预测 D75 回收 {b["pred75"]}',
                "action": f'可加价放量：出价上限 ${cap}（可承受 ${b["allow"]} 留 10% 安全垫），空间 +{round(b["room"]*100)}%',
                "why": f'当前 D7 {b["cur7"]} ≥ 目标 {b["tgt7"]}，且价格远低于回本线'})
    for c in campaigns:
        t = bench_apps.get(c["app"])
        if not t or c["roas_d0"] is None: continue
        pred = round(c["roas_d0"] * R70_APP[c["app"]] * MULT75_APP[c["app"]], 2)
        if c["cost"] >= 100 and c["roas_d0"] < t["stop"]:
            c["flag"] = "stop"
            suggestions.append({"level": "stop", "scope": "Campaign", "obj": c["name"], "owner": c["owner"], "cost": c["cost"],
                "cur": f'D0 ROAS {c["roas_d0"]:.2f} < 止损线 {t["stop"]}', "pred": f'预测 D75 回收仅 {pred}',
                "action": "建议当日停投（投手可申诉一次，负责人裁决）", "why": f'{c["app"]} 三档线（{BENCH_VER}）'})
        elif c["cost"] >= 100 and c["roas_d0"] < t["watch"]:
            c["flag"] = "watch"
            suggestions.append({"level": "watch", "scope": "Campaign", "obj": c["name"], "owner": c["owner"], "cost": c["cost"],
                "cur": f'D0 ROAS {c["roas_d0"]:.2f} < 观察线 {t["watch"]}', "pred": f'预测 D75 回收 {pred}',
                "action": "预算下调 30% 挂观察，3 天未回线按止损处理", "why": f'{c["app"]} 三档线（{BENCH_VER}）'})
        elif c["cost"] >= 80 and c["roas_d0"] >= t["scale"]:
            c["flag"] = "scale"
            suggestions.append({"level": "scale", "scope": "Campaign", "obj": c["name"], "owner": c["owner"], "cost": c["cost"],
                "cur": f'D0 ROAS {c["roas_d0"]:.2f} ≥ 放量线 {t["scale"]}', "pred": f'预测 D75 回收 {pred}',
                "action": "日预算 +50% 阶梯放量，连续 2 天保持可再加", "why": f'{c["app"]} 三档线（{BENCH_VER}）'})
        else:
            c["flag"] = ""
    # ===== 昨日全量 campaign 模型预估 =====
    yday = []
    yagg = defaultdict(lambda: defaultdict(float))
    for r in camp:
        if r["partner_name"] in EXCLUDE_PARTNERS or r["_d"] != end: continue
        k = (r["campaign_network"], r["app"], r["_ch"])
        for m in ["network_cost", "installs", "signup_complete_events", "revenue_total_d0"]:
            yagg[k][m] += f(r, m)
    for k, a in yagg.items():
        if a["network_cost"] < 10: continue
        app = k[1]
        if app not in MULT75_APP: continue
        d0 = ratio(a["revenue_total_d0"], a["network_cost"])
        m75 = MULT75_CH.get((app, k[2])) or MULT75_APP[app]
        p7 = None if d0 is None else round(d0 * R70_APP[app], 3)
        yday.append({"name": k[0], "app": app, "ch": k[2], "owner": owner(k[0]),
                     "cost": round(a["network_cost"], 1), "installs": int(a["installs"]),
                     "cpi": ratio(a["network_cost"], a["installs"]),
                     "d0": d0, "p7": p7,
                     "p30": None if p7 is None else round(p7 * MULT30_APP[app], 3),
                     "p75": None if p7 is None else round(p7 * m75, 3),
                     "small": a["network_cost"] < 50 or a["installs"] < 10})
    yday.sort(key=lambda x: -x["cost"])

    order = {"stop": 0, "cut": 1, "watch": 2, "scale": 3}
    suggestions.sort(key=lambda s: (order[s["level"]], -s["cost"]))
    keep = [s for s in suggestions if s["level"] != "scale"][:20]
    keep += [s for s in suggestions if s["level"] == "scale"][:10]
    suggestions = keep
    import hashlib as _h
    SLA = {"stop": "2 小时内", "cut": "当日", "watch": "当日", "scale": "24 小时内"}
    for s in suggestions:
        s["id"] = _h.sha1((end.isoformat() + s["level"] + s["obj"]).encode()).hexdigest()[:10]
        s["sla"] = SLA[s["level"]]

    campaigns.sort(key=lambda x: -x["cost"])
    rest = campaigns[60:]
    campaigns = campaigns[:60]
    rest_row = None
    if rest:
        rest_row = {"n": len(rest), "cost": round(sum(r["cost"] for r in rest)),
                    "rev_share_note": ratio(sum((r["roas_d0"] or 0) * r["cost"] for r in rest), sum(r["cost"] for r in rest))}
    owners = defaultdict(lambda: defaultdict(float))
    for r in campaigns + rest:
        o = owners[r["owner"]]
        o["cost"] += r["cost"]; o["rev0"] += (r["roas_d0"] or 0) * r["cost"]
        o["mc"] += 0 if r["roas_d7"] is None else r["cost"]
        o["n"] += 1
        o["installs"] += r["installs"]
    owner_rows = [{"owner": k, "cost": round(v["cost"]), "n": int(v["n"]),
                   "cpi": ratio(v["cost"], v["installs"]),
                   "roas_d0": ratio(v["rev0"], v["cost"])} for k, v in owners.items()]
    owner_rows.sort(key=lambda x: -x["cost"])

    # ===== 投手 D7 / D30 / 回本周期 =====
    # D7: 近期成熟窗 (日级明细中 cohort ≤ T-7)
    od7 = defaultdict(lambda: [0.0, 0.0])
    for r in camp:
        if r["partner_name"] in EXCLUDE_PARTNERS or r["_d"] > end - dt.timedelta(days=7): continue
        o = owner(r["campaign_network"])
        od7[o][0] += f(r, "network_cost"); od7[o][1] += f(r, "revenue_total_d7")
    # 历史月度 (成熟度按月末+dx判断)
    def month_mature(m, dx):
        y, mm = int(m[:4]), int(m[5:7])
        last = dt.date(y, mm, 28)
        while (last + dt.timedelta(days=1)).month == mm: last += dt.timedelta(days=1)
        return last + dt.timedelta(days=dx) <= end
    OFFS = [0, 1, 3, 7, 14, 30, 45, 75]
    o30 = defaultdict(lambda: [0.0, 0.0])
    opb = defaultdict(lambda: defaultdict(float))  # 单一批次集(成熟到75)的各节点回收
    for r in camp_hist:
        if r["partner_name"] in EXCLUDE_PARTNERS or r["app"] == "Kita": continue
        mth = r["month"][:7]
        o = owner(r["campaign_network"])
        c = float(r.get("network_cost") or 0)
        if c <= 0: continue
        if month_mature(mth, 30):
            o30[o][0] += c; o30[o][1] += float(r.get("revenue_total_d30") or 0)
        if month_mature(mth, 75):
            opb[o]["cost"] += c
            for dx in OFFS:
                opb[o][f"r{dx}"] += float(r.get(f"revenue_total_d{dx}") or 0)
    for row in owner_rows:
        o = row["owner"]
        c7, r7 = od7.get(o, [0, 0])
        row["roas_d7"] = ratio(r7, c7) if c7 >= 300 else None
        c30, r30 = o30.get(o, [0, 0])
        row["roas_d30"] = ratio(r30, c30) if c30 >= 500 else None
        pb = opb.get(o)
        row["pb"] = None; row["pb_est"] = False
        if pb and pb["cost"] >= 1000:
            roas = [(dx, pb[f"r{dx}"] / pb["cost"]) for dx in OFFS]
            hit = None
            for i in range(1, len(roas)):
                d0_, r0_ = roas[i - 1]; d1_, r1_ = roas[i]
                if r0_ < 1 <= r1_:
                    hit = d0_ + (1 - r0_) / (r1_ - r0_) * (d1_ - d0_); break
            if roas[0][1] >= 1: hit = 0
            if hit is not None:
                row["pb"] = round(hit)
            else:
                r45, r75 = roas[-2][1], roas[-1][1]
                slope = (r75 - r45) / 30
                if slope > 1e-4:
                    est = 75 + (1 - r75) / slope
                    if est <= 365: row["pb"] = round(est); row["pb_est"] = True

    return {"updated": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "end": end.isoformat(), "kpi": kpi, "daily": daily, "weekly_d7": weekly,
            "app_channel": app_channel, "apps": apps_tot, "countries": countries,
            "curves": curves, "campaigns": campaigns, "campaigns_rest": rest_row,
            "owners": owner_rows,
            "yday": yday,
            "bench": {"ver": BENCH_VER, "apps": bench_apps, "chs": bench_chs,
                      "mult": {"apps": {a: {"r70": R70_APP[a], "m30": MULT30_APP[a],
                                            "m45": MULT45_APP[a], "m75": MULT75_APP[a]} for a in MULT75_APP},
                               "chs": {k[0] + "|" + k[1]: v for k, v in MULT75_CH.items()}},
                      "backtest": BACKTEST},
            "suggestions": suggestions,
            "check": {"cost_121d": round(sum(f(r, "network_cost") for r in paid))}}

if __name__ == "__main__":
    token = None
    if "--token" in sys.argv: token = sys.argv[sys.argv.index("--token") + 1]
    main, camp, camp_hist = load(token)
    data = build(main, camp, camp_hist)
    json.dump(data, open("data.json", "w"), ensure_ascii=False)
    print("data.json written, end =", data["end"], "check:", data["check"])
