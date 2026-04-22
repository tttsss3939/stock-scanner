import yfinance as yf
import os
from datetime import datetime

SCORE_THRESHOLD = 60
BUY_VOL_RATIO   = 1.5
CHEAP_PER       = 15.0
PRICEY_PER      = 25.0

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

def analyze(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period="6mo")
        if hist.empty or len(hist) < 75:
            return None
        df = hist[["Close", "Volume"]].copy()
        df["ma25"]      = df["Close"].rolling(25).mean()
        df["ma75"]      = df["Close"].rolling(75).mean()
        df["vol_avg20"] = df["Volume"].rolling(20).mean()
        latest    = df.iloc[-1]
        close     = round(float(latest["Close"]), 1)
        ma25      = round(float(latest["ma25"]),  1)
        ma75      = round(float(latest["ma75"]),  1)
        vol_avg20 = float(latest["vol_avg20"])
        vol_ratio = round(float(latest["Volume"]) / vol_avg20, 2) if vol_avg20 > 0 else None
        trend_up  = bool(ma25 > ma75)
        per = None
        name = symbol
        try:
            info = ticker.info
            per  = info.get("trailingPE") or info.get("forwardPE")
            per  = round(float(per), 1) if per else None
            name = info.get("longName") or info.get("shortName") or symbol
        except:
            pass
        score = calc_score(trend_up, vol_ratio, per)
        return {
            "symbol": symbol, "name": name, "close": close,
            "score": score, "trend_up": trend_up,
            "vol_ratio": vol_ratio, "per": per,
        }
    except Exception as e:
        print(f"[ERROR] {symbol}: {e}")
        return None

def build_html(results, total):
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    score_color = lambda s: "#00ff9d" if s >= 70 else ("#ffd166" if s >= 40 else "#ff4d6d")

    rows = ""
    for r in results:
        trend  = "<span style='color:#00ff9d'>↑上昇</span>" if r["trend_up"] else "<span style='color:#ff4d6d'>↓下降</span>"
        per_s  = f"{r['per']:.1f}倍" if r["per"] else "N/A"
        vr_s   = f"{r['vol_ratio']:.2f}x" if r["vol_ratio"] else "N/A"
        sc     = r["score"]
        sc_col = score_color(sc)
        rows += f"""
        <tr>
          <td>{r['symbol']}</td>
          <td>{r['name']}</td>
          <td>¥{r['close']:,.1f}</td>
          <td style='color:{sc_col};font-weight:700'>{sc}/100</td>
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
  body {{ background:#0a0e1a; color:#c8d6e5; font-family:'Segoe UI',sans-serif; padding:20px; }}
  h1 {{ color:#00d4ff; font-size:22px; margin-bottom:4px; }}
  .meta {{ color:#4a7090; font-size:13px; margin-bottom:20px; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ background:#0d1b2e; color:#4a7090; font-size:11px; letter-spacing:1px; padding:10px; text-align:left; border-bottom:2px solid #1e3a5f; }}
  td {{ padding:10px 10px; border-bottom:1px solid #152030; font-size:13px; }}
  tr:hover td {{ background:#0d1b2e; }}
</style>
</head>
<body>
<h1>📈 株価スキャナー結果</h1>
<div class="meta">{now} ／ スキャン {total}銘柄 → 注目 {len(results)}銘柄（スコア{SCORE_THRESHOLD}以上）</div>
<table>
  <thead>
    <tr><th>コード</th><th>銘柄名</th><th>株価</th><th>スコア</th><th>トレンド</th><th>出来高比</th><th>PER</th></tr>
  </thead>
  <tbody>
    {rows}{no_result}
  </tbody>
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
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(build_html(results, len(symbols)))
    print(f"HTML生成完了: docs/index.html")

if __name__ == "__main__":
    main()
