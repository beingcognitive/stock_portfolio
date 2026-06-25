"""국내 ETF의 반도체 비중(look-through)을 네이버 구성종목에서 자동 갱신한다.

대시보드의 '반도체 집중도' 섹션이 쓰는 비중 중 **국내 부분만** 신선하게 유지한다.
  - 소스 : https://m.stock.naver.com/api/stock/<krx_code>/etfAnalysis 의
           etfTop10MajorConstituentAssets (구성종목 TOP10 + 비중)
  - 대상 : 원장(transactions.yaml)에서 보유 중인 ETF 의 krx_code
  - 출력 : etf_semi_weights.auto.yaml (삼성전자 / SK하이닉스 / 한국기타반도체)

해외 ETF·혼합형(예: RISE 삼성전자SK하이닉스)은 네이버가 비중을 '-' 로 주거나
주식분이 합성이라 **자동화하지 않는다.** 그 값들은 수동 파일(etf_semi_weights.yaml)에
그대로 두고, portfolio.load_semi_weights() 가 둘을 병합한다(자동이 국내 버킷만 덮음).

  실행 :  python refresh_semi_weights.py
한계 : TOP10 만 제공되므로 11위 밖 반도체주는 '한국기타반도체'에서 누락될 수 있다.
       (삼성전자·SK하이닉스는 항상 상위라 정확.) 분류 코드 목록은 아래에서 편집.
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
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etf_semi_weights.auto.yaml")

# --- 반도체 종목코드 분류 (편집 가능) ---------------------------------------
SAMSUNG = {"005930", "005935"}            # 삼성전자(보통주/우선주)
HYNIX = {"000660"}                          # SK하이닉스
# 한국 기타 반도체(설계·장비·소재·후공정·기판 포함). 필요 시 자유롭게 추가/삭제.
KR_OTHER_SEMI = {
    "402340": "SK스퀘어", "009150": "삼성전기", "080220": "제주반도체",
    "042700": "한미반도체", "000990": "DB하이텍", "058470": "리노공업",
    "039030": "이오테크닉스", "036930": "주성엔지니어링", "240810": "원익IPS",
    "403870": "HPSP", "095340": "ISC", "357780": "솔브레인", "064760": "티씨케이",
    "067310": "하나마이크론", "131970": "두산테스나", "108320": "LX세미콘",
}


def _pct(s) -> float | None:
    """'34.48%' → 34.48, '-'/''/None → None."""
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


def compute(code: str) -> dict | None:
    """국내 ETF 한 종목의 {삼성전자, SK하이닉스, 한국기타반도체} 비중. 비중 없으면 None."""
    try:
        rows = fetch_top10(code)
    except Exception as e:  # noqa: BLE001 — 네트워크/파싱 실패는 건너뛰고 수동값 보존
        print(f"  ! {code}: 조회 실패 ({e}) — 건너뜀")
        return None
    ss = hy = etc = 0.0
    got = False
    for r in rows:
        w = _pct(r.get("etfWeight"))
        if w is None:
            continue
        got = True
        ic = (r.get("itemCode") or "").strip()
        if ic in SAMSUNG:
            ss += w
        elif ic in HYNIX:
            hy += w
        elif ic in KR_OTHER_SEMI:
            etc += w
    if not got:
        return None  # 비중 미제공(해외/혼합) → 자동화 대상 아님
    out = {}
    if ss:
        out["삼성전자"] = round(ss, 2)
    if hy:
        out["SK하이닉스"] = round(hy, 2)
    if etc:
        out["한국기타반도체"] = round(etc, 2)
    return out or None


def main() -> None:
    # 보유 ETF 의 (krx_code, name) 유니크 목록 (현재 보유 lots 기준)
    seen: dict[str, str] = {}
    for lot in pf.load_lots():
        code = lot.get("krx_code")
        if code and code not in seen:
            seen[code] = lot["name"]

    weights: dict[str, dict] = {}
    updated, skipped = [], []
    for code, name in seen.items():
        w = compute(code)
        if w:
            weights[code] = w
            updated.append(f"{code} {name}: {w}")
        else:
            skipped.append(f"{code} {name}")

    payload = {
        "as_of": _dt.date.today().isoformat(),
        "_generated_by": "refresh_semi_weights.py",
        "weights": weights,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("# 자동 생성 파일 — 직접 편집 금지. `python refresh_semi_weights.py` 로 갱신.\n")
        f.write("# 국내 ETF 의 삼성전자/SK하이닉스/한국기타반도체 비중(네이버 구성종목 TOP10).\n")
        f.write("# 해외·혼합형은 수동 파일(etf_semi_weights.yaml)에서 관리된다.\n")
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)

    print(f"\n✅ 갱신 완료 → {os.path.basename(OUT_PATH)} (as_of {payload['as_of']})")
    print(f"   자동 갱신 {len(updated)}건:")
    for u in updated:
        print("     -", u)
    if skipped:
        print(f"   건너뜀(해외/혼합/비중미제공, 수동 유지) {len(skipped)}건: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
