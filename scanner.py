import yfinance as yf
import os
from datetime import datetime

SCORE_THRESHOLD = 60
BUY_VOL_RATIO   = 1.5
CHEAP_PER       = 15.0
PRICEY_PER      = 25.0

PEERS = {
    "7203.T": ["7267.T", "7201.T", "7269.T"],
    "7267.T": ["7203.T", "7201.T", "7269.T"],
    "6758.T": ["6752.T", "6753.T", "6971.T"],
    "8306.T": ["8316.T", "8411.T"],
    "8316.T": ["8306.T", "8411.T"],
    "8411.T": ["8306.T", "8316.T"],
    "9984.T": ["9983.T", "4755.T", "3659.T"],
    "9432.T": ["9433.T", "9434.T"],
    "9433.T": ["9432.T", "9434.T"],
    "4063.T": ["4005.T", "3407.T", "4183.T"],
    "4568.T": ["4519.T", "4507.T"],
    "8001.T": ["8002.T", "8031.T", "8058.T"],
    "8002.T": ["8001.T", "8031.T", "8058.T"],
    "8031.T": ["8001.T", "8002.T", "8058.T"],
    "8058.T": ["8001.T", "8002.T", "8031.T"],
}

def calc_score(trend_up, vol_ratio, per):
    score = 0
    vr = vol_ratio or 0.0
    score += 40 if trend_up else 0
    if vr >= 2.0:    score += 30
    elif vr >= 1.5:  score += 22
    elif vr >= 1.0:  score += 12
    if per is None:          score += 0
    elif per < CHEAP_PER:    score += 30
    elif per < PRICEY_PER:   score += 15
    return min(score, 100)

def calc_state(trend_up, vol_ratio):
    vr = vol_ratio or 0.0
    if trend_up and vr >= BUY_VOL_RATIO:  return "強気"
    elif trend_up or vr >= 1.0:           return "中立"
    else:                                  return "弱気"

def calc_verdict(state, per):
    if state == "強気":  return "買い優勢"
    elif state == "中立": return "買い優勢" if (per and per < CHEAP_PER) else "様子見"
    else:                 return "見送り"

def analyze(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period="6mo")
        if hist.empty or len(hist) < 75:
            return None
        df = hist[["Close", "Volume"]].copy()
        df["ma5"]       = df["Close"].rolling(5).mean()
        df["ma25"]      = df["Close"].rolling(25).mean()
        df["ma75"]      = df["Close"].rolling(75).mean()
        df["vol_avg20"] = df["Volume"].rolling(20).mean()
        latest    = df.iloc[-1]
        close     = round(float(latest["Close"]), 1)
        ma5       = round(float(latest["ma5"]),   1)
        ma25      = round(float(latest["ma25"]),  1)
        ma75      = round(float(latest["ma75"]),  1)
        vol_avg20 = float(latest["vol_avg20"])
        vol_ratio = round(float(latest["Volume"]) / vol_avg20, 2) if vol_avg20 > 0 else None
        trend_up  = bool(ma25 > ma75)
        closes    = df["Close"].tail(20).round(1).tolist()
        last4     = df["Close"].tail(4).round(1).tolist()

        # 出来高トレンド
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
        if up_with_vol >= 2:    vol_strength = "強い流入"
        elif down_with_vol >= 2: vol_strength = "弱い"
        else:                    vol_strength = "通常"

        # 市場比較
        nikkei_ret = stock_ret = relative = None
        try:
            nk = yf.Ticker("^N225").history(period="5d")
            if len(nk) >= 2:
                nikkei_ret = round((nk["Close"].iloc[-1] / nk["Close"].iloc[-2] - 1) * 100, 2)
            prev_close = df["Close"].iloc[-2] if len(df) >= 2 else None
            if prev_close and float(prev_close) != 0:
                stock_ret = round((close / float(prev_close) - 1) * 100, 2)
            if nikkei_ret is not None and stock_ret is not None:
                relative = round(stock_ret - nikkei_ret, 2)
        except: pass

        # ファンダメンタル
        per = pbr = roe = roa = div_yield = None
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
            roe = round(float(roe_raw)*100, 1) if roe_raw else None
            roa = round(float(roa_raw)*100, 1) if roa_raw else None
            if div_raw is not None:
                div_yield = round(float(div_raw)*100, 1) if float(div_raw) < 1 else round(float(div_raw), 1)
            name = info.get("longName") or info.get("shortName") or symbol
        except: pass

        # 年初来・上場来
        ytd_high = ytd_low = ath = atl = None
        try:
            from datetime import date
            import pandas as pd
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

        score = calc_score(trend_up, vol_ratio, per)
        return {
            "symbol": symbol, "name": name, "close": close,
            "ma5": ma5, "ma25": ma25, "ma75": ma75,
            "score": score, "trend_up": trend_up,
            "vol_ratio": vol_ratio, "vol_strength": vol_strength,
            "vol_days": vol_days,
            "per": per, "pbr": pbr, "roe": roe, "roa": roa,
            "div_yield": div_yield, "closes": closes, "last4": last4,
            "nikkei_ret": nikkei_ret, "stock_ret": stock_ret, "relative": relative,
            "ytd_high": ytd_high, "ytd_low": ytd_low, "ath": ath, "atl": atl,
        }
    except Exception as e:
        print(f"[ERROR] {symbol}: {e}")
        return None

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

