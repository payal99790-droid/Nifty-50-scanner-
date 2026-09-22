"""
Nifty 50 intraday scanner.

Fetches live quotes for the Nifty 50 constituents from NSE (via nsepython),
scores each stock on gap-from-prev-close, move-from-open, and position within
the day's range, and writes a ranked long/short candidate list to an HTML
file (docs/index.html) that can be published as a static page (e.g. GitHub
Pages) and viewed on a phone.

This script is READ-ONLY: it never places orders. It is a market-reading
aid, not a trade recommendation or an automated trading system.
"""

import datetime
import json
import time
import traceback

from nsepython import nse_eq

# --- Nifty 50 constituent list (update if NSE reconstitutes the index) ---
NIFTY50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "ITC", "INDUSINDBK", "INFY",
    "JSWSTEEL", "JIOFIN", "KOTAKBANK", "LT", "M&M",
    "MARUTI", "NTPC", "NESTLEIND", "ONGC", "POWERGRID",
    "RELIANCE", "SBILIFE", "SHRIRAMFIN", "SBIN", "SUNPHARMA",
    "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TECHM",
    "TITAN", "TRENT", "ULTRACEMCO", "WIPRO", "INDIGO",
]

REQUEST_DELAY_SECONDS = 0.4  # be polite to NSE's endpoint


def fetch_quote(symbol):
    """Fetch one symbol's quote from NSE. Returns a plain dict or None on failure."""
    try:
        data = nse_eq(symbol)
        price_info = data.get("priceInfo", {})
        open_price = price_info.get("open")
        prev_close = price_info.get("previousClose")
        ltp = price_info.get("lastPrice")
        day_high = price_info.get("intraDayHighLow", {}).get("max")
        day_low = price_info.get("intraDayHighLow", {}).get("min")

        if not all([open_price, prev_close, ltp, day_high, day_low]):
            return None

        gap_pct = (open_price / prev_close - 1) * 100
        from_open_pct = (ltp / open_price - 1) * 100
        change_pct = (ltp / prev_close - 1) * 100
        rng = day_high - day_low
        pos_in_range = ((ltp - day_low) / rng * 100) if rng > 0 else 50.0

        return {
            "symbol": symbol,
            "open": open_price,
            "prev_close": prev_close,
            "ltp": ltp,
            "day_high": day_high,
            "day_low": day_low,
            "gap_pct": round(gap_pct, 2),
            "from_open_pct": round(from_open_pct, 2),
            "change_pct": round(change_pct, 2),
            "pos_in_range": round(pos_in_range, 1),
        }
    except Exception:
        return None


def fetch_all():
    rows = []
    for sym in NIFTY50:
        row = fetch_quote(sym)
        if row:
            rows.append(row)
        time.sleep(REQUEST_DELAY_SECONDS)
    return rows


def score_and_rank(rows):
    """
    Score = combination of move-from-open and position-in-range.
    Longs: positive move from open AND near the day's high (trend continuing).
    Shorts: negative move from open AND near the day's low (trend continuing).
    """
    longs = [r for r in rows if r["from_open_pct"] > 0]
    shorts = [r for r in rows if r["from_open_pct"] < 0]

    for r in longs:
        r["score"] = r["from_open_pct"] + (r["pos_in_range"] - 50) / 20
    for r in shorts:
        r["score"] = -r["from_open_pct"] + (50 - r["pos_in_range"]) / 20

    longs.sort(key=lambda r: r["score"], reverse=True)
    shorts.sort(key=lambda r: r["score"], reverse=True)

    return longs[:8], shorts[:8]


