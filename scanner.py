import yfinance as yf
import pandas as pd
import os
from datetime import datetime

BUY_VOL_RATIO = 1.5
CHEAP_PER     = 15.0
PRICEY_PER    = 25.0

PEERS = {
    "7203.T": ["7267.T", "7201.T", "7269.T"],
    "7267.T": ["7203.T", "7201.T", "7269.T"],
    "7201.T": ["7203.T", "7267.T", "7269.T"],
    "9984.T": ["9983.T", "4755.T", "3659.T"],
    "6758.T": ["6752.T", "6753.T", "6971.T"],
    "6752.T": ["6758.T", "6753.T", "6971.T"],
    "4063.T": ["4005.T", "3407.T", "4183.T"],
    "8306.T": ["8316.T", "8411.T"],
    "8316.T": ["8306.T", "8411.T"],
    "8411.T": ["8306.T", "8316.T"],
    "9432.T": ["9433.T", "9434.T"],
    "9433.T": ["9432.T", "9434.T"],
    "4568.T": ["4519.T", "4507.T"],
    "6367.T": ["6301.T", "6302.T"],
    "8001.T": ["8002.T", "8031.T", "8058.T"],
    "8002.T": ["8001.T", "8031.T", "8058.T"],
    "8031.T": ["8001.T", "8002.T", "8058.T"],
    "8058.T": ["8001.T", "8002.T", "8031.T"],
}

def fetch_peers(symbol):
    peers = PEERS.get(symbol.upper(), [])
    if not peers: return {"per_avg": None, "roe_avg": None}
    pers, roes = [], []
    for p in peers:
        try:
            info = yf.Ticker(p).info
            per  = info.get("trailingPE") or info.get("forwardPE")
            roe  = info.get("returnOnEquity")
            if per: pers.append(float(per))
            if roe: roes.append(float(roe)*100)
        except: pass
    return {
        "per_avg": round(sum(pers)/len(pers), 1) if pers else None,
        "roe_avg": round(sum(roes)/len(roes), 1) if roes else None,
    }

def calc_state(trend_up, vol_ratio):
    vr = vol_ratio or 0.0
    if trend_up and vr >= BUY_VOL_RATIO: return "強気"
    elif trend_up or vr >= 1.0:          return "中立"
    else:                                 return "弱気"

def calc_verdict(score):
    if score >= 70:   return "買い優勢"
    elif score >= 40: return "様子見"
    else:             return "見送り"

def calc_score_detail(d, peers):
    s_trend = 25 if d["trend_up"] else 0
    vr = d["vol_ratio"] or 0.0
    if vr >= 2.0:   s_vol = 15
    elif vr >= 1.5: s_vol = 10
    elif vr >= 1.0: s_vol = 5
    else:           s_vol = 0
    s_val = 0
    try:
        if d["per"] and peers.get("per_avg"):
            if d["per"] < peers["per_avg"]: s_val += 10
        pbr = d.get("pbr")
        if pbr is not None:
            if pbr < 1.0: s_val += 5
            elif pbr < 1.5: s_val += 3
        div = d.get("div_yield")
        if div is not None:
            if div >= 3.0: s_val += 5
            elif div >= 2.0: s_val += 3
    except: pass
    yoy_vals = [d.get("rev_yoy"), d.get("op_yoy"), d.get("net_yoy")]
    positive = sum(1 for v in yoy_vals if v is not None and v > 0)
    if positive == 3:   s_growth = 15
    elif positive == 2: s_growth = 10
    elif positive == 1: s_growth = 5
    else:               s_growth = 0
    rel = d.get("relative5")
    if rel is None:   s_market = 0
    elif rel >= 1.0:  s_market = 10
    elif rel >= 0.0:  s_market = 5
    else:             s_market = 0
    s_entry = 0
    try:
        close    = d["close"]
        pullback = d.get("pullback")
        breakout = d.get("breakout_20")
        diffs = []
        if pullback and pullback > 0: diffs.append(abs((close/pullback-1)*100))
        if breakout and breakout > 0: diffs.append(abs((close/breakout-1)*100))
        if diffs:
            min_diff = min(diffs)
            if min_diff <= 2.0:   s_entry = 15
            elif min_diff <= 5.0: s_entry = 8
    except: pass
    total = s_trend + s_vol + s_val + s_growth + s_market + s_entry
    return {"trend": s_trend, "volume": s_vol, "value": s_val,
            "growth": s_growth, "market": s_market, "entry": s_entry, "total": total}

