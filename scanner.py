import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# ── 設定 ──────────────────────────────────────────────
SCORE_THRESHOLD = 60  # このスコア以上の銘柄だけ通知
BUY_VOL_RATIO   = 1.5
CHEAP_PER       = 15.0
PRICEY_PER      = 25.0

# ── スコア計算 ─────────────────────────────────────────
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

# ── 銘柄分析 ───────────────────────────────────────────
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
        try:
            info = ticker.info
            per  = info.get("trailingPE") or info.get("forwardPE")
            per  = round(float(per), 1) if per else None
            name = info.get("longName") or info.get("shortName") or symbol
        except:
            name = symbol

        score = calc_score(trend_up, vol_ratio, per)
        return {
            "symbol":    symbol,
            "name":      name,
            "close":     close,
            "score":     score,
            "trend_up":  trend_up,
            "vol_ratio": vol_ratio,
            "per":       per,
        }
    except Exception as e:
        print(f"[ERROR] {symbol}: {e}")
        return None

# ── メール送信 ─────────────────────────────────────────
def send_email(results):
    sender   = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_PASSWORD"]
    receiver = sender  # 自分宛

    subject = f"📈 本日の注目銘柄 {len(results)}件"

    body = "本日のスキャン結果（スコア60以上）\n"
    body += "=" * 40 + "\n\n"
    for r in results:
        trend = "↑上昇" if r["trend_up"] else "↓下降"
        per_s = f"{r['per']:.1f}倍" if r["per"] else "N/A"
        body += f"【{r['symbol']}】{r['name']}\n"
        body += f"  株価: ¥{r['close']:,.1f}\n"
        body += f"  スコア: {r['score']}/100\n"
        body += f"  トレンド: {trend}\n"
        body += f"  出来高比: {r['vol_ratio']:.2f}x\n"
        body += f"  PER: {per_s}\n\n"

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = receiver
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.send_message(msg)

    print(f"メール送信完了: {len(results)}件")

# ── メイン ─────────────────────────────────────────────
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

    if results:
        send_email(results)
    else:
        print("本日の注目銘柄なし")

if __name__ == "__main__":
    main()