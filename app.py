"""포트폴리오 대시보드 웹 서버 (Flask).

실행: python app.py  →  http://127.0.0.1:8000
프런트엔드가 /api/data 한 번으로 곡선·기준일 테이블·계좌 필터를 모두 계산한다.
"""

from __future__ import annotations

import argparse
import threading
import time
import webbrowser

from flask import Flask, jsonify, render_template, request

import portfolio as pf

app = Flask(__name__)

# 차분 모드 기본값: 전일대비(일일 변동)를 숨긴다. --show-daily 로 켠다.
# 자주 들여다볼수록 노이즈상 손실에 조급해지기 쉬워, 기본은 누적·곡선만 보여준다.
SHOW_DAILY = False

# 섹터 집중도(look-through) 패널은 기본 숨김. --semi / --defense 로 켠다.
# 개인화 분석 + 외부 비중 데이터(etf_<sector>_weights.yaml) 의존이라 공개 기본값엔 두지 않는다.
SHOW_SEMI = False
SHOW_DEFENSE = False

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
    return render_template("index.html", show_daily=SHOW_DAILY,
                           show_semi=SHOW_SEMI, show_defense=SHOW_DEFENSE)


@app.route("/api/data")
def api_data():
    force = request.args.get("force") in ("1", "true", "yes")
    return jsonify(_get_data(force=force))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--curve", action="store_true", help="가치 곡선을 콘솔에 출력하고 종료")
    parser.add_argument("--show-daily", action="store_true",
                        help="전일대비(일일 변동)를 표시. 기본은 차분 모드로 숨김")
    parser.add_argument("--semi", action="store_true",
                        help="종목별 보기에 '반도체 집중도(look-through)' 섹션을 표시 "
                             "(etf_semi_weights.yaml 필요)")
    parser.add_argument("--defense", action="store_true",
                        help="종목별 보기에 '방산·조선 집중도(look-through)' 섹션을 표시 "
                             "(etf_defense_weights.yaml 필요)")
    parser.add_argument("--no-browser", action="store_true",
                        help="실행 시 브라우저 자동 열기를 끈다")
    args = parser.parse_args()

    SHOW_DAILY = args.show_daily
    SHOW_SEMI = args.semi
    SHOW_DEFENSE = args.defense

    if args.curve:
        for pt in pf.equity_curve():
            print(f"{pt['date']}  value=₩{pt['total_value']:>15,.0f}  cost=₩{pt['total_cost']:>15,.0f}")
    else:
        # 서버가 포트에 바인딩될 때까지 잠깐 기다렸다가 기본 브라우저로 대시보드를 연다.
        #   접속 주소는 localhost 고정(0.0.0.0 으로 띄워도 브라우저는 127.0.0.1 로 연결).
        if not args.no_browser:
            url = f"http://127.0.0.1:{args.port}/"
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        app.run(host=args.host, port=args.port, debug=False)
