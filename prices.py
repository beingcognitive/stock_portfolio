"""현재가 조회 (price fetching).

전략: KRX 숫자 코드는 pykrx로 최근 종가를 먼저 시도하고,
실패하거나 영숫자 코드(예: 0185L0)인 경우 yfinance(.KS)로 폴백한다.
모든 종목에 .KS 야후 심볼이 있으므로 yfinance가 최종 안전망 역할을 한다.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import io
import re

_NUMERIC_CODE = re.compile(r"^\d{6}$")


@contextlib.contextmanager
def _quiet():
    """pykrx 등이 import/호출 시 찍는 잡음을 삼킨다."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


def _from_pykrx(krx_code: str, as_of: _dt.date | None = None) -> float | None:
    if not krx_code or not _NUMERIC_CODE.match(krx_code):
        return None
    try:
        with _quiet():
            from pykrx import stock
    except Exception:
        return None
    try:
        end_date = as_of or _dt.date.today()
        start = (end_date - _dt.timedelta(days=14)).strftime("%Y%m%d")
        end = end_date.strftime("%Y%m%d")
        with _quiet():
            df = stock.get_market_ohlcv(start, end, krx_code)
        if df is None or df.empty:
            return None
        # as_of 이하 날짜 중 가장 최근 종가 (휴장일 대비)
        close = df["종가"].dropna()
        if close.empty:
            return None
        return float(close.iloc[-1])
    except Exception:
        return None


def _from_yfinance(ticker: str, as_of: _dt.date | None = None) -> float | None:
    if not ticker:
        return None
    try:
        import yfinance as yf
    except Exception:
        return None
    try:
        t = yf.Ticker(ticker)
        if as_of is None:
            # 현재가: fast_info 가 가장 싸고 신뢰도 높음
            try:
                price = t.fast_info.get("last_price")
                if price:
                    return float(price)
            except Exception:
                pass
            hist = t.history(period="5d")
        else:
            # 특정일 종가: as_of 포함 직전 9일 창에서 as_of 이하 마지막 종가
            start = (as_of - _dt.timedelta(days=9)).strftime("%Y-%m-%d")
            end = (as_of + _dt.timedelta(days=1)).strftime("%Y-%m-%d")
            with _quiet():
                hist = t.history(start=start, end=end)
        if hist is not None and not hist.empty:
            return float(hist["Close"].dropna().iloc[-1])
    except Exception:
        return None
    return None


def get_price(
    ticker: str, krx_code: str | None = None, as_of: _dt.date | None = None
) -> tuple[float | None, str]:
    """가격과 출처를 반환. (price, source)

    as_of 를 주면 그 날짜(휴장이면 직전 거래일)의 종가를 조회한다.
    source 는 'pykrx', 'yfinance', 또는 'none'.
    """
    price = _from_pykrx(krx_code or "", as_of)
    if price is not None:
        return price, "pykrx"
    price = _from_yfinance(ticker, as_of)
    if price is not None:
        return price, "yfinance"
    return None, "none"


def get_series(
    ticker: str, krx_code: str | None, start: _dt.date, end: _dt.date
) -> dict[str, float]:
    """[start, end] 구간의 일별 종가를 {'YYYY-MM-DD': close} 로 반환.

    숫자 KRX 코드는 pykrx, 그 외엔 yfinance(.KS) 사용. 실패 시 빈 dict.
    """
    out: dict[str, float] = {}
    code = krx_code or ""
    if _NUMERIC_CODE.match(code):
        try:
            with _quiet():
                from pykrx import stock

                df = stock.get_market_ohlcv(
                    start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), code
                )
            if df is not None and not df.empty:
                for idx, val in df["종가"].dropna().items():
                    out[idx.strftime("%Y-%m-%d")] = float(val)
            if out:
                return out
        except Exception:
            pass
    # yfinance 폴백 (또는 영숫자 코드)
    try:
        import yfinance as yf

        with _quiet():
            hist = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=(end + _dt.timedelta(days=1)).strftime("%Y-%m-%d"),
            )
        if hist is not None and not hist.empty:
            for idx, val in hist["Close"].dropna().items():
                out[idx.strftime("%Y-%m-%d")] = float(val)
    except Exception:
        pass
    return out


def get_prices(
    holdings: list[dict], as_of: _dt.date | None = None
) -> dict[str, dict]:
    """티커별 가격을 한 번씩만 조회 (중복 종목 캐시)."""
    cache: dict[str, dict] = {}
    for h in holdings:
        ticker = h["ticker"]
        if ticker in cache:
            continue
        price, source = get_price(ticker, h.get("krx_code"), as_of)
        cache[ticker] = {"price": price, "source": source}
    return cache