def render_html(longs, shorts, all_rows, timestamp):
    advances = sum(1 for r in all_rows if r["change_pct"] > 0)
    declines = sum(1 for r in all_rows if r["change_pct"] < 0)

    def row_html(r, side):
        cls = "pos" if side == "long" else "neg"
        return f"""
        <tr>
          <td>{r['symbol']}</td>
          <td>{r['ltp']}</td>
          <td class="{cls}">{r['change_pct']:+.2f}%</td>
          <td>{r['from_open_pct']:+.2f}%</td>
          <td>{r['pos_in_range']:.0f}%</td>
        </tr>"""

    long_rows = "".join(row_html(r, "long") for r in longs) or "<tr><td colspan=5>None</td></tr>"
    short_rows = "".join(row_html(r, "short") for r in shorts) or "<tr><td colspan=5>None</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Nifty 50 Scanner</title>
<style>
  :root {{
    --bg: #0f1115; --card: #171a21; --text: #e8e8ea; --muted: #9aa0aa;
    --pos: #26a65b; --neg: #e5484d; --border: #2a2e37;
    box-sizing: border-box;
    padding-top: env(safe-area-inset-top, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }}
  @media (prefers-color-scheme: light) {{
    :root:not([data-theme="dark"]) {{
      --bg: #f5f6f8; --card: #ffffff; --text: #1a1c22; --muted: #666c78; --border: #e2e4e8;
    }}
  }}
  html {{ scroll-padding-top: env(safe-area-inset-top, 0px); }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 16px;
  }}
  h1 {{ font-size: 1.3rem; margin: 0 0 4px; }}
  .meta {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 16px; }}
  .breadth {{ display: flex; gap: 12px; margin-bottom: 16px; }}
  .pill {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 8px 14px; font-size: 0.9rem;
  }}
  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    padding: 14px; margin-bottom: 16px; overflow-x: auto;
  }}
  .card h2 {{ font-size: 1rem; margin: 0 0 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; white-space: nowrap; }}
  th {{ text-align: left; color: var(--muted); font-weight: 500; padding: 4px 8px; }}
  td {{ padding: 6px 8px; border-top: 1px solid var(--border); }}
  .pos {{ color: var(--pos); font-weight: 600; }}
  .neg {{ color: var(--neg); font-weight: 600; }}
  .disclaimer {{ color: var(--muted); font-size: 0.78rem; margin-top: 8px; line-height: 1.4; }}
</style>
</head>
<body>
  <h1>Nifty 50 Scanner</h1>
  <div class="meta">Last updated: {timestamp} IST &middot; refresh this page for the latest run</div>
  <div class="breadth">
    <div class="pill">Advances: <span class="pos">{advances}</span></div>
    <div class="pill">Declines: <span class="neg">{declines}</span></div>
    <div class="pill">Tracked: {len(all_rows)}/50</div>
  </div>

  <div class="card">
    <h2>Long candidates (trending up from open)</h2>
    <table>
      <tr><th>Symbol</th><th>LTP</th><th>Day %</th><th>From open</th><th>Range pos</th></tr>
      {long_rows}
    </table>
  </div>

  <div class="card">
    <h2>Short candidates (trending down from open)</h2>
    <table>
      <tr><th>Symbol</th><th>LTP</th><th>Day %</th><th>From open</th><th>Range pos</th></tr>
      {short_rows}
    </table>
  </div>

  <p class="disclaimer">
    Read-only market data, refreshed on a schedule. This is not a trade recommendation
    and does not place any orders. "Range pos" is where the last price sits between the
    day's low (0%) and high (100%). Verify against your own chart before acting.
  </p>
</body>
</html>"""
    return html


def main():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)  # IST
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    rows = fetch_all()
    longs, shorts = score_and_rank(rows)
    html = render_html(longs, shorts, rows, timestamp)

    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    # also dump raw data, useful for debugging / history
    with open("docs/latest.json", "w", encoding="utf-8") as f:
        json.dump({"timestamp": timestamp, "rows": rows}, f, indent=2)

    print(f"[{timestamp}] wrote docs/index.html with {len(rows)} symbols "
          f"({len(longs)} longs, {len(shorts)} shorts)")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
