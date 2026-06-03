# Stock Portfolio Tracker

A local web dashboard that turns your trade ledger (buys and sells) into current holdings
valuation, realized P/L, and a daily market-value curve from your first purchase to today.

> Built for Korean-listed (KRX) ETFs — including ones that hold overseas assets. Daily closes come
> from [pykrx](https://github.com/sharebook-kr/pykrx) (KRX) and [yfinance](https://github.com/ranaroussi/yfinance).
> **The dashboard UI is in Korean.** This README maps the key terms to English (see
> [What's on screen](#whats-on-screen)); for the rest, your browser's auto-translate works fine.

## Preview

![Portfolio dashboard](docs/screenshot.png)

> The screenshot uses the bundled **sample data** (`transactions.example.yaml`), not real holdings.
> Run it yourself and the same screen renders from your own ledger (`transactions.yaml`).

## Install · Run

### Let Claude Code do it (the easy way)

Open [Claude Code](https://claude.com/claude-code) in a terminal and **paste this:**

> Clone and run https://github.com/beingcognitive/stock_portfolio for me.
> Create a venv, install `requirements.txt`, then start the dashboard **in the background** with the
> sample data and **open the URL in my browser** (use another port if it's taken). Then show me how
> to put my own trades into `transactions.yaml`.

It handles the clone, venv, dependencies, and run, then walks you through filling in your ledger.
(For the format, see the field notes at the top of the file and the
[Editing the ledger](#editing-the-ledger-single-source) section below.)

### Manual install

```bash
git clone https://github.com/beingcognitive/stock_portfolio.git
cd stock_portfolio
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Add your trades: copy the sample and fill it in (transactions.yaml is gitignored)
cp transactions.example.yaml transactions.yaml
#   If transactions.yaml is absent, it just runs on the sample data.

# Start the dashboard (Windows: .venv\Scripts\python app.py)
.venv/bin/python app.py
# → open http://127.0.0.1:8000 in your browser (port clash: app.py --port 8001)
```

> On Windows, replace `.venv/bin/` with `.venv\Scripts\` in the commands above.

### Filling in your trades (no hand-writing YAML)

You don't have to format `transactions.yaml` by hand. Give your brokerage transaction history
as-is (text, CSV, or a screenshot of the table) to Claude Code and **say:**

> Here's my brokerage transaction history (↓ replace the line below with the text, or drag a screenshot in):
> [transactions here]
> Turn this into `transactions.yaml` (`lots` / `closed` / `cash`). Follow the format in
> `transactions.example.yaml` and the "Editing the ledger" section of the README. Rules:
> - For each ETF set `ticker`, the 6-digit `krx_code`, and `region` (`국내` for domestic-asset ETFs,
>   `해외` for foreign-asset ones). **If you're unsure, ask me — don't guess** (a wrong code breaks price lookups).
> - For sells, I also need the actual sale proceeds (`proceeds`) and the **buy tranches (when and how
>   much I bought in each lot)** — ask if they're missing.
> - When done, show me a name↔code table so I can verify.

Claude Code sorts your holdings, closed trades, and cash, and asks instead of guessing on unknown
values, which avoids silent errors. After that, just hand it any new trades.

Don't know an ETF's KRX code? Give Claude the fund's English name or ISIN and ask it to find the
6-digit KRX listing code — then check it against the name↔code table it shows you.

🔒 Everything runs on your own machine and `transactions.yaml` is gitignored (never pushed). But text
you paste into Claude Code is transmitted, so strip out account numbers and personal ID numbers
(SSN, resident registration number, etc.) and share only the trades.

## What's on screen

On-screen labels are Korean; below, the English term comes first with the Korean label in parentheses.

- **Asset flow (summary)** : reads left to right as Cost basis (투자원금) → (unrealized P/L) →
  **Market value (평가금액)** → (+ cash) → Net worth (총자산). **Market value** is the focus
  (yellow border); cash is just added on to reach net worth. A line below shows realized P/L (확정수익)
  and total gain (unrealized + realized) separately.
- **Account filter (pills)** : only accounts that hold something appear as pills. Click to filter to
  that account; **전체** (All) clears it. (Cash-only accounts have nothing to show, so they're left off.)
- **Value curve** : daily market value vs. cost basis from your first purchase onward. A sold position
  counts **only while you held it**; after the sale it moves to realized P/L. If you sold everything
  before a given day, the curve drops to (near) zero that day — the real cash-out, shown as-is.
- **Per-account holdings table** : per ticker — shares / average cost / current (or as-of-date close)
  price / P/L / return %.
- **Realized P/L table** : completed sells/expirations and cumulative realized gain.

**On-screen labels (Korean → English):** 종목 = name · 수량 = shares · 평균단가 = avg cost ·
현재가 = current price · 매입금액 = cost · 평가금액 = market value · 손익 = P/L · 수익률 = return % ·
합계 = total · 전일대비 = vs. prior day · 확정 수익 (실현) = realized P/L · 매수일 / 매도일 = buy / sell date ·
매도금액 = proceeds · 새로고침 = Refresh · 전체 = All · 현재로 돌아가기 = Back to today.
(Or just let your browser auto-translate the page.)

## Interactions

- **Click a point on the graph** : the summary, holdings table, and realized P/L all switch to that
  date. (Positions held that day — including ones later sold — are valued at that day's close.) The
  selected day shows a **white-bordered dot + faint dotted vertical line**; hovering shows a small ring.
  Use **현재로 돌아가기** (Back to today) in the top banner to return.
- **Click an account pill** : filter to that account. Click several to combine (e.g. account A + B).
  Chart, tables, and realized P/L follow the selection. **전체** (All), or nothing selected, means everything.
- **Year selector (top-right of chart)** : All / per-year buttons zoom the curve to that year. Buttons
  are generated from the years present in your data. The Y-axis always starts at 0.

All computation runs in the browser from a single `/api/data` fetch, so clicks/filters are instant.

## Data refresh / caching

- **Ledger (lots/closed)** : `transactions.yaml` is re-read on every request, so after editing it just
  **refresh the browser** — no server restart needed.
- **Prices** : past closes don't change, so they're cached and reused; refetched only when:
  - the server first starts (full history),
  - 30 minutes have passed since the last price refresh, or
  - you hit the **Refresh button** (ignores the server cache and forces an update).
- The **Refresh button** calls `/api/data?force=1` and refetches **only the last 7 days for
  currently-held tickers** (already-sold tickers have only past, fixed prices). It shows
  **갱신 중…** (refreshing…) while it works.
- **During market hours (09:00–15:30 KST)** : this is a "closing-price" dashboard, most accurate after
  the close. Intraday, the last point is provisional (yfinance lags ~15 min; pykrx gives no intraday
  close before the close) and settles after close. Past dates are always final.

## Editing the ledger (single source)

All data comes from one file, `transactions.yaml` (or `transactions.example.yaml` if it's absent).
This file is personal, so it's excluded from the repo via `.gitignore`.

- `lots` : open buy positions. Add/remove lines as you buy and sell. Current holdings per account are
  auto-aggregated by (account, ticker).
- `closed` : completed sells (or expiries). Grouped per ticker, but each buy **tranche** is kept by
  date. That way the cost-basis curve accrues at each tranche's actual buy date (not pulled forward),
  and the held-period valuation uses the tranche's shares. Realized P/L = `proceeds` (the actual sale
  amount) − sum of tranche costs.
- `cash` (optional) : reserve cash outside your investments. Kept out of cost basis / market value /
  return %, and only added into **net worth (market value + cash)** and the asset flow. Recorded by
  date, so moving cash into a position reconciles automatically: one negative `amount` line + one buy
  `lot`. Treated like an account, but with no holdings it won't appear as a filter pill.

A few per-row fields, in English:
- `ticker` is the Yahoo Finance symbol (6-digit code + `.KS`); `krx_code` is the bare KRX short code
  for pykrx (usually 6 digits, occasionally alphanumeric like `0185L0`). The digits repeat on purpose — both are needed.
- `region` (`국내` = domestic-asset, `해외` = overseas-asset) is a **display-only tag**: copy the exact
  Korean value from the example — it does *not* affect prices or any calculation.
- Account names (`계좌A`…) and cash labels (`케이뱅크`, `예비현금`) are just placeholders — rename them to
  anything, in any language (they show verbatim as filter pills).

The file's own header comments describe each field (in Korean); the English summary above covers the same ground.

## Price sources

- Current/past closes: 6-digit numeric KRX codes are looked up via `pykrx` first; alphanumeric codes
  (e.g. `0185L0`) or failures fall back to `yfinance` (`.KS`).
- Every position (held or closed) has a ticker, so it's valued at actual closes. If a given day's close
  is unavailable, it's forward-filled from the prior trading day's close; failing that, the tranche's
  buy price is used.

## Value curve to the console

```bash
.venv/bin/python app.py --curve
```

## Files

| File | Role |
|------|------|
| `transactions.yaml` | the trade ledger (what you edit): `lots` + `closed` + `cash` |
| `prices.py` | price lookup — current price + historical close series (pykrx + yfinance) |
| `portfolio.py` | holdings, realized-P/L aggregation, daily value curve, the `/api/data` dataset |
| `app.py` | Flask web server (`/` dashboard, `/api/data`) |
| `templates/index.html` | the dashboard (all rendering/recompute happens in the browser) |

## Implementation notes (key decisions & assumptions)

- **Single source of truth = the ledger** : not a static holdings snapshot but a buy/sell ledger, from
  which current holdings, realized P/L, and the daily curve are all derived. Closed trades are grouped
  per ticker but keep their buy **tranches** by date/shares/amount.
- **What "cost basis" (투자원금) means** : the summed buy cost of positions held *on that day*. It rises
  at each tranche's buy date and falls when you sell (the gain moves to realized P/L). So it's the cost
  of *current* holdings, not cumulative deposits — which is why it drops on a sell day.
- **Tranche split avoids pull-forward** : lumping a closed position into one block (full amount at the
  first buy date) pulls cost basis earlier than reality and distorts the start of the curve. Splitting
  by tranche accrues it at the real buy dates.
- **Curve start** : drawn from the oldest buy date in your history.
- **Realized-P/L accuracy** : when the sale amount (`proceeds`) is known, it's used directly, so
  realized P/L = proceeds − sum of tranche costs is exact.
- **When you have to estimate** :
  - If you don't know the share count, round (cost ÷ fill price) to an integer (error usually < 0.1%).
  - For a closed trade with an unknown sale amount, estimate `proceeds` from the sell-date close (or the
    open, if sold near the open). Replace it once you have the exact figure.
  - Dividends are best left out of realized P/L to keep it simple (track separately if you want).
- **Cash is a separate bucket** : reserve cash isn't mixed into cost basis / market value / return %,
  only into **net worth (market value + cash)** and the asset flow. This keeps two different stories —
  investment performance (return, P/L) and balance (net worth) — apart, so the same number never shows twice.
- **Day-over-day (daily change) definition** : the "전일대비" line under the unrealized-P/L node and each
  account total is the **pure price move of positions held on *both* yesterday and today**, valued at the
  continuously-held share count (`min(yesterday, today)`), from the prior trading day's close to today's.
  Today's buys (not held yesterday) and sells (not held today) are excluded symmetrically, so cash flows
  don't leak in. It's a **separate metric** from cumulative P/L (vs. cost) and from realized P/L, and on
  a no-trade day it equals the price move of your holdings. The denominator is yesterday's held value,
  making it a daily %. A ticker bought today isn't in the total, so its row's day-over-day arrow (▲▼) is
  hidden too (for consistency).
- **No browser cache** : a `Cache-Control: no-store` header is set so stale JS doesn't read new data and
  break after a code update.
