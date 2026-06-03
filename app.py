"""포트폴리오 대시보드 웹 서버 (Flask).

실행: python app.py  →  http://127.0.0.1:5000
프런트엔드가 /api/data 한 번으로 곡선·기준일 테이블·계좌 필터를 모두 계산한다.
"""

from __future__ import annotations

import argparse
import time

from flask import Flask, jsonify, render_template, request

import portfolio as pf

app = Flask(__name__)

# 가격 시계열만 캐시(과거 종가는 불변). 원장은 매 요청 새로 읽는다.
_cache: dict = {"prices": None, "ts": 0.0}
_TTL = 1800.0  # 이 시간이 지나거나 새로고침을 누르면 최근 구간 가격을 다시 받는다.


def _get_data(force: bool = False) -> dict:
    now = time.time()
    prior = _cache["prices"]
    # 쓸 만한 캐시 = 비어있지 않은 가격 시계열이 하나라도 있을 때.
    have_cache = bool(prior) and any(prior.values())
    if not have_cache:
        data = pf.dataset()                      # 콜드/복구: 전 구간 수집
        _cache["ts"] = now
    elif force or now - _cache["ts"] > _TTL:
        data = pf.dataset(prior, refresh=True)   # 최근 구간만 다시 받기
        _cache["ts"] = now
    else:
        data = pf.dataset(prior, refresh=False)  # 캐시 재사용 (원장만 갱신, 네트워크 0)
    # 가격 수집에 성공(거래일 존재)했을 때만 캐시. 실패하면 다음 요청에서 다시 시도.
    if data.get("trading_days"):
        _cache["prices"] = data["prices"]
    else:
        _cache["prices"] = None
        _cache["ts"] = 0.0
    return data


@app.after_request
def _no_cache(resp):
    # 브라우저가 옛 HTML/JS 를 들고 새 /api/data 를 호출하면 깨지므로 캐시 금지.
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    force = request.args.get("force") in ("1", "true", "yes")
    return jsonify(_get_data(force=force))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--curve", action="store_true", help="가치 곡선을 콘솔에 출력하고 종료")
    args = parser.parse_args()

    if args.curve:
        for pt in pf.equity_curve():
            print(f"{pt['date']}  value=₩{pt['total_value']:>15,.0f}  cost=₩{pt['total_cost']:>15,.0f}")
    else:
        app.run(host=args.host, port=args.port, debug=False)
