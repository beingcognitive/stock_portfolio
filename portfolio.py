"""포트폴리오 계산: 거래 원장 → 현재 보유 + 확정수익 + 일별 가치 곡선."""

from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3

import yaml

import prices as price_mod

_DIR = os.path.dirname(os.path.abspath(__file__))
# 개인 원장(transactions.yaml)이 있으면 그걸, 없으면 공개 샘플(transactions.example.yaml)을 사용.
# 개인 원장은 .gitignore 로 저장소에서 제외됩니다.
LEDGER_PATH = os.path.join(_DIR, "transactions.yaml")
EXAMPLE_PATH = os.path.join(_DIR, "transactions.example.yaml")
DB_PATH = os.path.join(_DIR, "history.db")

CURVE_START = _dt.date(2025, 8, 1)  # 최초 매수(2025-08)부터 곡선 시작


def _as_date(v) -> _dt.date:
    if isinstance(v, _dt.date):
        return v
    return _dt.date.fromisoformat(str(v))


def _ledger_path() -> str:
    return LEDGER_PATH if os.path.exists(LEDGER_PATH) else EXAMPLE_PATH


def load_ledger() -> dict:
    with open(_ledger_path(), "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_lots() -> list[dict]:
    return load_ledger().get("lots", [])


def load_closed() -> list[dict]:
    return load_ledger().get("closed", [])


def load_cash() -> list[dict]:
    """투자 외 예비현금 기록 (회차별). 매입원금/평가금액에는 섞지 않는다."""
    return load_ledger().get("cash", [])


def load_account_order() -> list[str]:
    """계좌 표시/정렬 우선순위 (선택). 원장에 없으면 빈 리스트.

    여기 나열된 계좌가 앞쪽에 이 순서대로 오고, 목록에 없는 계좌는
    원장 등장 순서대로 뒤에 붙는다. 실제 계좌명은 개인 원장에만 두고
    공개 코드에는 두지 않기 위한 설정 항목이다.
    """
    return [str(a) for a in load_ledger().get("account_order", [])]


def cash_total(as_of: _dt.date | None = None) -> float:
    """기준일까지 누적된 현금 잔액 (날짜 지정 없으면 전체)."""
    as_of = as_of or _dt.date.today()
    return sum(
        float(c["amount"]) for c in load_cash() if _as_date(c["date"]) <= as_of
    )


def load_holdings() -> list[dict]:
    """현재 보유 = open lots 를 (계좌, 티커) 기준으로 합산."""
    agg: dict[tuple, dict] = {}
    for lot in load_lots():
        key = (lot["account"], lot["ticker"])
        cost = float(lot["shares"]) * float(lot["price"])
        if key not in agg:
            agg[key] = {
                "name": lot["name"],
                "ticker": lot["ticker"],
                "krx_code": lot.get("krx_code"),
                "account": lot["account"],
                "region": lot["region"],
                "shares": 0.0,
                "cost": 0.0,
            }
        agg[key]["shares"] += float(lot["shares"])
        agg[key]["cost"] += cost
    holdings = []
    for h in agg.values():
        h["avg_price"] = h["cost"] / h["shares"] if h["shares"] else 0.0
        holdings.append(h)
    return holdings


def build_portfolio(price_cache: dict | None = None) -> dict:
    """현재 가격으로 종목/계좌/전체 + 확정수익 요약을 만든다."""
    holdings = load_holdings()
    if price_cache is None:
        price_cache = price_mod.get_prices(holdings)

    positions = []
    for h in holdings:
        info = price_cache.get(h["ticker"], {})
        live = info.get("price")
        source = info.get("source", "none")
        cost = float(h["cost"])
        shares = float(h["shares"])
        cur_price = live if live is not None else float(h["avg_price"])
        value = shares * cur_price
        pl = value - cost
        positions.append(
            {
                "name": h["name"],
                "ticker": h["ticker"],
                "account": h["account"],
                "region": h["region"],
                "shares": shares,
                "avg_price": float(h["avg_price"]),
                "cost": cost,
                "price": cur_price,
                "value": value,
                "pl": pl,
                "return_pct": (pl / cost * 100.0) if cost else 0.0,
                "source": source,
                "stale": live is None,
            }
        )

    accounts: dict[str, dict] = {}
    for p in positions:
        a = accounts.setdefault(
            p["account"], {"account": p["account"], "cost": 0.0, "value": 0.0}
        )
        a["cost"] += p["cost"]
        a["value"] += p["value"]
    for a in accounts.values():
        a["pl"] = a["value"] - a["cost"]
        a["return_pct"] = (a["pl"] / a["cost"] * 100.0) if a["cost"] else 0.0

    total_cost = sum(p["cost"] for p in positions)
    total_value = sum(p["value"] for p in positions)
    total_pl = total_value - total_cost
    cash = cash_total()

    return {
        "as_of": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "positions": positions,
        "accounts": sorted(accounts.values(), key=lambda x: -x["value"]),
        "cash": cash,
        "total": {
            "cost": total_cost,
            "value": total_value,
            "pl": total_pl,
            "return_pct": (total_pl / total_cost * 100.0) if total_cost else 0.0,
            "net_worth": total_value + cash,
        },
        "realized": realized_summary(),
    }


# --------------------------- 확정수익 (realized) ---------------------------

def realized_summary() -> dict:
    """청산 거래의 확정수익 합계 + 계좌별 + 거래 목록.

    매입원금 = 회차(tranches)의 cost 합, 매도금액 = proceeds(시트 실제 수령액),
    확정수익 = proceeds - 매입원금.
    """
    trades = []
    accounts: dict[str, float] = {}
    total = 0.0
    for c in load_closed():
        cost = sum(float(t["cost"]) for t in c["tranches"])
        proceeds = float(c["proceeds"])
        pl = proceeds - cost
        buy_date = min(str(t["date"]) for t in c["tranches"])
        total += pl
        accounts[c["account"]] = accounts.get(c["account"], 0.0) + pl
        trades.append(
            {
                "account": c["account"],
                "name": c["name"],
                "buy_date": buy_date,
                "sell_date": str(c["sell_date"]),
                "cost": cost,
                "proceeds": proceeds,
                "pl": pl,
                "return_pct": (pl / cost * 100.0) if cost else 0.0,
            }
        )
    trades.sort(key=lambda t: t["sell_date"], reverse=True)
    return {
        "total": total,
        "accounts": accounts,
        "trades": trades,
    }


# --------------------------- 클라이언트용 데이터셋 ---------------------------

REFRESH_WINDOW_DAYS = 7  # 새로고침 시 다시 받는 최근 구간. 그 이전은 종가가 확정됐으므로 캐시 재사용.


def dataset(prior_prices: dict | None = None, refresh: bool = True) -> dict:
    """프런트엔드가 곡선/기준일 테이블/계좌 필터를 직접 계산하도록
    원장 + 가격 시계열 + 거래일 그리드를 한 번에 내려준다.

    가격 처리:
      - prior_prices=None         : 전 구간을 새로 수집 (콜드 스타트).
      - prior_prices 있음, refresh : 과거 시계열은 재사용하고 최근 며칠만 다시 받음
                                      (장중 갱신·당일 종가 확정 반영, API 부담 최소).
      - prior_prices 있음, no refresh : 가격은 그대로 두고 원장만 다시 읽음 (네트워크 0).
    원장(lots/closed)은 매번 새로 읽으므로 transactions.yaml 편집이 새로고침에 바로 반영됩니다.
    """
    start, end = CURVE_START, _dt.date.today()
    lots = load_lots()
    closed = load_closed()
    cash = load_cash()

    tickers: dict[str, str | None] = {}
    for lot in lots:
        tickers[lot["ticker"]] = lot.get("krx_code")
    for c in closed:
        if c.get("ticker"):
            tickers[c["ticker"]] = c.get("krx_code")

    # 현재 보유 중인 티커만 최신가가 의미 있음. 이미 매도한(closed 전용) 티커는
    # 가격 이력이 전부 과거(불변)라 새로고침 때 다시 받을 필요가 없다.
    held = {lot["ticker"] for lot in lots}
    recent_start = end - _dt.timedelta(days=REFRESH_WINDOW_DAYS)
    prices: dict[str, dict[str, float]] = {}
    tdays: set[str] = set()
    for tk, code in tickers.items():
        cached = prior_prices.get(tk) if prior_prices is not None else None
        if cached:  # 비어있지 않은 캐시만 재사용 (빈 시계열이면 아래 전체 수집으로 복구).
            s = dict(cached)
            if refresh and tk in held:
                s.update(price_mod.get_series(tk, code, recent_start, end))
        else:
            # 신규 티커이거나 캐시 없음/비어있음 → 전 구간 수집 (실패 캐시 자동 복구).
            s = price_mod.get_series(tk, code, start, end)
        prices[tk] = s
        tdays.update(s.keys())
    days = sorted(d for d in tdays if start.isoformat() <= d <= end.isoformat())

    nlots = [
        {
            "account": l["account"], "name": l["name"], "ticker": l["ticker"],
            "region": l["region"], "date": str(l["date"]),
            "shares": float(l["shares"]), "price": float(l["price"]),
        }
        for l in lots
    ]
    nclosed = [
        {
            "account": c["account"], "name": c["name"], "ticker": c.get("ticker"),
            "region": c["region"], "sell_date": str(c["sell_date"]),
            "proceeds": float(c["proceeds"]),
            "tranches": [
                {"date": str(t["date"]), "shares": float(t["shares"]), "cost": float(t["cost"])}
                for t in c["tranches"]
            ],
        }
        for c in closed
    ]
    ncash = [
        {
            "account": c["account"], "name": c.get("name", "현금"),
            "date": str(c["date"]), "amount": float(c["amount"]),
        }
        for c in cash
    ]
    accounts = list(dict.fromkeys(
        [l["account"] for l in lots]
        + [c["account"] for c in closed]
        + [c["account"] for c in cash]
    ))

    return {
        "as_of": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "lots": nlots,
        "closed": nclosed,
        "cash": ncash,
        "prices": prices,
        "trading_days": days,
        "accounts": accounts,
        "account_order": load_account_order(),
    }


# --------------------------- 일별 가치 곡선 (equity curve) ---------------------------

def equity_curve(start: _dt.date | None = None, end: _dt.date | None = None) -> list[dict]:
    """[start, end] 구간 일별 평가금액/투자원금 곡선.

    각 거래일 D 에서 그날 보유 중인 모든 건(open lots + 매도 전 closed)을
    합산한다. 티커가 있으면 실제 종가, 없으면 매수가→매도가 선형 보간.
    """
    import pandas as pd

    start = start or CURVE_START
    end = end or _dt.date.today()
    lots = load_lots()
    closed = load_closed()
    cash = load_cash()

    # 1) 티커별 종가 시계열 수집 (open + 티커 있는 closed)
    tickers: dict[str, str | None] = {}
    for lot in lots:
        tickers[lot["ticker"]] = lot.get("krx_code")
    for c in closed:
        if c.get("ticker"):
            tickers[c["ticker"]] = c.get("krx_code")

    series: dict[str, dict[str, float]] = {}
    trading_days: set[str] = set()
    for tk, code in tickers.items():
        s = price_mod.get_series(tk, code, start, end)
        series[tk] = s
        trading_days.update(s.keys())

    if not trading_days:
        return []

    days = sorted(d for d in trading_days if start.isoformat() <= d <= end.isoformat())

    # 티커별 forward-fill 시리즈 (휴장일 대비)
    idx = pd.to_datetime(days)
    ff: dict[str, pd.Series] = {}
    for tk, s in series.items():
        if not s:
            continue
        ser = pd.Series(s)
        ser.index = pd.to_datetime(ser.index)
        ff[tk] = ser.reindex(idx, method="ffill")

    def price_on(tk: str, i: int) -> float | None:
        ser = ff.get(tk)
        if ser is None:
            return None
        v = ser.iloc[i]
        return None if pd.isna(v) else float(v)

    out = []
    for i, d in enumerate(days):
        dd = _dt.date.fromisoformat(d)
        value = 0.0
        cost = 0.0
        # open lots
        for lot in lots:
            if _as_date(lot["date"]) <= dd:
                shares = float(lot["shares"])
                cost += shares * float(lot["price"])
                p = price_on(lot["ticker"], i)
                value += shares * (p if p is not None else float(lot["price"]))
        # closed lots: 회차별로 매수일~매도일 직전까지만 보유 (매도일 당일은 현금화).
        # 같은 날 전 종목을 팔면 그날 곡선이 푹 꺼지는데 이는 실제 현금화를 반영한 것.
        for c in closed:
            sd = _as_date(c["sell_date"])
            if dd >= sd:
                continue
            p = price_on(c["ticker"], i)
            for tr in c["tranches"]:
                if _as_date(tr["date"]) <= dd:
                    shares = float(tr["shares"])
                    tcost = float(tr["cost"])
                    cost += tcost
                    fallback = tcost / shares if shares else 0.0
                    value += shares * (p if p is not None else fallback)
        cash_amt = sum(
            float(cc["amount"]) for cc in cash if _as_date(cc["date"]) <= dd
        )
        if value > 0 or cash_amt > 0:
            out.append({
                "date": d,
                "total_value": value,
                "total_cost": cost,
                "cash": cash_amt,
                "net_worth": value + cash_amt,
            })
    return out


# --------------------------- 스냅샷 (옵션, 곡선 보조) ---------------------------

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            date        TEXT PRIMARY KEY,
            total_cost  REAL,
            total_value REAL,
            accounts    TEXT,
            taken_at    TEXT
        )
        """
    )
    return conn


def save_snapshot(portfolio: dict | None = None, date: _dt.date | None = None) -> dict:
    if portfolio is None:
        portfolio = build_portfolio()
    day = (date or _dt.date.today()).strftime("%Y-%m-%d")
    accounts_json = json.dumps(
        {a["account"]: a["value"] for a in portfolio["accounts"]},
        ensure_ascii=False,
    )
    conn = _conn()
    with conn:
        conn.execute(
            "REPLACE INTO snapshots (date, total_cost, total_value, accounts, taken_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                day,
                portfolio["total"]["cost"],
                portfolio["total"]["value"],
                accounts_json,
                portfolio["as_of"],
            ),
        )
    conn.close()
    return {"date": day, "total_value": portfolio["total"]["value"]}