def analyze(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period="6mo")
        if hist.empty or len(hist) < 75: return None
        df = hist[["Close","High","Low","Volume"]].copy()
        df["prev_close"] = df["Close"].shift(1)
        df["tr"] = df.apply(lambda r: max(
            r["High"]-r["Low"],
            abs(r["High"]-r["prev_close"]) if pd.notna(r["prev_close"]) else 0,
            abs(r["Low"] -r["prev_close"]) if pd.notna(r["prev_close"]) else 0,
        ), axis=1)
        df["ma5"]       = df["Close"].rolling(5).mean()
        df["ma25"]      = df["Close"].rolling(25).mean()
        df["ma75"]      = df["Close"].rolling(75).mean()
        df["atr14"]     = df["tr"].rolling(14).mean()
        df["vol_avg20"] = df["Volume"].rolling(20).mean()
        df["high20"]    = df["High"].rolling(20).max()
        latest    = df.iloc[-1]
        close     = round(float(latest["Close"]), 1)
        ma5       = round(float(latest["ma5"]),   1)
        ma25      = round(float(latest["ma25"]),  1)
        ma75      = round(float(latest["ma75"]),  1)
        atr       = round(float(latest["atr14"]), 1) if pd.notna(latest["atr14"]) else None
        breakout_20 = round(float(latest["high20"]), 1)
        pullback  = round(ma25 - atr, 1) if atr is not None else ma25
        vol_avg20 = float(latest["vol_avg20"])
        vol_ratio = round(float(latest["Volume"])/vol_avg20, 2) if vol_avg20 > 0 else None
        trend_up  = bool(ma25 > ma75)
        closes    = df["Close"].tail(20).round(1).tolist()
        last4     = df["Close"].tail(4).round(1).tolist()
        recent = df.tail(4)
        vol_days = []
        for i in range(1, 4):
            day  = recent.iloc[i]
            prev = recent.iloc[i-1]
            vol_days.append({
                "up":        bool(day["Close"] > prev["Close"]),
                "vol_above": bool(day["Volume"] > vol_avg20),
                "volume":    int(day["Volume"]),
                "vol_prev":  int(prev["Volume"]),
            })
        up_with_vol   = sum(1 for d in vol_days if d["up"] and d["vol_above"])
        down_with_vol = sum(1 for d in vol_days if not d["up"] and d["vol_above"])
        if up_with_vol >= 2:     vol_strength = "強い流入"
        elif down_with_vol >= 2: vol_strength = "弱い"
        else:                    vol_strength = "通常"
        stock_ret5 = nikkei_ret5 = relative5 = None
        try:
            closes_6 = df["Close"].tail(6)
            if len(closes_6) >= 6:
                rets = [(float(closes_6.iloc[i])/float(closes_6.iloc[i-1])-1)*100 for i in range(1,6)]
                stock_ret5 = round(sum(rets)/len(rets), 2)
            nk = yf.Ticker("^N225").history(period="15d")
            nk_closes = nk["Close"].tail(6)
            if len(nk_closes) >= 6:
                nk_rets = [(float(nk_closes.iloc[i])/float(nk_closes.iloc[i-1])-1)*100 for i in range(1,6)]
                nikkei_ret5 = round(sum(nk_rets)/len(nk_rets), 2)
            if stock_ret5 is not None and nikkei_ret5 is not None:
                relative5 = round(stock_ret5 - nikkei_ret5, 2)
        except: pass
        rev_yoy = op_yoy = net_yoy = None
        try:
            qf = ticker.quarterly_financials
            if qf is not None and not qf.empty and qf.shape[1] >= 5:
                def _yoy(keys):
                    for idx in qf.index:
                        idx_str = str(idx).lower()
                        if any(k in idx_str for k in keys):
                            try:
                                v_new = float(qf.iloc[qf.index.get_loc(idx), 0])
                                v_old = float(qf.iloc[qf.index.get_loc(idx), 4])
                                if v_old and v_old != 0:
                                    return round((v_new/v_old-1)*100, 1)
                            except: pass
                    return None
                rev_yoy = _yoy(["total revenue","revenue"])
                op_yoy  = _yoy(["operating income","ebit","operating profit"])
                net_yoy = _yoy(["net income","net profit"])
        except: pass
        per = pbr = roe = roa = div_yield = equity_ratio = payout_ratio = None
        name = symbol
        try:
            info    = ticker.info
            per     = info.get("trailingPE") or info.get("forwardPE")
            per     = round(float(per), 1) if per else None
            pbr_raw = info.get("priceToBook")
            pbr     = round(float(pbr_raw), 1) if pbr_raw else None
            roe_raw = info.get("returnOnEquity")
            roa_raw = info.get("returnOnAssets")
            div_raw = info.get("dividendYield")
            pay_raw = info.get("payoutRatio")
            eq_raw  = info.get("equityToAssets")
            roe = round(float(roe_raw)*100, 1) if roe_raw else None
            roa = round(float(roa_raw)*100, 1) if roa_raw else None
            if div_raw is not None:
                div_yield = round(float(div_raw)*100, 1) if float(div_raw) < 1 else round(float(div_raw), 1)
            if pay_raw is not None:
                payout_ratio = round(float(pay_raw)*100, 1) if float(pay_raw) <= 1 else round(float(pay_raw), 1)
            if eq_raw is not None:
                equity_ratio = round(float(eq_raw)*100, 1) if float(eq_raw) <= 1 else round(float(eq_raw), 1)
            name = info.get("longName") or info.get("shortName") or symbol
        except: pass
        ytd_high = ytd_low = ath = atl = None
        try:
            from datetime import date
            hist_max = ticker.history(period="max")[["High","Low"]]
            if not hist_max.empty:
                hist_max.index = pd.to_datetime(hist_max.index).tz_localize(None)
                year_start = pd.Timestamp(f"{date.today().year}-01-01")
                ytd = hist_max[hist_max.index >= year_start]
                if not ytd.empty:
                    ytd_high = round(float(ytd["High"].max()), 1)
                    ytd_low  = round(float(ytd["Low"].min()),  1)
                ath = round(float(hist_max["High"].max()), 1)
                atl = round(float(hist_max["Low"].min()),  1)
        except: pass
        peers_data = fetch_peers(symbol)
        scores = calc_score_detail({
            "trend_up": trend_up, "vol_ratio": vol_ratio, "per": per,
            "pbr": pbr, "div_yield": div_yield, "rev_yoy": rev_yoy,
            "op_yoy": op_yoy, "net_yoy": net_yoy, "relative5": relative5,
            "close": close, "pullback": pullback, "breakout_20": breakout_20,
        }, peers_data)
        return {
            "symbol": symbol, "name": name, "close": close,
            "ma5": ma5, "ma25": ma25, "ma75": ma75,
            "atr": atr, "pullback": pullback, "breakout_20": breakout_20,
            "score": scores["total"], "scores": scores,
            "trend_up": trend_up, "vol_ratio": vol_ratio, "vol_strength": vol_strength,
            "vol_days": vol_days, "per": per, "pbr": pbr, "roe": roe, "roa": roa,
            "div_yield": div_yield, "payout_ratio": payout_ratio, "equity_ratio": equity_ratio,
            "closes": closes, "last4": last4,
            "stock_ret5": stock_ret5, "nikkei_ret5": nikkei_ret5, "relative5": relative5,
            "rev_yoy": rev_yoy, "op_yoy": op_yoy, "net_yoy": net_yoy,
            "ytd_high": ytd_high, "ytd_low": ytd_low, "ath": ath, "atl": atl,
            "peers": peers_data,
        }
    except Exception as e:
        print(f"[ERROR] {symbol}: {e}")
        return None