def build_detail_html(d, peers):
    state   = calc_state(d["trend_up"], d["vol_ratio"])
    verdict = calc_verdict(state, d["per"])
    score   = d["score"]
    vr      = d["vol_ratio"] or 0.0

    state_colors   = {"強気": ("#00ff9d","#003322"), "中立": ("#ffd166","#2a2000"), "弱気": ("#ff4d6d","#2a0010")}
    verdict_colors = {"買い優勢": "#00ff9d", "様子見": "#ffd166", "見送り": "#ff4d6d"}
    state_color, state_bg = state_colors[state]
    verdict_color = verdict_colors[verdict]
    score_color   = "#00ff9d" if score >= 70 else ("#ffd166" if score >= 40 else "#ff4d6d")
    trend_color   = "#00ff9d" if d["trend_up"] else "#ff4d6d"
    trend_label   = "↑ 上昇トレンド" if d["trend_up"] else "↓ 下降トレンド"

    rel       = d["relative"]
    rel_color = "#00ff9d" if (rel and rel > 0) else "#ff4d6d"
    rel_main  = f"市場比 {rel:+.2f}%" if rel is not None else "市場比 N/A"
    nk_str    = f"{d['nikkei_ret']:+.2f}%" if d["nikkei_ret"] is not None else "N/A"
    st_str    = f"{d['stock_ret']:+.2f}%" if d["stock_ret"] is not None else "N/A"

    per_str   = f"{d['per']:.1f}倍" if d["per"] else "N/A"
    per_color = "#00ff9d" if (d["per"] and d["per"] < CHEAP_PER) else ("#ffd166" if (d["per"] and d["per"] < PRICEY_PER) else "#ff4d6d")
    per_sub   = "割安" if (d["per"] and d["per"] < CHEAP_PER) else ("適正" if (d["per"] and d["per"] < PRICEY_PER) else ("割高" if d["per"] else "取得不可"))

    snap_trend = "🟢 上昇トレンド" if d["trend_up"] else "🔴 下降トレンド"
    snap_vol   = "🟢 出来高強" if d["vol_strength"]=="強い流入" else ("🟡 出来高普通" if d["vol_strength"]=="通常" else "🔴 出来高弱")
    snap_val   = "🟢 割安" if (d["per"] and d["per"]<CHEAP_PER) else ("🟡 適正" if (d["per"] and d["per"]<PRICEY_PER) else "🔴 割高")

    if state == "強気":
        strat_icon, strat_title = "📈", "押し目買い"
        strat_body = f"上昇トレンド＋出来高増が揃っている。<br>MA25（¥{d['ma25']:,.0f}）付近の押し目を狙う。"
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
        risks.append(("△","#ffd166",f"PER {d['per']:.1f}x 割高水準","業績悪化時の下落リスクが大きい"))
    if not risks:
        risks.append(("✓","#00ff9d","主要リスクなし","現時点でのリスク要因は確認されない"))
    risk_html = "".join(
        f'<div class="risk-item"><span class="risk-icon" style="color:{c}">{ic}</span>'
        f'<div><div class="risk-title" style="color:{c}">{t}</div>'
        f'<div class="risk-desc">{desc}</div></div></div>'
        for ic,c,t,desc in risks[:3]
    )

    spark = ""
    if d["closes"]:
        mn,mx = min(d["closes"]),max(d["closes"])
        rng   = mx-mn if mx!=mn else 1
        w,h   = 280,60
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

    def _mrow(lbl,val,col="#c8d6e5"):
        return (f'<div class="metric-row"><span class="metric-label">{lbl}</span>'
                f'<span class="metric-value" style="color:{col}">{val}</span></div>')

    def _fmt(v,s): return f"{v}{s}" if v is not None else "N/A"
    def _per_c(v):  return "#4a7090" if v is None else ("#00ff9d" if v<15 else ("#ffd166" if v<25 else "#ff4d6d"))
    def _pbr_c(v):  return "#4a7090" if v is None else ("#00ff9d" if v<1  else ("#ffd166" if v<2  else "#ff4d6d"))
    def _roe_c(v):  return "#4a7090" if v is None else ("#00ff9d" if v>=15 else ("#ffd166" if v>=8 else "#ff4d6d"))
    def _roa_c(v):  return "#4a7090" if v is None else ("#00ff9d" if v>=5  else ("#ffd166" if v>=2 else "#ff4d6d"))
    def _div_c(v):  return "#4a7090" if v is None else ("#00ff9d" if v>=3  else ("#ffd166" if v>=1 else "#ff4d6d"))

    val_html = "".join(
        f'<div class="metric-row"><span class="metric-label">{lbl}</span>'
        f'<span class="metric-value" style="color:{col}">{val}</span></div>'
        for lbl,val,col in [
            ("PER",_fmt(d["per"],"倍"),_per_c(d["per"])),
            ("PBR",_fmt(d["pbr"],"倍"),_pbr_c(d["pbr"])),
            ("ROE",_fmt(d["roe"],"%"),_roe_c(d["roe"])),
            ("ROA",_fmt(d["roa"],"%"),_roa_c(d["roa"])),
            ("配当利回り",_fmt(d["div_yield"],"%"),_div_c(d["div_yield"])),
        ]
    )

    last4_labels = ["3日前","2日前","前日","当日"]
    last4_html = ""
    for i,(label,price) in enumerate(zip(last4_labels, d["last4"])):
        if i == 0:
            chg_html = ""
        else:
            prev = d["last4"][i-1]
            chg  = price - prev
            pct  = chg/prev*100 if prev else 0
            col  = "#00ff9d" if chg>0 else ("#ff4d6d" if chg<0 else "#4a7090")
            sign = "+" if chg>=0 else ""
            chg_html = f'<span style="color:{col};font-size:12px;margin-left:8px">{sign}{chg:,.1f}（{sign}{pct:.2f}%）</span>'
        last4_html += (f'<div class="metric-row"><span class="metric-label">{label}</span>'
                       f'<span class="metric-value">¥{price:,.1f}{chg_html}</span></div>')

    ma_diff = d["ma25"] - d["ma75"]
    st_ret_col = "#00ff9d" if (d["stock_ret"] and d["stock_ret"]>0) else "#ff4d6d"
    nk_ret_col = "#00ff9d" if (d["nikkei_ret"] and d["nikkei_ret"]>0) else "#ff4d6d"
    trend_card = (_mrow("MA5",f"{d['ma5']:,.1f}") + _mrow("MA25",f"{d['ma25']:,.1f}") +
                  _mrow("MA75",f"{d['ma75']:,.1f}") + _mrow("MA差(25-75)",f"{ma_diff:+,.1f}",trend_color))
    market_card = (_mrow("銘柄前日比",st_str,st_ret_col) + _mrow("日経前日比",nk_str,nk_ret_col) +
                   _mrow("相対強度",f"{d['relative']:+.2f}%" if d["relative"] is not None else "N/A",rel_color))

    def _ps(v): return f"¥{v:,.1f}" if v is not None else "N/A"
    def _dc(v,base):
        if v is None or base is None or base==0: return "#4a7090"
        pct=(base-v)/v*100
        return "#00ff9d" if pct>10 else ("#ffd166" if pct>3 else "#ff4d6d")
    range_card = (_mrow("年初来高値",_ps(d["ytd_high"]),_dc(d["ytd_high"],d["close"])) +
                  _mrow("年初来安値",_ps(d["ytd_low"]),_dc(d["ytd_low"],d["close"])) +
                  _mrow("上場来高値",_ps(d["ath"]),_dc(d["ath"],d["close"])) +
                  _mrow("上場来安値",_ps(d["atl"]),_dc(d["atl"],d["close"])))

    has_peers = peers["per_avg"] is not None or peers["roe_avg"] is not None
    if has_peers:
        pp_col = "#00ff9d" if (d["per"] and peers["per_avg"] and d["per"]<peers["per_avg"]) else "#ff4d6d"
        pr_col = "#00ff9d" if (d["roe"] and peers["roe_avg"] and d["roe"]>peers["roe_avg"]) else "#ff4d6d"
        industry_html = (
            _mrow("PER（自社）",per_str,pp_col) +
            _mrow("PER（業界平均）",f"{peers['per_avg']:.1f}倍" if peers["per_avg"] else "N/A") +
            _mrow("ROE（自社）",_fmt(d["roe"],"%"),pr_col) +
            _mrow("ROE（業界平均）",f"{peers['roe_avg']:.1f}%" if peers["roe_avg"] else "N/A")
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
        vol_day_html += (f'<div class="vol-day-row"><span class="metric-label">{day_labels[i]}</span>'
                         f'<span style="color:{pc};font-weight:700">{pa} 株価</span>'
                         f'<span>{day["volume"]:,}株</span>'
                         f'<span style="color:{vcc};font-weight:600">{va} {abs(vc):,}</span></div>')

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{d['symbol']} — 投資判断</title>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0a0e1a;color:#c8d6e5;font-family:'Segoe UI',sans-serif;min-height:100vh;padding:12px 20px}}
  .back-btn{{display:inline-block;margin-bottom:12px;padding:6px 14px;background:#0d1b2e;border:1px solid #1e3a5f;border-radius:8px;color:#00d4ff;text-decoration:none;font-size:13px}}
  .back-btn:hover{{background:#1e3a5f}}
  .container{{max-width:1400px;margin:0 auto;display:flex;flex-direction:column;gap:7px}}
  .snapshot{{background:#0d1b2e;border:1px solid #1e3a5f;border-radius:10px;padding:7px 16px;font-size:12px;font-weight:600;color:#c8d6e5;text-align:center}}
  .header{{background:linear-gradient(135deg,#0d1b2e,#0a1628);border:1px solid #1e3a5f;border-radius:14px;padding:12px 18px;display:flex;align-items:center;justify-content:space-between;gap:16px}}
  .symbol{{font-size:12px;font-weight:600;letter-spacing:2px;color:#00d4ff}}
  .name{{font-size:18px;font-weight:700;color:#fff;margin:2px 0 6px}}
  .price{{font-size:28px;font-weight:700;color:#fff}}
  .price span{{font-size:16px;color:#7a92ab;margin-right:4px}}
  .state-badge{{padding:6px 16px;border-radius:999px;font-size:16px;font-weight:700;color:{state_color};background:{state_bg};border:2px solid {state_color};box-shadow:0 0 14px {state_color}55;white-space:nowrap}}
  .card{{background:#0d1b2e;border:1px solid #1e3a5f;border-radius:12px;padding:10px 14px}}
  .card-label{{font-size:10px;font-weight:600;letter-spacing:2px;color:#4a7090;text-transform:uppercase;margin-bottom:6px}}
  .verdict-row{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
  .verdict-text{{font-size:24px;font-weight:700;color:{verdict_color};text-shadow:0 0 10px {verdict_color}88}}
  .score-number{{font-size:26px;font-weight:700;color:{score_color};margin-bottom:8px}}
  .score-number span{{font-size:14px;color:#4a7090}}
  .gauge-bg{{background:#1a2a3a;border-radius:999px;height:8px;overflow:hidden}}
  .gauge-fill{{height:100%;width:{score}%;background:linear-gradient(90deg,{score_color}88,{score_color});border-radius:999px}}
  .reasons{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
  .reason-card{{background:#0d1b2e;border:1px solid #1e3a5f;border-radius:12px;padding:10px 14px}}
  .reason-main{{font-size:14px;font-weight:700;margin-bottom:2px}}
  .reason-sub{{font-size:11px;color:#4a7090}}
  .grid-4{{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}}
  .grid-3{{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}}
  .metric-row{{display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid #152030;font-size:11px}}
  .metric-row:last-child{{border-bottom:none}}
  .metric-label{{color:#4a7090}}
  .metric-value{{font-weight:600}}
  .vol-day-row{{display:grid;grid-template-columns:8em 3.5em 1fr 1fr;align-items:center;padding:3px 0;border-bottom:1px solid #152030;font-size:10px;gap:4px}}
  .vol-day-row:last-child{{border-bottom:none}}
  .strat-icon{{font-size:18px;margin-bottom:4px}}
  .strat-title{{font-size:15px;font-weight:700;color:#00d4ff;margin-bottom:5px}}
  .strat-body{{font-size:11px;line-height:1.6;color:#8aa8c0}}
  .risk-item{{display:flex;gap:8px;align-items:flex-start;padding:5px 0;border-bottom:1px solid #152030}}
  .risk-item:last-child{{border-bottom:none}}
  .risk-title{{font-size:12px;font-weight:600;margin-bottom:2px}}
  .risk-desc{{font-size:10px;color:#4a7090}}
  .footer{{text-align:center;font-size:10px;color:#2a4060;padding-top:4px}}
</style>
</head>
<body>
<a href="index.html" class="back-btn">← 一覧に戻る</a>
<div class="container">
  <div class="snapshot">{snap_trend}  ×  {snap_vol}  ×  {snap_val}</div>
  <div class="header">
    <div>
      <div class="symbol">{d['symbol']}</div>
      <div class="name">{d['name']}</div>
      <div class="price"><span>¥</span>{d['close']:,.1f}</div>
    </div>
    <div>{spark}</div>
    <div class="state-badge">{state}</div>
  </div>
  <div class="verdict-row">
    <div class="card"><div class="card-label">投資判断</div><div class="verdict-text">{verdict}</div></div>
    <div class="card"><div class="card-label">総合スコア</div><div class="score-number">{score}<span> / 100</span></div><div class="gauge-bg"><div class="gauge-fill"></div></div></div>
  </div>
  <div class="reasons">
    <div class="reason-card"><div>📊</div><div class="reason-main" style="color:{trend_color}">{trend_label}</div><div class="reason-sub">MA25 {d['ma25']:,.1f} / MA75 {d['ma75']:,.1f}</div></div>
    <div class="reason-card"><div>🌐</div><div class="reason-main" style="color:{rel_color}">{rel_main}</div><div class="reason-sub">日経 {nk_str} / 銘柄 {st_str}</div></div>
    <div class="reason-card"><div>💰</div><div class="reason-main" style="color:{per_color}">PER {per_str}</div><div class="reason-sub">{per_sub}</div></div>
  </div>
  <div class="grid-4">
    <div class="card"><div class="card-label">トレンド詳細</div>{trend_card}</div>
    <div class="card"><div class="card-label">市場比較</div>{market_card}</div>
    <div class="card"><div class="card-label">価格レンジ</div>{range_card}</div>
    <div class="card"><div class="card-label">直近終値</div>{last4_html}</div>
  </div>
  <div class="grid-3">
    <div class="card"><div class="card-label">Valuation</div>{val_html}</div>
    <div class="card"><div class="card-label">業界比較</div>{industry_html}</div>
    <div class="card"><div class="card-label">出来高分析（直近3日）</div>
      <div style="font-size:13px;font-weight:700;color:{vs_color};margin-bottom:5px">◆ {d['vol_strength']}</div>
      {vol_day_html}
    </div>
  </div>
  <div class="grid-3">
    <div class="card"><div class="strat-icon">{strat_icon}</div><div class="strat-title">{strat_title}</div><div class="strat-body">{strat_body}</div></div>
    <div class="card"><div class="card-label">リスク</div>{risk_html}</div>
  </div>
  <div class="footer">generated automatically</div>
</div>
</body>
</html>"""

def build_index_html(results, all_count):
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    score_color = lambda s: "#00ff9d" if s >= 70 else ("#ffd166" if s >= 40 else "#ff4d6d")
    rows = ""
    for r in results:
        trend = "<span style='color:#00ff9d'>↑上昇</span>" if r["trend_up"] else "<span style='color:#ff4d6d'>↓下降</span>"
        per_s = f"{r['per']:.1f}倍" if r["per"] else "N/A"
        vr_s  = f"{r['vol_ratio']:.2f}x" if r["vol_ratio"] else "N/A"
        sc    = r["score"]
        fname = r["symbol"].replace(".", "_") + ".html"
        rows += f"""<tr onclick="location.href='{fname}'" style="cursor:pointer">
          <td>{r['symbol']}</td>
          <td>{r['name']}</td>
          <td>¥{r['close']:,.1f}</td>
          <td style='color:{score_color(sc)};font-weight:700'>{sc}/100</td>
          <td>{trend}</td>
          <td>{vr_s}</td>
          <td>{per_s}</td>
        </tr>"""

    no_result = "" if results else "<tr><td colspan='7' style='text-align:center;color:#4a7090;padding:40px'>本日の注目銘柄はありません</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>株価スキャナー結果</title>
<style>
  body{{background:#0a0e1a;color:#c8d6e5;font-family:'Segoe UI',sans-serif;padding:20px}}
  h1{{color:#00d4ff;font-size:22px;margin-bottom:4px}}
  .meta{{color:#4a7090;font-size:13px;margin-bottom:20px}}
  table{{width:100%;border-collapse:collapse}}
  th{{background:#0d1b2e;color:#4a7090;font-size:11px;letter-spacing:1px;padding:10px;text-align:left;border-bottom:2px solid #1e3a5f}}
  td{{padding:10px;border-bottom:1px solid #152030;font-size:13px}}
  tr:hover td{{background:#0d1b2e}}
  .hint{{color:#4a7090;font-size:11px;margin-bottom:12px}}
</style>
</head>
<body>
<h1>📈 株価スキャナー結果</h1>
<div class="meta">{now} ／ スキャン {all_count}銘柄 → 注目 {len(results)}銘柄（スコア{SCORE_THRESHOLD}以上）</div>
<div class="hint">※ 行をクリックすると詳細ダッシュボードが開きます</div>
<table>
  <thead><tr><th>コード</th><th>銘柄名</th><th>株価</th><th>スコア</th><th>トレンド</th><th>出来高比</th><th>PER</th></tr></thead>
  <tbody>{rows}{no_result}</tbody>
</table>
</body>
</html>"""

def main():
    with open("stocks.txt") as f:
        symbols = [line.strip() for line in f if line.strip()]

    print(f"スキャン開始: {len(symbols)}銘柄")
    results = []
    for symbol in symbols:
        print(f"  チェック中: {symbol}")
        r = analyze(symbol)
        if r and r["score"] >= SCORE_THRESHOLD:
            results.append(r)
            print(f"  ✅ {symbol} スコア{r['score']}")
        else:
            print(f"  ⬜ {symbol} 対象外")

    results.sort(key=lambda x: x["score"], reverse=True)
    os.makedirs("docs", exist_ok=True)

    # 詳細ページ生成
    for r in results:
        print(f"  詳細ページ生成: {r['symbol']}")
        peers = fetch_peers(r["symbol"])
        html  = build_detail_html(r, peers)
        fname = r["symbol"].replace(".", "_") + ".html"
        with open(f"docs/{fname}", "w", encoding="utf-8") as f:
            f.write(html)

    # 一覧ページ生成
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(build_index_html(results, len(symbols)))

    print(f"完了: 一覧+{len(results)}件の詳細ページを生成")

if __name__ == "__main__":
    main()
