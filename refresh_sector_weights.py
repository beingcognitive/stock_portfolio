"""국내 ETF의 섹터 비중(look-through)을 네이버 구성종목에서 자동 갱신한다.

대시보드의 섹터 집중도 패널(반도체 `--semi`, 방산·조선 `--defense`)이 쓰는 비중 중
**국내 부분만** 신선하게 유지한다. 한 번의 구성종목 조회로 여러 섹터를 동시에 분류한다.
  - 소스 : https://m.stock.naver.com/api/stock/<krx_code>/etfAnalysis 의
           etfTop10MajorConstituentAssets (구성종목 TOP10 + 비중)
  - 대상 : 원장(transactions.yaml)에서 보유 중인 ETF 의 krx_code
  - 출력 : etf_<sector>_weights.auto.yaml  (sector ∈ semi, defense)

해외 ETF·혼합형은 네이버가 비중을 '-' 로 주거나 주식분이 합성이라 자동화하지 않는다.
그 값들은 수동 파일(etf_<sector>_weights.yaml)에 두고, portfolio.load_sector_weights() 가
둘을 병합한다(자동이 국내 버킷만 덮음).

  실행 :  python refresh_sector_weights.py
한계 : TOP10 만 제공되므로 11위 밖 종목은 누락될 수 있다(대형주는 상위라 정확).
       분류 종목코드는 아래 SECTORS 에서 편집/확장.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import urllib.request

import yaml

import portfolio as pf

API = "https://m.stock.naver.com/api/stock/{code}/etfAnalysis"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_DIR = os.path.dirname(os.path.abspath(__file__))

# --- 섹터별 분류: 버킷 -> 종목코드 집합 (편집 가능) -------------------------
# 자동 갱신은 '국내' 버킷만 채운다. 해외/글로벌 버킷은 수동 파일에서 관리.
SECTORS = {
    "semi": {
        "삼성전자": {"005930", "005935"},                 # 삼성전자(보통주/우선주)
        "SK하이닉스": {"000660"},
        "한국기타반도체": {                                  # 설계·장비·소재·후공정·기판·지주
            "402340", "009150", "080220", "042700", "000990", "058470",
            "039030", "036930", "240810", "403870", "095340", "357780",
            "064760", "067310", "131970", "108320",
        },
    },
    "defense": {
        "방산": {                                          # 항공우주·방산·감시
            "012450",  # 한화에어로스페이스
            "079550",  # LIG디펜스앤에어로스페이스(구 LIG넥스원)
            "047810",  # 한국항공우주(KAI)
            "064350",  # 현대로템
            "272210",  # 한화시스템
            "489790",  # 한화비전(감시/방산)
            "103140",  # 풍산
        },
        "조선": {                                          # 조선·해양·엔진
            "329180",  # HD현대중공업
            "009540",  # HD한국조선해양
            "010140",  # 삼성중공업
            "010620",  # HD현대미포
            "042660",  # 한화오션
            "443060",  # HD현대마린솔루션
        },
    },
}


def _pct(s) -> float | None:
    if s in (None, "-", ""):
        return None
    try:
        return float(str(s).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def fetch_top10(code: str) -> list[dict]:
    req = urllib.request.Request(API.format(code=code), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    return d.get("etfTop10MajorConstituentAssets", []) or []


def classify(rows: list[dict], buckets: dict) -> dict | None:
    """top10 행들을 한 섹터의 버킷으로 합산. 비중 미제공이면 None(자동화 대상 아님)."""
    out: dict[str, float] = {}
    got = False
    for r in rows:
        w = _pct(r.get("etfWeight"))
        if w is None:
            continue
        got = True
        ic = (r.get("itemCode") or "").strip()
        for bucket, codes in buckets.items():
            if ic in codes:
                out[bucket] = round(out.get(bucket, 0.0) + w, 2)
    if not got:
        return None
    return {k: v for k, v in out.items() if v} or None


def main() -> None:
    seen: dict[str, str] = {}
    for lot in pf.load_lots():
        code = lot.get("krx_code")
        if code and code not in seen:
            seen[code] = lot["name"]

    today = _dt.date.today().isoformat()
    for sector, buckets in SECTORS.items():
        weights, updated, skipped = {}, [], []
        for code, name in seen.items():
            try:
                rows = fetch_top10(code)
            except Exception as e:  # noqa: BLE001
                skipped.append(f"{code}({name}: 조회실패 {e})")
                continue
            w = classify(rows, buckets)
            if w:
                weights[code] = w
                updated.append(f"{code} {name}: {w}")
            else:
                skipped.append(f"{code} {name}")
        path = os.path.join(_DIR, f"etf_{sector}_weights.auto.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# 자동 생성 파일 — 직접 편집 금지. `python refresh_sector_weights.py` 로 갱신.\n")
            f.write(f"# 섹터 '{sector}' 국내 ETF 비중(네이버 구성종목 TOP10). 해외/혼합은 수동 파일에서 관리.\n")
            yaml.safe_dump({"as_of": today, "_generated_by": "refresh_sector_weights.py",
                            "weights": weights}, f, allow_unicode=True, sort_keys=False)
        print(f"\n[{sector}] → etf_{sector}_weights.auto.yaml (as_of {today}) · 갱신 {len(updated)}건")
        for u in updated:
            print("   -", u)
        if skipped:
            print(f"   건너뜀 {len(skipped)}건(해외/혼합/비중미제공, 수동 유지)")


if __name__ == "__main__":
    main()