def _yoy_str(v):
    return f"{v:+.1f}%" if v is not None else "N/A"

def _yoy_col(v):
    if v is None: return "#4a7090"
    return "#00ff9d" if v > 0 else "#ff4d6d"

def _mrow(lbl, val, col="#c8d6e5"):
    return (f'<div class="metric-row"><span class="metric-label">{lbl}</span>'
            f'<span class="metric-value" style="color:{col}">{val}</span></div>')

def _fmt(v, s):
    return f"{v}{s}" if v is not None else "N/A"

def build_detail_html(d):
    peers   = d["peers"]
    scores  = d["scores"]
    score   = scores["total"]
    state   = calc_state(d["trend_up"], d["vol_ratio"])
    verdict = calc_verdict(score)
    vr      = d["vol_ratio"] or 0.0

    state_colors   = {"強気": ("#00ff9d","#003322"), "中立": ("#ffd166","#2a2000"), "弱気": ("#ff4d6d","#2a0010")}
    verdict_colors = {"買い優勢": "#00ff9d", "様子見": "#ffd166", "見送り": "#ff4d6d"}
    state_color, state_bg = state_colors[state]
    verdict_color = verdict_colors[verdict]
    score_color   = "#00ff9d" if score >= 70 else ("#ffd166" if score >= 40 else "#ff4d6d")
    trend_color   = "#00ff9d" if d["trend_up"] else "#ff4d6d"
    trend_label   = "↑ 上昇トレンド" if d["trend_up"] else "↓ 下降トレンド"

    pullback = d["pullback"]
    breakout = d["breakout_20"]

    def _entry_col(diff):
        if diff is None: return "#4a7090"
        return "#00ff9d" if abs(diff) <= 2 else ("#ffd166" if abs(diff) <= 5 else "#ff4d6d")

    diff_pull  = round((d["close"]/pullback -1)*100, 1) if pullback and pullback > 0 else None
    diff_break = round((d["close"]/breakout -1)*100, 1) if breakout and breakout > 0 else None
    entry_pull_str  = f"¥{pullback:,.1f}（{diff_pull:+.1f}%）"  if diff_pull  is not None else "N/A"
    entry_break_str = f"¥{breakout:,.1f}（{diff_break:+.1f}%）" if diff_break is not None else "N/A"

    if diff_pull is not None and abs(diff_pull) <= 2:
        entry_label, entry_color = "押し目圏内", "#00ff9d"
    elif diff_break is not None and 0 <= diff_break <= 2:
        entry_label, entry_color = "ブレイク圏内", "#00ff9d"
    elif diff_pull is not None and diff_pull < 0:
        entry_label, entry_color = f"押し目まで {diff_pull:+.1f}%", "#ffd166"
    else:
        entry_label, entry_color = "待機", "#4a7090"

    growth_items = [("売上", d["rev_yoy"]), ("営業益", d["op_yoy"]), ("純利益", d["net_yoy"])]
    growth_available = [v for _,v in growth_items if v is not None]
    if growth_available:
        avg_growth = sum(growth_available)/len(growth_available)
        growth_label = f"成長 {avg_growth:+.1f}%"
        growth_color = _yoy_col(avg_growth)
    else:
        growth_label, growth_color = "業績 N/A", "#4a7090"

    rel5 = d["relative5"]
    rel5_col = "#00ff9d" if (rel5 and rel5 > 0) else "#ff4d6d"

    if state == "強気":
        strat_icon, strat_title = "📈", "押し目買い"
        strat_body = f"上昇トレンド＋出来高増が揃っている。<br>押し目（¥{pullback:,.0f}）付近でのエントリーを狙う。"
    elif vr >= BUY_VOL_RATIO:
        strat_icon, strat_title = "⚡", "ブレイク待ち"
        strat_body = "出来高は強いがトレンドが弱い。<br>MA25がMA75を上抜けるタイミングを待つ。"
    elif state == "中立":
        strat_icon, strat_title = "⏳", "様子見"
        strat_body = "出来高の回復を待つ。<br>トレンド継続を確認してからエントリー検討。"
    else:
        strat_icon, strat_title = "🚫", "見送り"
        strat_body = "下降トレンド継続中。<br>MA25がMA75を上回るまでポジションは持たない。"

    risks = []
    if not d["trend_up"]:
        risks.append(("⚠","#ff4d6d","下降トレンド継続","戻り売り圧力が続く可能性"))
    if vr < 1.0:
        risks.append(("⚠","#ff4d6d","出来高不足","買い圧力が弱く反発力に欠ける"))
    elif vr < BUY_VOL_RATIO:
        risks.append(("△","#ffd166","出来高平均水準","強い上昇には出来高増が必要"))
    if d["per"] and d["per"] > PRICEY_PER:
        risks.append(("△","#ffd166",f"PER {d['per']:.1f}倍 割高水準","業績悪化時の下落リスクが大きい"))
    if rel5 is not None and rel5 < -1.0:
        risks.append(("△","#ffd166",f"市場に劣後（{rel5:+.2f}%）","相対弱者は上昇しにくい"))
    if not risks:
        risks.append(("✓","#00ff9d","主要リスクなし","現時点でのリスク要因は確認されない"))
    risk_html = "".join(
        f'<div class="risk-item"><span style="color:{c};font-size:14px;margin-top:1px;flex-shrink:0">{ic}</span>'
        f'<div><div style="font-size:14px;font-weight:600;color:{c};margin-bottom:1px">{t}</div>'
        f'<div style="font-size:12px;color:#4a7090">{desc}</div></div></div>'
        for ic,c,t,desc in risks[:3]
    )

    spark = ""
    if d["closes"]:
        mn,mx = min(d["closes"]),max(d["closes"])
        rng   = mx-mn if mx!=mn else 1
        w,h   = 240,44
        pts   = [f"{i*w/(len(d['closes'])-1):.1f},{h-(v-mn)/rng*h:.1f}" for i,v in enumerate(d["closes"])]
        poly  = " ".join(pts)
        fill  = f"0,{h} {poly} {w},{h}"
        spark = (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
                 f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
                 f'<stop offset="0%" stop-color="#00d4ff" stop-opacity="0.3"/>'
                 f'<stop offset="100%" stop-color="#00d4ff" stop-opacity="0"/>'
                 f'</linearGradient></defs>'
                 f'<polygon points="{fill}" fill="url(#g)"/>'
                 f'<polyline points="{poly}" fill="none" stroke="#00d4ff" stroke-width="2"/>'
                 f'</svg>')

    def _per_c(v):  return "#4a7090" if v is None else ("#00ff9d" if v<15 else ("#ffd166" if v<25 else "#ff4d6d"))
    def _pbr_c(v):  return "#4a7090" if v is None else ("#00ff9d" if v<1  else ("#ffd166" if v<2  else "#ff4d6d"))
    def _roe_c(v):  return "#4a7090" if v is None else ("#00ff9d" if v>=15 else ("#ffd166" if v>=8 else "#ff4d6d"))
    def _roa_c(v):  return "#4a7090" if v is None else ("#00ff9d" if v>=5  else ("#ffd166" if v>=2 else "#ff4d6d"))
    def _div_c(v):  return "#4a7090" if v is None else ("#00ff9d" if v>=3  else ("#ffd166" if v>=1 else "#ff4d6d"))
    def _eq_c(v):   return "#4a7090" if v is None else ("#00ff9d" if v>=50 else ("#ffd166" if v>=30 else "#ff4d6d"))

    div_str = f"{d['div_yield']}%" if d["div_yield"] is not None else "N/A"
    if d.get("payout_ratio") is not None:
        div_str += f"（{d['payout_ratio']:.0f}%）"

    val_html = "".join(
        f'<div class="metric-row"><span class="metric-label">{lbl}</span>'
        f'<span class="metric-value" style="color:{col}">{val}</span></div>'
        for lbl,val,col in [
            ("PER",_fmt(d["per"],"倍"),_per_c(d["per"])),
            ("PBR",_fmt(d["pbr"],"倍"),_pbr_c(d["pbr"])),
            ("ROE",_fmt(d["roe"],"%"),_roe_c(d["roe"])),
            ("ROA",_fmt(d["roa"],"%"),_roa_c(d["roa"])),
            ("配当利回り",div_str,_div_c(d["div_yield"])),
            ("自己資本比率",_fmt(d.get("equity_ratio"),"%"),_eq_c(d.get("equity_ratio"))),
        ]
    )

    has_peers = peers["per_avg"] is not None or peers["roe_avg"] is not None
    if has_peers:
        per_diff = round(d["per"]-peers["per_avg"], 1) if d["per"] and peers["per_avg"] else None
        roe_diff = round(d["roe"]-peers["roe_avg"], 1) if d["roe"] and peers["roe_avg"] else None
        pp_col = "#00ff9d" if (per_diff and per_diff<0) else ("#ff4d6d" if (per_diff and per_diff>0) else "#4a7090")
        pr_col = "#00ff9d" if (roe_diff and roe_diff>0) else ("#ff4d6d" if (roe_diff and roe_diff<0) else "#4a7090")
        industry_html = (
            _mrow("PER 自社",    f"{d['per']:.1f}倍" if d["per"] else "N/A", pp_col) +
            _mrow("PER 業界平均", f"{peers['per_avg']:.1f}倍" if peers["per_avg"] else "N/A") +
            _mrow("ROE 自社",    f"{d['roe']:.1f}%" if d["roe"] else "N/A", pr_col) +
            _mrow("ROE 業界平均", f"{peers['roe_avg']:.1f}%" if peers["roe_avg"] else "N/A")
        )
    else:
        industry_html = '<div style="color:#4a7090;font-size:13px;padding:8px 0">業界比較データなし</div>'

    vs_color = {"強い流入":"#00ff9d","通常":"#ffd166","弱い":"#ff4d6d"}[d["vol_strength"]]
    day_labels = ["3日前→2日前","2日前→前日","前日→当日"]
    vol_day_html = ""
    for i,day in enumerate(d["vol_days"]):
        pa = "▲" if day["up"] else "▼"
        pc = "#00ff9d" if day["up"] else "#ff4d6d"
        vc = day["volume"]-day["vol_prev"]
        va = "▲" if vc>0 else "▼"
        vcc= "#00ff9d" if vc>0 else "#ff4d6d"
        vol_day_html += (
            f'<div class="vol-day-row">'
            f'<span class="metric-label">{day_labels[i]}</span>'
            f'<span style="color:{pc};font-weight:700">{pa} 株価</span>'
            f'<span>{day["volume"]:,}株</span>'
            f'<span style="color:{vcc};font-weight:600">{va} {abs(vc):,}</span>'
            f'</div>'
        )

    ma_diff = d["ma25"]-d["ma75"]
    st5_col = "#00ff9d" if (d["stock_ret5"] and d["stock_ret5"]>0) else "#ff4d6d"
    nk5_col = "#00ff9d" if (d["nikkei_ret5"] and d["nikkei_ret5"]>0) else "#ff4d6d"
    st5_str = f"{d['stock_ret5']:+.2f}%" if d["stock_ret5"] is not None else "N/A"
    nk5_str = f"{d['nikkei_ret5']:+.2f}%" if d["nikkei_ret5"] is not None else "N/A"
    rel5_str= f"{rel5:+.2f}%" if rel5 is not None else "N/A"

    def _ps(v): return f"¥{v:,.1f}" if v is not None else "N/A"
    def _dc(v,base):
        if v is None or base is None or base==0: return "#4a7090"
        pct=(base-v)/v*100
        return "#00ff9d" if pct>10 else ("#ffd166" if pct>3 else "#ff4d6d")

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{d['symbol']} — 投資判断</title>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0a0e1a;color:#c8d6e5;font-family:'Segoe UI',sans-serif;padding:8px 16px}}
  a.back{{display:inline-block;margin-bottom:10px;padding:5px 14px;background:#0d1b2e;border:1px solid #1e3a5f;border-radius:8px;color:#00d4ff;text-decoration:none;font-size:13px}}
  .container{{max-width:1400px;margin:0 auto;display:flex;flex-direction:column;gap:6px}}
  .header{{background:linear-gradient(135deg,#0d1b2e,#0a1628);border:1px solid #1e3a5f;border-radius:14px;padding:8px 16px;display:flex;align-items:center;justify-content:space-between;gap:16px}}
  .symbol{{font-size:12px;font-weight:600;letter-spacing:2px;color:#00d4ff}}
  .name{{font-size:18px;font-weight:700;color:#fff;margin:2px 0}}
  .price{{font-size:26px;font-weight:700;color:#fff}}
  .price span{{font-size:15px;color:#7a92ab;margin-right:4px}}
  .state-badge{{padding:6px 16px;border-radius:999px;font-size:16px;font-weight:700;color:{state_color};background:{state_bg};border:2px solid {state_color};box-shadow:0 0 14px {state_color}55;white-space:nowrap}}
  .card{{background:#0d1b2e;border:1px solid #1e3a5f;border-radius:12px;padding:8px 12px}}
  .card-label{{font-size:10px;font-weight:600;letter-spacing:2px;color:#4a7090;text-transform:uppercase;margin-bottom:4px}}
  .top-row{{display:grid;grid-template-columns:2fr 1fr;gap:6px}}
  .verdict-text{{font-size:22px;font-weight:700;color:{verdict_color};margin-bottom:2px}}
  .score-number{{font-size:34px;font-weight:700;color:{score_color};line-height:1;margin-bottom:2px}}
  .score-number span{{font-size:14px;color:#4a7090;margin-left:4px}}
  .gauge-bg{{background:#1a2a3a;border-radius:999px;height:5px;overflow:hidden;margin-bottom:4px}}
  .gauge-fill{{height:100%;width:{score}%;background:linear-gradient(90deg,{score_color}88,{score_color});border-radius:999px}}
  .sb-row{{display:flex;justify-content:space-between;font-size:13px;padding:1px 0;color:#4a6080}}
  .sb-row span:last-child{{font-weight:600;color:#8aa8c0}}
  .reason-stack{{display:flex;flex-direction:column;gap:5px}}
  .reason-card{{background:#0d1b2e;border:1px solid #1e3a5f;border-radius:12px;padding:7px 10px;flex:1}}
  .reason-main{{font-size:14px;font-weight:700;margin-bottom:2px}}
  .reason-sub{{font-size:12px;color:#4a7090;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .grid-4{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}}
  .grid-3{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}}
  .grid-2{{display:grid;grid-template-columns:repeat(2,1fr);gap:6px}}
  .metric-row{{display:flex;justify-content:space-between;align-items:center;padding:2px 0;border-bottom:1px solid #152030;font-size:13px}}
  .metric-row:last-child{{border-bottom:none}}
  .metric-label{{color:#4a7090}}
  .metric-value{{font-weight:600}}
  .vol-day-row{{display:grid;grid-template-columns:8em 3.5em 1fr 1fr;align-items:center;padding:2px 0;border-bottom:1px solid #152030;font-size:12px;gap:4px;white-space:nowrap}}
  .vol-day-row:last-child{{border-bottom:none}}
  .strat-title{{font-size:15px;font-weight:700;color:#00d4ff;margin:4px 0}}
  .strat-body{{font-size:13px;line-height:1.5;color:#8aa8c0}}
  .risk-item{{display:flex;gap:8px;align-items:flex-start;padding:4px 0;border-bottom:1px solid #152030}}
  .risk-item:last-child{{border-bottom:none}}
  .footer{{text-align:center;font-size:10px;color:#2a4060;padding-top:4px}}
</style>
</head>
<body>
<a href="index.html" class="back">← 一覧に戻る</a>
<div class="container">
  <div class="header">
    <div><div class="symbol">{d['symbol']}</div><div class="name">{d['name']}</div><div class="price"><span>¥</span>{d['close']:,.1f}</div></div>
    <div>{spark}</div>
    <div class="state-badge">{state}</div>
  </div>
  <div class="top-row">
    <div class="card">
      <div class="card-label">投資判断</div>
      <div class="verdict-text">{verdict}</div>
      <div class="score-number">{score}<span>/ 100</span></div>
      <div class="gauge-bg"><div class="gauge-fill"></div></div>
      <div style="border-top:1px solid #1a2a3a;padding-top:3px">
        <div class="sb-row"><span>トレンド</span><span>{scores['trend']}/25</span></div>
        <div class="sb-row"><span>出来高</span><span>{scores['volume']}/15</span></div>
        <div class="sb-row"><span>割安性</span><span>{scores['value']}/20</span></div>
        <div class="sb-row"><span>成長性</span><span>{scores['growth']}/15</span></div>
        <div class="sb-row"><span>市場</span><span>{scores['market']}/10</span></div>
        <div class="sb-row"><span>エントリー</span><span>{scores['entry']}/15</span></div>
      </div>
    </div>
    <div class="reason-stack">
      <div class="reason-card"><div style="font-size:13px">📊</div><div class="reason-main" style="color:{trend_color}">{trend_label}</div><div class="reason-sub">MA25 {d['ma25']:,.1f} / MA75 {d['ma75']:,.1f}</div></div>
      <div class="reason-card"><div style="font-size:13px">🎯</div><div class="reason-main" style="color:{entry_color}">{entry_label}</div><div class="reason-sub">押し目 {entry_pull_str} / ブレイク {entry_break_str}</div></div>
      <div class="reason-card"><div style="font-size:13px">📈</div><div class="reason-main" style="color:{growth_color}">{growth_label}</div><div class="reason-sub">{"  ".join(f"{lbl} {_yoy_str(v)}" for lbl,v in growth_items)}</div></div>
    </div>
  </div>
  <div class="grid-4">
    <div class="card"><div class="card-label">トレンド詳細</div>
      {_mrow("MA5",f"{d['ma5']:,.1f}")}{_mrow("MA25",f"{d['ma25']:,.1f}")}{_mrow("MA75",f"{d['ma75']:,.1f}")}{_mrow("MA差(25-75)",f"{ma_diff:+,.1f}",trend_color)}{_mrow("ATR(14)",f"{d['atr']:,.1f}","#7a92ab") if d["atr"] else ""}
    </div>
    <div class="card"><div class="card-label">市場比較（5日平均）</div>
      {_mrow("銘柄",st5_str,st5_col)}{_mrow("日経",nk5_str,nk5_col)}{_mrow("相対強度",rel5_str,rel5_col)}
    </div>
    <div class="card"><div class="card-label">価格レンジ</div>
      {_mrow("年初来高値",_ps(d["ytd_high"]),_dc(d["ytd_high"],d["close"]))}{_mrow("年初来安値",_ps(d["ytd_low"]),_dc(d["ytd_low"],d["close"]))}{_mrow("上場来高値",_ps(d["ath"]),_dc(d["ath"],d["close"]))}{_mrow("上場来安値",_ps(d["atl"]),_dc(d["atl"],d["close"]))}
    </div>
    <div class="card"><div class="card-label">業績モメンタム</div>
      {_mrow("売上 YoY",_yoy_str(d["rev_yoy"]),_yoy_col(d["rev_yoy"]))}{_mrow("営業利益 YoY",_yoy_str(d["op_yoy"]),_yoy_col(d["op_yoy"]))}{_mrow("純利益 YoY",_yoy_str(d["net_yoy"]),_yoy_col(d["net_yoy"]))}
    </div>
  </div>
  <div class="grid-3">
    <div class="card"><div class="card-label">Valuation</div>{val_html}</div>
    <div class="card"><div class="card-label">業界比較</div>{industry_html}</div>
    <div class="card"><div class="card-label">出来高分析（直近3日）</div>
      <div style="font-size:13px;font-weight:700;color:{vs_color};margin-bottom:3px">◆ {d['vol_strength']}</div>
      {vol_day_html}
    </div>
  </div>
  <div class="grid-2">
    <div class="card"><div style="font-size:17px;margin-bottom:3px">{strat_icon}</div><div class="strat-title">{strat_title}</div><div class="strat-body">{strat_body}</div></div>
    <div class="card"><div class="card-label">リスク</div>{risk_html}</div>
  </div>
  <div class="footer">generated automatically</div>
</div>
</body>
</html>"""

def build_index_html(results, all_count):
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    def sc(s): return "#00ff9d" if s >= 70 else ("#ffd166" if s >= 40 else "#ff4d6d")
    def verdict_label(s): return "買い優勢" if s >= 70 else ("様子見" if s >= 40 else "見送り")
    rows = ""
    for i, r in enumerate(results, 1):
        trend = "<span style='color:#00ff9d'>↑上昇</span>" if r["trend_up"] else "<span style='color:#ff4d6d'>↓下降</span>"
        per_s = f"{r['per']:.1f}倍" if r["per"] else "N/A"
        vr_s  = f"{r['vol_ratio']:.2f}x" if r["vol_ratio"] else "N/A"
        s     = r["score"]
        fname = r["symbol"].replace(".", "_") + ".html"
        medal = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}"))
        rows += f"""<tr onclick="location.href='{fname}'" style="cursor:pointer">
          <td style="text-align:center;font-size:16px">{medal}</td>
          <td>{r['symbol']}</td>
          <td>{r['name']}</td>
          <td>¥{r['close']:,.1f}</td>
          <td style='color:{sc(s)};font-weight:700'>{s}/100</td>
          <td style='color:{sc(s)}'>{verdict_label(s)}</td>
          <td>{trend}</td>
          <td>{vr_s}</td>
          <td>{per_s}</td>
        </tr>"""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>株価スキャナー結果</title>
<style>
  body{{background:#0a0e1a;color:#c8d6e5;font-family:'Segoe UI',sans-serif;padding:20px}}
  h1{{color:#00d4ff;font-size:22px;margin-bottom:4px}}
  .meta{{color:#4a7090;font-size:13px;margin-bottom:8px}}
  .hint{{color:#4a7090;font-size:11px;margin-bottom:16px}}
  table{{width:100%;border-collapse:collapse}}
  th{{background:#0d1b2e;color:#4a7090;font-size:11px;letter-spacing:1px;padding:10px;text-align:left;border-bottom:2px solid #1e3a5f}}
  td{{padding:10px;border-bottom:1px solid #152030;font-size:13px}}
  tr:hover td{{background:#0d1b2e}}
</style>
</head>
<body>
<h1>📈 株価スキャナー ランキング</h1>
<div class="meta">{now} ／ {all_count}銘柄 スコア順ランキング</div>
<div class="hint">※ 行をクリックすると詳細ダッシュボードが開きます</div>
<table>
  <thead><tr><th>順位</th><th>コード</th><th>銘柄名</th><th>株価</th><th>スコア</th><th>判断</th><th>トレンド</th><th>出来高比</th><th>PER</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
</body>
</html>"""

def main():
    with open("stocks.txt") as f:
        symbols = [line.strip() for line in f if line.strip()]
    print(f"スキャン開始: {len(symbols)}銘柄")
    all_results = []
    for symbol in symbols:
        print(f"  チェック中: {symbol}")
        r = analyze(symbol)
        if r:
            all_results.append(r)
            print(f"  ✅ {symbol} スコア{r['score']}")
        else:
            print(f"  ⬜ {symbol} 取得失敗")
    all_results.sort(key=lambda x: x["score"], reverse=True)
    os.makedirs("docs", exist_ok=True)
    for r in all_results:
        print(f"  詳細ページ生成: {r['symbol']}")
        html  = build_detail_html(r)
        fname = r["symbol"].replace(".", "_") + ".html"
        with open(f"docs/{fname}", "w", encoding="utf-8") as f:
            f.write(html)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(build_index_html(all_results, len(symbols)))
    print(f"完了: {len(all_results)}銘柄をランキング表示")

if __name__ == "__main__":
    main()
