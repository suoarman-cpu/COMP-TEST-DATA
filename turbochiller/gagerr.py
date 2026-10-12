"""게이지 R&R — 측정시스템 분석 (반복성·재현성).

압축기 시험에서 쓰는 측정기(온도·압력·유량·전력계, 마이크로미터·CMM 등)가
'믿을 만한지' 를 숫자로 판정한다. AIAG MSA 4판의 두 가지 방법을 모두 계산한다.

  - ANOVA 법           — 측정자×부품 교호작용까지 분리한다. 기본 판정에 쓴다.
  - 평균·범위(X̄/R) 법  — 손계산·엑셀과 맞춰볼 때 쓴다.

용어 (AIAG MSA)

    EV  반복성   같은 사람이 같은 부품을 여러 번 쟀을 때의 흩어짐 (장비 변동)
    AV  재현성   사람이 바뀌었을 때의 차이 (측정자 변동)
    GRR 게이지 R&R = √(EV² + AV²)
    PV  부품간 변동 (실제 제품 차이)
    TV  총변동  = √(GRR² + PV²)
    ndc 구별 범주 수 = 1.41 × PV / GRR — 이 측정기가 제품을 몇 등급으로 가를 수 있나

판정 (AIAG)

    %GRR < 10 %      적합
    10 ~ 30 %        조건부 (측정 대상의 중요도·비용을 보고 결정)
    > 30 %           부적합 — 측정시스템 개선 필요
    ndc ≥ 5          구별력 충분

이 모듈은 파이썬 내장 기능만 쓴다 (numpy·scipy 불필요).

    python -m turbochiller.gagerr 데이터.csv --lsl 249.95 --usl 250.05
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from dataclasses import dataclass, field
from typing import Optional, Sequence

# ---------------------------------------------------------------------------
# 관리도 상수 (부분군 크기 m = 2..15)
# ---------------------------------------------------------------------------

#: 범위의 기대값 d2, 표준편차 d3 (정규분포)
_D2 = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534, 7: 2.704, 8: 2.847,
       9: 2.970, 10: 3.078, 11: 3.173, 12: 3.258, 13: 3.336, 14: 3.407, 15: 3.472}
_D3 = {2: 0.853, 3: 0.888, 4: 0.880, 5: 0.864, 6: 0.848, 7: 0.833, 8: 0.820,
       9: 0.808, 10: 0.797, 11: 0.787, 12: 0.778, 13: 0.770, 14: 0.763, 15: 0.756}

#: R 관리도 상·하한 계수
_D4 = {2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114, 6: 2.004, 7: 1.924, 8: 1.864,
       9: 1.816, 10: 1.777, 11: 1.744, 12: 1.716, 13: 1.692, 14: 1.671, 15: 1.652}
_D3_CHART = {2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0, 7: 0.076, 8: 0.136,
             9: 0.184, 10: 0.223, 11: 0.256, 12: 0.284, 13: 0.308, 14: 0.329,
             15: 0.348}

#: X̄ 관리도 한계 계수
_A2 = {2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483, 7: 0.419, 8: 0.373,
       9: 0.337, 10: 0.308, 11: 0.285, 12: 0.266, 13: 0.249, 14: 0.235, 15: 0.223}

#: AIAG MSA 4판 표의 K1 (반복 횟수 2, 3). 나머지는 1/d2 로 계산한다.
_K1_AIAG = {2: 0.8862, 3: 0.5908}

#: AIAG MSA 4판 표의 K2(측정자 수)·K3(부품 수). 11 이상은 1/d2* 로 계산한다.
_K23_AIAG = {2: 0.7071, 3: 0.5231, 4: 0.4467, 5: 0.4030, 6: 0.3742, 7: 0.3534,
             8: 0.3375, 9: 0.3249, 10: 0.3146}

#: 판정 경계 [%]
LIMIT_OK = 10.0
LIMIT_NG = 30.0
NDC_MIN = 5

#: 연구변동 배수. AIAG 4판·Minitab 기본값이 6σ 다 (옛 3판은 5.15σ).
STUDY_VAR_K = 6.0


def k1(trials: int) -> float:
    """반복성 상수 K1 = 1/d2 (부분군이 많을 때)."""
    if trials in _K1_AIAG:
        return _K1_AIAG[trials]
    return 1.0 / _D2[trials]


def k_single(m: int) -> float:
    """K2·K3 = 1/d2* (부분군 1개). d2* = √(d2² + d3²)."""
    if m in _K23_AIAG:
        return _K23_AIAG[m]
    return 1.0 / math.sqrt(_D2[m] ** 2 + _D3[m] ** 2)


# ---------------------------------------------------------------------------
# F 분포 (p 값) — 불완전 베타 함수로 직접 계산
# ---------------------------------------------------------------------------

def _betacf(a: float, b: float, x: float) -> float:
    """불완전 베타 함수의 연분수 (Lentz 법)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """정규화 불완전 베타 함수 I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                + a * math.log(x) + b * math.log1p(-x))
    front = math.exp(ln_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def f_pvalue(f: float, df1: float, df2: float) -> float:
    """F 분포의 위쪽 꼬리 확률 P(F > f)."""
    if math.isnan(f):
        return float("nan")
    if math.isinf(f):
        return 0.0
    if f <= 0.0:
        return 1.0
    return betainc(df2 / 2.0, df1 / 2.0, df2 / (df2 + df1 * f))


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------

@dataclass
class Study:
    """측정 데이터. data[(부품, 측정자)] = [1회, 2회, ...]"""

    parts: list[str]
    operators: list[str]
    data: dict[tuple[str, str], list[float]]

    @property
    def trials(self) -> int:
        return len(next(iter(self.data.values())))

    @property
    def n_parts(self) -> int:
        return len(self.parts)

    @property
    def n_operators(self) -> int:
        return len(self.operators)

    def values(self) -> list[float]:
        return [v for vs in self.data.values() for v in vs]

    def cell_mean(self, part: str, op: str) -> float:
        vs = self.data[(part, op)]
        return sum(vs) / len(vs)

    def cell_range(self, part: str, op: str) -> float:
        vs = self.data[(part, op)]
        return max(vs) - min(vs)

    def part_mean(self, part: str) -> float:
        vs = [v for op in self.operators for v in self.data[(part, op)]]
        return sum(vs) / len(vs)

    def operator_mean(self, op: str) -> float:
        vs = [v for p in self.parts for v in self.data[(p, op)]]
        return sum(vs) / len(vs)


def build_study(rows: Sequence[tuple[str, str, float]]) -> Study:
    """(부품, 측정자, 값) 목록으로 Study 를 만들고 모양을 검사한다."""
    parts: list[str] = []
    operators: list[str] = []
    data: dict[tuple[str, str], list[float]] = {}
    for part, op, value in rows:
        if part not in parts:
            parts.append(part)
        if op not in operators:
            operators.append(op)
        data.setdefault((part, op), []).append(float(value))

    if len(parts) < 2:
        raise ValueError("부품이 2개 이상 있어야 합니다 (보통 10개).")
    if len(operators) < 2:
        raise ValueError("측정자가 2명 이상 있어야 합니다 (보통 3명).")

    missing = [f"{p}/{o}" for p in parts for o in operators if (p, o) not in data]
    if missing:
        raise ValueError(
            "모든 측정자가 모든 부품을 재야 합니다. 빠진 조합: "
            + ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")
        )

    counts = {len(v) for v in data.values()}
    if len(counts) != 1:
        detail = ", ".join(
            f"{p}/{o}={len(v)}회" for (p, o), v in list(data.items())[:6]
        )
        raise ValueError(
            "모든 부품·측정자 조합의 반복 횟수가 같아야 합니다 "
            f"(지금은 {sorted(counts)}회가 섞여 있음: {detail} ...)."
        )
    n = counts.pop()
    if n < 2:
        raise ValueError("같은 부품을 2회 이상 반복해서 재야 반복성을 알 수 있습니다.")
    if n > 15:
        raise ValueError("반복 횟수는 15회까지 받습니다.")

    return Study(parts=parts, operators=operators, data=data)


#: 긴 표(한 줄에 측정값 하나)의 머리글로 알아보는 이름들
_PART_KEYS = ("부품", "시료", "샘플", "품번", "제품", "part", "sample", "item")
_OP_KEYS = ("측정자", "작업자", "검사자", "평가자", "operator", "appraiser", "inspector")
_VALUE_KEYS = ("측정값", "측정치", "값", "결과", "value", "measurement", "result", "data")
_TRIAL_KEYS = ("반복", "횟수", "회차", "trial", "replicate", "rep")


def _find_col(header: list[str], keys: Sequence[str]) -> Optional[int]:
    norm = [h.strip().lower() for h in header]
    for key in keys:
        for i, h in enumerate(norm):
            if h == key or h.startswith(key):
                return i
    return None


def _to_float(text: str, where: str) -> float:
    t = text.strip().replace(" ", "")
    try:
        return float(t)
    except ValueError:
        raise ValueError(f"{where} 의 '{text}' 를 숫자로 읽을 수 없습니다.") from None


#: 넓은 표 머리글 "A-1", "A_2", "측정자1 3", "B1" -> (측정자, 회차)
_WIDE_HEAD = re.compile(r"^(.+?)\s*[-_/#.\s]\s*(\d+)$|^(.*?\D)(\d+)$")


def parse_table(text: str) -> Study:
    """CSV 나 엑셀에서 복사해 붙인 표를 읽는다.

    두 가지 모양을 받는다.

    긴 표 — 한 줄에 측정값 하나 ::

        부품,측정자,반복,측정값
        1,A,1,250.012
        1,A,2,250.010

    넓은 표 — 한 줄에 부품 하나, 칸마다 '측정자-회차' ::

        부품,A-1,A-2,A-3,B-1,B-2,B-3
        1,250.012,250.010,...
    """
    text = text.strip().lstrip("﻿")
    if not text:
        raise ValueError("데이터가 비어 있습니다.")
    first = text.splitlines()[0]
    if "\t" in first:
        delim = "\t"
    elif ";" in first and "," not in first:
        delim = ";"
    else:
        delim = ","
    table = [
        [c.strip() for c in row]
        for row in csv.reader(text.splitlines(), delimiter=delim)
        if any(c.strip() for c in row)
    ]
    if len(table) < 2:
        raise ValueError("머리글 한 줄과 데이터가 있어야 합니다.")
    header, body = table[0], table[1:]

    i_part = _find_col(header, _PART_KEYS)
    i_op = _find_col(header, _OP_KEYS)
    i_val = _find_col(header, _VALUE_KEYS)

    rows: list[tuple[str, str, float]] = []

    if i_part is not None and i_op is not None and i_val is not None:
        i_trial = _find_col(header, _TRIAL_KEYS)
        keyed = []
        for n, r in enumerate(body, start=2):
            if max(i_part, i_op, i_val) >= len(r) or not r[i_val]:
                continue
            trial = (_to_float(r[i_trial], f"{n}번째 줄")
                     if i_trial is not None and i_trial < len(r) and r[i_trial] else 0)
            keyed.append((trial, n, r[i_part], r[i_op],
                          _to_float(r[i_val], f"{n}번째 줄")))
        # 회차 칸이 있으면 회차 순서대로 (없으면 적힌 순서)
        keyed.sort(key=lambda k: (k[0], k[1]))
        rows = [(p, o, v) for _, _, p, o, v in keyed]
    else:
        # 넓은 표: 첫 칸이 부품, 나머지 머리글이 '측정자-회차'
        cols: list[tuple[int, str]] = []
        for j, h in enumerate(header[1:], start=1):
            m = _WIDE_HEAD.match(h)
            if not m:
                raise ValueError(
                    f"머리글 '{h}' 를 알아볼 수 없습니다. "
                    "긴 표는 '부품, 측정자, 측정값' 칸이, 넓은 표는 'A-1, A-2, B-1 …' "
                    "처럼 '측정자-회차' 머리글이 있어야 합니다."
                )
            op = (m.group(1) or m.group(3)).strip()
            cols.append((j, op))
        for n, r in enumerate(body, start=2):
            part = r[0]
            for j, op in cols:
                if j < len(r) and r[j]:
                    rows.append((part, op, _to_float(r[j], f"{n}번째 줄")))

    if not rows:
        raise ValueError("읽을 수 있는 측정값이 없습니다.")
    return build_study(rows)


def read_csv(path: str) -> Study:
    """CSV 파일을 읽는다. 엑셀이 저장한 CP949(ANSI) 파일도 받는다."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            with open(path, encoding=enc) as f:
                return parse_table(f.read())
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path} 의 글자 인코딩을 읽을 수 없습니다 (UTF-8 이나 CP949 로 저장).")


# ---------------------------------------------------------------------------
# 결과
# ---------------------------------------------------------------------------

@dataclass
class AnovaRow:
    source: str
    df: int
    ss: float
    ms: float
    f: Optional[float] = None
    p: Optional[float] = None


@dataclass
class GageResult:
    """분산 성분으로 정리한 결과. 단위는 측정값과 같다 (분산은 제곱)."""

    method: str                      # "ANOVA" | "평균·범위"
    study: Study
    var_ev: float                    # 반복성 σ²
    var_operator: float              # 측정자 σ²
    var_interaction: float           # 측정자×부품 σ²
    var_part: float                  # 부품간 σ²
    tolerance: Optional[float] = None
    process_sd: Optional[float] = None   # 공정 표준편차를 따로 알 때 (TV 대신)
    anova: list[AnovaRow] = field(default_factory=list)
    interaction_p: Optional[float] = None
    interaction_pooled: bool = False

    # --- 성분 -------------------------------------------------------------
    @property
    def var_av(self) -> float:
        return self.var_operator + self.var_interaction

    @property
    def var_grr(self) -> float:
        return self.var_ev + self.var_av

    @property
    def var_tv(self) -> float:
        if self.process_sd is not None:
            return self.process_sd ** 2
        return self.var_grr + self.var_part

    @property
    def ev(self) -> float:
        return math.sqrt(self.var_ev)

    @property
    def av(self) -> float:
        return math.sqrt(self.var_av)

    @property
    def grr(self) -> float:
        return math.sqrt(self.var_grr)

    @property
    def pv(self) -> float:
        if self.process_sd is not None:
            return math.sqrt(max(self.var_tv - self.var_grr, 0.0))
        return math.sqrt(self.var_part)

    @property
    def tv(self) -> float:
        return math.sqrt(self.var_tv)

    def components(self) -> list[tuple[str, float]]:
        """(이름, σ²) — 표와 그래프에 쓰는 순서."""
        out = [
            ("게이지 R&R", self.var_grr),
            ("  반복성 (EV)", self.var_ev),
            ("  재현성 (AV)", self.var_av),
        ]
        if self.method == "ANOVA" and not self.interaction_pooled:
            out += [("    측정자", self.var_operator),
                    ("    측정자×부품", self.var_interaction)]
        out += [("부품간 (PV)", self.pv ** 2), ("총변동 (TV)", self.var_tv)]
        return out

    # --- 비율 -------------------------------------------------------------
    def pct_study(self, var: float) -> float:
        """%연구변동 = σ / σ_TV."""
        return 100.0 * math.sqrt(var) / self.tv if self.tv > 0 else float("nan")

    def pct_contribution(self, var: float) -> float:
        """%기여도 = σ² / σ²_TV."""
        return 100.0 * var / self.var_tv if self.var_tv > 0 else float("nan")

    def pct_tolerance(self, var: float) -> Optional[float]:
        """%공차 = 6σ / (USL − LSL)."""
        if not self.tolerance:
            return None
        return 100.0 * STUDY_VAR_K * math.sqrt(var) / self.tolerance

    @property
    def pct_grr(self) -> float:
        return self.pct_study(self.var_grr)

    @property
    def pct_grr_tol(self) -> Optional[float]:
        return self.pct_tolerance(self.var_grr)

    @property
    def ndc(self) -> int:
        """구별 범주 수. AIAG: 1.41 × PV/GRR 를 버림, 최소 1."""
        if self.grr <= 0:
            return 99
        return max(1, int(math.floor(1.41 * self.pv / self.grr)))


def verdict_of(pct: Optional[float]) -> str:
    if pct is None or math.isnan(pct):
        return "-"
    if pct < LIMIT_OK:
        return "적합"
    if pct <= LIMIT_NG:
        return "조건부"
    return "부적합"


def overall_verdict(res: GageResult) -> tuple[str, list[str]]:
    """종합 판정과 그 이유. 가장 나쁜 항목을 따른다."""
    order = {"적합": 0, "조건부": 1, "부적합": 2}
    items = [("총변동 대비 %GRR", res.pct_grr)]
    if res.pct_grr_tol is not None:
        items.append(("공차 대비 %GRR", res.pct_grr_tol))
    worst = "적합"
    reasons = []
    for name, pct in items:
        v = verdict_of(pct)
        reasons.append(f"{name} {pct:.1f}% → {v}")
        if order[v] > order[worst]:
            worst = v
    if res.ndc < NDC_MIN:
        reasons.append(f"구별 범주 수 ndc = {res.ndc} (< {NDC_MIN}) → 제품 차이를 가르기 부족")
        if worst == "적합":
            worst = "조건부"
    else:
        reasons.append(f"구별 범주 수 ndc = {res.ndc} (≥ {NDC_MIN})")
    return worst, reasons


# ---------------------------------------------------------------------------
# ANOVA 법
# ---------------------------------------------------------------------------

def anova_method(
    study: Study,
    tolerance: Optional[float] = None,
    alpha_interaction: float = 0.05,
    process_sd: Optional[float] = None,
) -> GageResult:
    """2원 랜덤효과 ANOVA (부품 × 측정자, 교호작용 포함).

    교호작용의 p 값이 alpha_interaction 보다 크면 교호작용을 오차에 합쳐
    (pooling) 다시 계산한다. Minitab 의 기본값과 같은 0.05 를 쓴다.
    """
    p, o, n = study.n_parts, study.n_operators, study.trials
    vals = study.values()
    grand = sum(vals) / len(vals)

    pm = {pt: study.part_mean(pt) for pt in study.parts}
    om = {op: study.operator_mean(op) for op in study.operators}
    cm = {k: sum(v) / n for k, v in study.data.items()}

    ss_part = o * n * sum((m - grand) ** 2 for m in pm.values())
    ss_op = p * n * sum((m - grand) ** 2 for m in om.values())
    ss_cells = n * sum((m - grand) ** 2 for m in cm.values())
    ss_int = max(ss_cells - ss_part - ss_op, 0.0)
    ss_err = sum((v - cm[k]) ** 2 for k, vs in study.data.items() for v in vs)
    ss_tot = sum((v - grand) ** 2 for v in vals)

    df_part, df_op = p - 1, o - 1
    df_int, df_err = df_part * df_op, p * o * (n - 1)
    ms_part, ms_op = ss_part / df_part, ss_op / df_op
    ms_int, ms_err = ss_int / df_int, ss_err / df_err

    def ratio(a: float, b: float) -> float:
        if b > 0:
            return a / b
        return float("inf") if a > 0 else float("nan")

    f_int = ratio(ms_int, ms_err)
    p_int = f_pvalue(f_int, df_int, df_err)
    pooled = not (p_int <= alpha_interaction)   # nan 이어도 합친다

    if not pooled:
        f_part, f_op = ratio(ms_part, ms_int), ratio(ms_op, ms_int)
        table = [
            AnovaRow("부품", df_part, ss_part, ms_part, f_part,
                     f_pvalue(f_part, df_part, df_int)),
            AnovaRow("측정자", df_op, ss_op, ms_op, f_op,
                     f_pvalue(f_op, df_op, df_int)),
            AnovaRow("부품×측정자", df_int, ss_int, ms_int, f_int, p_int),
            AnovaRow("반복성(오차)", df_err, ss_err, ms_err),
            AnovaRow("합계", p * o * n - 1, ss_tot, float("nan")),
        ]
        var_ev = ms_err
        var_int = max((ms_int - ms_err) / n, 0.0)
        var_op = max((ms_op - ms_int) / (p * n), 0.0)
        var_part = max((ms_part - ms_int) / (o * n), 0.0)
    else:
        ss_e2, df_e2 = ss_err + ss_int, df_err + df_int
        ms_e2 = ss_e2 / df_e2
        f_part, f_op = ratio(ms_part, ms_e2), ratio(ms_op, ms_e2)
        table = [
            AnovaRow("부품", df_part, ss_part, ms_part, f_part,
                     f_pvalue(f_part, df_part, df_e2)),
            AnovaRow("측정자", df_op, ss_op, ms_op, f_op,
                     f_pvalue(f_op, df_op, df_e2)),
            AnovaRow("반복성(오차)", df_e2, ss_e2, ms_e2),
            AnovaRow("합계", p * o * n - 1, ss_tot, float("nan")),
        ]
        var_ev = ms_e2
        var_int = 0.0
        var_op = max((ms_op - ms_e2) / (p * n), 0.0)
        var_part = max((ms_part - ms_e2) / (o * n), 0.0)

    return GageResult(
        method="ANOVA", study=study, var_ev=var_ev, var_operator=var_op,
        var_interaction=var_int, var_part=var_part, tolerance=tolerance,
        process_sd=process_sd, anova=table, interaction_p=p_int,
        interaction_pooled=pooled,
    )


# ---------------------------------------------------------------------------
# 평균·범위 법 (AIAG MSA 4판 양식)
# ---------------------------------------------------------------------------

def xbar_r_method(
    study: Study,
    tolerance: Optional[float] = None,
    process_sd: Optional[float] = None,
) -> GageResult:
    """평균·범위 법. 측정자 수·부품 수가 15 를 넘으면 상수표가 없어 쓸 수 없다."""
    p, o, n = study.n_parts, study.n_operators, study.trials
    if p > 15 or o > 15:
        raise ValueError("평균·범위 법은 부품·측정자 15 이하에서만 계산합니다 (ANOVA 를 보세요).")

    r_bar_op = [
        sum(study.cell_range(pt, op) for pt in study.parts) / p
        for op in study.operators
    ]
    r_dbar = sum(r_bar_op) / o
    ev = r_dbar * k1(n)

    op_means = [study.operator_mean(op) for op in study.operators]
    x_diff = max(op_means) - min(op_means)
    av_sq = (x_diff * k_single(o)) ** 2 - ev ** 2 / (n * p)
    av_sq = max(av_sq, 0.0)

    part_means = [study.part_mean(pt) for pt in study.parts]
    rp = max(part_means) - min(part_means)
    pv = rp * k_single(p)

    return GageResult(
        method="평균·범위", study=study, var_ev=ev ** 2, var_operator=av_sq,
        var_interaction=0.0, var_part=pv ** 2, tolerance=tolerance,
        process_sd=process_sd,
    )


# ---------------------------------------------------------------------------
# 관리도 점검
# ---------------------------------------------------------------------------

@dataclass
class ChartCheck:
    r_bar: float
    ucl_r: float
    lcl_r: float
    x_bar: float
    ucl_x: float
    lcl_x: float
    out_r: list[tuple[str, str, float]]       # (부품, 측정자, 범위) — UCL 넘은 것
    pct_x_outside: float                      # X̄ 관리도 밖에 있는 점의 비율 [%]


def chart_check(study: Study) -> ChartCheck:
    """R 관리도: 점이 UCL 을 넘으면 그 반복 측정이 튄 것이다 (재측정 대상).
    X̄ 관리도: 점이 한계 '밖' 에 많을수록 좋다 (부품 차이를 잘 가른다는 뜻,
    AIAG 는 절반 이상을 권한다)."""
    n = study.trials
    ranges = {k: max(v) - min(v) for k, v in study.data.items()}
    r_bar = sum(ranges.values()) / len(ranges)
    means = {k: sum(v) / n for k, v in study.data.items()}
    x_bar = sum(means.values()) / len(means)
    ucl_r, lcl_r = _D4[n] * r_bar, _D3_CHART[n] * r_bar
    ucl_x, lcl_x = x_bar + _A2[n] * r_bar, x_bar - _A2[n] * r_bar
    out_r = [(p, o, r) for (p, o), r in ranges.items() if r > ucl_r + 1e-12]
    outside = sum(1 for m in means.values() if m > ucl_x or m < lcl_x)
    return ChartCheck(
        r_bar=r_bar, ucl_r=ucl_r, lcl_r=lcl_r, x_bar=x_bar, ucl_x=ucl_x,
        lcl_x=lcl_x, out_r=out_r, pct_x_outside=100.0 * outside / len(means),
    )


# ---------------------------------------------------------------------------
# 글자 보고서
# ---------------------------------------------------------------------------

def _fmt(x: Optional[float], digits: int = 5) -> str:
    if x is None or math.isnan(x):
        return ""
    if math.isinf(x):
        return "∞"
    return f"{x:.{digits}g}"


def format_gagerr_report(res: GageResult, xr: Optional[GageResult] = None) -> str:
    s = res.study
    lines = [
        "=" * 64,
        f" 게이지 R&R ({res.method} 법)",
        "=" * 64,
        f" 부품 {s.n_parts}개 × 측정자 {s.n_operators}명 × 반복 {s.trials}회"
        f" = {s.n_parts * s.n_operators * s.trials}개 측정값",
    ]
    if res.tolerance:
        lines.append(f" 공차 (USL−LSL) = {_fmt(res.tolerance)}")
    lines.append("")

    if res.anova:
        lines.append(" ANOVA 표")
        lines.append(f" {'요인':<12}{'자유도':>6}{'SS':>13}{'MS':>13}{'F':>10}{'p':>9}")
        for r in res.anova:
            p_txt = "" if r.p is None else f"{r.p:.3f}"
            lines.append(
                f" {r.source:<12}{r.df:>6}{_fmt(r.ss):>13}{_fmt(r.ms):>13}"
                f"{_fmt(r.f, 4):>10}{p_txt:>9}"
            )
        if res.interaction_pooled:
            lines.append(
                f" ※ 부품×측정자 교호작용 p = {res.interaction_p:.3f} 이 커서"
                " 오차에 합쳤다."
            )
        lines.append("")

    head = f" {'성분':<16}{'σ':>11}{'%기여도':>9}{'%연구변동':>10}"
    if res.tolerance:
        head += f"{'%공차':>8}"
    lines.append(head)
    for name, var in res.components():
        row = (f" {name:<16}{_fmt(math.sqrt(var)):>11}"
               f"{res.pct_contribution(var):>9.2f}{res.pct_study(var):>10.2f}")
        if res.tolerance:
            row += f"{res.pct_tolerance(var):>8.2f}"
        lines.append(row)
    lines.append("")

    verdict, reasons = overall_verdict(res)
    lines.append(f" 판정: {verdict}")
    for r in reasons:
        lines.append(f"   - {r}")

    cc = chart_check(s)
    if cc.out_r:
        lines.append(
            "   - R 관리도 UCL 을 넘은 반복 측정 "
            + ", ".join(f"{p}/{o}" for p, o, _ in cc.out_r)
            + " → 그 조합은 다시 재 볼 것"
        )
    lines.append(
        f"   - X̄ 관리도 한계 밖 점 {cc.pct_x_outside:.0f}% "
        + ("(50% 이상: 부품 차이를 잘 가른다)" if cc.pct_x_outside >= 50
           else "(50% 미만: 부품 차이에 비해 측정 흩어짐이 크다)")
    )

    if xr is not None:
        lines += [
            "",
            " 참고 — 평균·범위 법",
            f"   EV {_fmt(xr.ev)}   AV {_fmt(xr.av)}   GRR {_fmt(xr.grr)}"
            f"   PV {_fmt(xr.pv)}   TV {_fmt(xr.tv)}",
            f"   %GRR {xr.pct_grr:.1f}%   ndc {xr.ndc}",
        ]
    lines.append("=" * 64)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SVG 그래프 (내장 기능만)
# ---------------------------------------------------------------------------

#: 측정자별 색. 화면 쪽 CSS 가 --s1.. 을 밝은/어두운 화면에 맞게 정한다.
#: 3개까지는 색약에서도 서로 구별되는 조합이다. 그 이상은 점 모양으로도 구별한다.
_SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)",
           "var(--s5)", "var(--s6)", "var(--s7)", "var(--s8)"]
_MARKERS = ["circle", "square", "diamond", "triangle"]


def _xml_esc(t: object) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + (abs(lo) * 0.01 or 1.0)
    raw = (hi - lo) / count
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    i0, i1 = math.floor(lo / step + 1e-9), math.ceil(hi / step - 1e-9)
    return [round(i * step, 12) for i in range(i0, i1 + 1)]


def _tick_text(v: float, ticks: list[float]) -> str:
    step = abs(ticks[1] - ticks[0]) if len(ticks) > 1 else 1.0
    dec = 0
    while dec < 6 and abs(round(step, dec) - step) > step * 1e-6:
        dec += 1
    return f"{v:.{dec}f}"


def _marker(kind: str, x: float, y: float, color: str, tip: str) -> str:
    title = f"<title>{_xml_esc(tip)}</title>"
    ring = 'stroke="var(--panel)" stroke-width="2"'
    if kind == "square":
        return (f'<rect x="{x - 4:.1f}" y="{y - 4:.1f}" width="8" height="8" '
                f'fill="{color}" {ring}>{title}</rect>')
    if kind == "diamond":
        return (f'<path d="M{x:.1f},{y - 5.5:.1f} L{x + 5.5:.1f},{y:.1f} '
                f'L{x:.1f},{y + 5.5:.1f} L{x - 5.5:.1f},{y:.1f}Z" fill="{color}" '
                f'{ring}>{title}</path>')
    if kind == "triangle":
        return (f'<path d="M{x:.1f},{y - 5.5:.1f} L{x + 5:.1f},{y + 4:.1f} '
                f'L{x - 5:.1f},{y + 4:.1f}Z" fill="{color}" {ring}>{title}</path>')
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" '
            f'{ring}>{title}</circle>')


class _Frame:
    """축 하나짜리 그래프 틀."""

    W, H = 560, 300
    L, R, T, B = 74, 16, 14, 46

    def __init__(self, y_lo: float, y_hi: float, n_x: int, y_label: str = "",
                 floor: Optional[float] = None):
        pad = (y_hi - y_lo) * 0.08 or (abs(y_hi) * 0.01 or 1.0)
        lo = y_lo - pad if floor is None else max(y_lo - pad, floor)
        self.ticks = _nice_ticks(lo, y_hi + pad)
        self.y0, self.y1 = self.ticks[0], self.ticks[-1]
        self.n_x = n_x
        self.y_label = y_label
        self.parts: list[str] = []
        self._label_ys: list[float] = []
        self.labels: list[str] = []

    def x(self, i: float) -> float:
        span = self.W - self.L - self.R
        return self.L + span * (i + 0.5) / self.n_x

    def y(self, v: float) -> float:
        span = self.H - self.T - self.B
        return self.T + span * (1 - (v - self.y0) / (self.y1 - self.y0))

    def grid(self) -> None:
        for t in self.ticks:
            yy = self.y(t)
            self.parts.append(
                f'<line x1="{self.L}" x2="{self.W - self.R}" y1="{yy:.1f}" y2="{yy:.1f}" '
                f'stroke="var(--line)" stroke-width="1"/>'
                f'<text x="{self.L - 6}" y="{yy + 4:.1f}" text-anchor="end" '
                f'font-size="11" fill="var(--ink3)">{_tick_text(t, self.ticks)}</text>'
            )
        if self.y_label:
            self.parts.append(
                f'<text x="12" y="{(self.T + self.H - self.B) / 2:.0f}" font-size="11" '
                f'fill="var(--ink2)" text-anchor="middle" '
                f'transform="rotate(-90 12 {(self.T + self.H - self.B) / 2:.0f})">'
                f'{_xml_esc(self.y_label)}</text>'
            )

    def hline(self, v: float, label: str, dash: str = "5 4", strong: bool = False) -> None:
        yy = self.y(v)
        color = "var(--ink2)" if strong else "var(--ink3)"
        # 기준선끼리 가까우면 글자가 겹친다. 이미 쓴 글자와 12px 이상 떨어뜨린다.
        ty = yy - 4
        for _ in range(len(self._label_ys) + 1):
            hit = [u for u in self._label_ys if abs(u - ty) < 12]
            if not hit:
                break
            ty = max(hit) + 12 if ty >= yy - 4 else min(hit) - 12
        self._label_ys.append(ty)
        self.parts.append(
            f'<line x1="{self.L}" x2="{self.W - self.R}" y1="{yy:.1f}" y2="{yy:.1f}" '
            f'stroke="{color}" stroke-width="1.2" stroke-dasharray="{dash}"/>'
        )
        # 글자는 맨 위에 그리도록 따로 모아 둔다 (막대·점에 가리지 않게)
        self.labels.append(
            f'<text x="{self.W - self.R - 3}" y="{ty:.1f}" text-anchor="end" '
            f'font-size="10.5" fill="var(--ink2)" stroke="var(--panel)" '
            f'stroke-width="3" paint-order="stroke">{_xml_esc(label)}</text>'
        )

    def svg(self, extra_bottom: str = "") -> str:
        return (
            f'<svg viewBox="0 0 {self.W} {self.H}" width="100%" role="img" '
            f'style="display:block;font-family:inherit">'
            + "".join(self.parts) + "".join(self.labels) + extra_bottom + "</svg>"
        )


def legend_html(study: Study) -> str:
    items = []
    for i, op in enumerate(study.operators):
        color = _SERIES[i % len(_SERIES)]
        kind = _MARKERS[i % len(_MARKERS)]
        mk = _marker(kind, 8, 8, color, op)
        items.append(
            f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px">'
            f'<svg width="16" height="16" viewBox="0 0 16 16">{mk}</svg>{_xml_esc(op)}</span>'
        )
    return f'<div style="font-size:12px;color:var(--ink2);margin:2px 0 6px">{"".join(items)}</div>'


def components_svg(res: GageResult) -> str:
    """성분별 %기여도·%연구변동·%공차 막대 그래프 (10%·30% 기준선 포함)."""
    groups = [
        ("게이지 R&R", res.var_grr),
        ("반복성", res.var_ev),
        ("재현성", res.var_av),
        ("부품간", res.pv ** 2),
    ]
    series = [("%기여도", res.pct_contribution, "var(--s1)"),
              ("%연구변동", res.pct_study, "var(--s2)")]
    if res.tolerance:
        series.append(("%공차", res.pct_tolerance, "var(--s3)"))

    top = max([110.0] + [fn(v) or 0 for _, v in groups for _, fn, _ in series])
    fr = _Frame(0, top, len(groups), "%")
    fr.ticks = [t for t in _nice_ticks(0, top)]
    fr.y0, fr.y1 = 0.0, fr.ticks[-1]
    fr.grid()
    fr.hline(LIMIT_OK, "10%")
    fr.hline(LIMIT_NG, "30%")

    slot = (fr.W - fr.L - fr.R) / len(groups)
    bw = min(34.0, (slot - 18) / len(series) - 2)
    for gi, (name, var) in enumerate(groups):
        cx = fr.x(gi)
        x0 = cx - (bw + 2) * len(series) / 2
        for si, (sname, fn, color) in enumerate(series):
            val = fn(var) or 0.0
            yy = fr.y(val)
            base = fr.y(0)
            h = max(base - yy, 0.0)
            bx = x0 + si * (bw + 2) + 1
            r = min(4.0, h)
            # 위쪽만 둥근 막대
            path = (f"M{bx:.1f},{base:.1f} L{bx:.1f},{yy + r:.1f} "
                    f"Q{bx:.1f},{yy:.1f} {bx + r:.1f},{yy:.1f} "
                    f"L{bx + bw - r:.1f},{yy:.1f} Q{bx + bw:.1f},{yy:.1f} "
                    f"{bx + bw:.1f},{yy + r:.1f} L{bx + bw:.1f},{base:.1f}Z")
            fr.parts.append(
                f'<path d="{path}" fill="{color}"><title>{_xml_esc(name)} {sname} '
                f'{val:.1f}%</title></path>'
            )
        fr.parts.append(
            f'<text x="{cx:.1f}" y="{fr.H - fr.B + 18}" text-anchor="middle" '
            f'font-size="12" fill="var(--ink2)">{_xml_esc(name)}</text>'
        )
    fr.parts.append(
        f'<line x1="{fr.L}" x2="{fr.W - fr.R}" y1="{fr.y(0):.1f}" y2="{fr.y(0):.1f}" '
        f'stroke="var(--ink3)" stroke-width="1"/>'
    )
    legend = "".join(
        f'<rect x="{fr.L + i * 96}" y="{fr.H - 16}" width="10" height="10" rx="2" '
        f'fill="{c}"/><text x="{fr.L + i * 96 + 14}" y="{fr.H - 7}" font-size="11" '
        f'fill="var(--ink2)">{_xml_esc(n)}</text>'
        for i, (n, _, c) in enumerate(series)
    )
    return fr.svg(legend)


def _by_operator_svg(study: Study, values: dict, center: float, ucl: float,
                     lcl: float, y_label: str, what: str,
                     floor: Optional[float] = None) -> str:
    """측정자별로 칸을 나눠 부품 순서대로 점을 찍는 관리도."""
    p, o = study.n_parts, study.n_operators
    gap = 1
    n_x = o * p + gap * (o - 1)
    vals = list(values.values())
    fr = _Frame(min(vals + [lcl, center]), max(vals + [ucl, center]), n_x, y_label,
                floor)
    fr.grid()
    fr.hline(ucl, f"UCL {_fmt(ucl, 6)}")
    fr.hline(center, f"중심 {_fmt(center, 6)}", dash="0", strong=True)
    if lcl >= fr.y0:
        fr.hline(lcl, f"LCL {_fmt(lcl, 6)}")

    for oi, op in enumerate(study.operators):
        color = _SERIES[oi % len(_SERIES)]
        kind = _MARKERS[oi % len(_MARKERS)]
        xs = [oi * (p + gap) + pi for pi in range(p)]
        pts = [(fr.x(x), fr.y(values[(pt, op)])) for x, pt in zip(xs, study.parts)]
        fr.parts.append(
            '<polyline fill="none" stroke="' + color + '" stroke-width="2" points="'
            + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + '"/>'
        )
        for (a, b), pt in zip(pts, study.parts):
            fr.parts.append(_marker(kind, a, b, color,
                                    f"{op} · 부품 {pt} · {what} {_fmt(values[(pt, op)])}"))
        mid = (fr.x(xs[0]) + fr.x(xs[-1])) / 2
        fr.parts.append(
            f'<text x="{mid:.1f}" y="{fr.H - fr.B + 18}" text-anchor="middle" '
            f'font-size="12" fill="var(--ink2)">측정자 {_xml_esc(op)}</text>'
        )
    return fr.svg()


def r_chart_svg(study: Study) -> str:
    cc = chart_check(study)
    ranges = {k: max(v) - min(v) for k, v in study.data.items()}
    return _by_operator_svg(study, ranges, cc.r_bar, cc.ucl_r, cc.lcl_r, "범위 R", "범위",
                            floor=0.0)


def xbar_chart_svg(study: Study) -> str:
    cc = chart_check(study)
    means = {k: sum(v) / len(v) for k, v in study.data.items()}
    return _by_operator_svg(study, means, cc.x_bar, cc.ucl_x, cc.lcl_x, "평균 X̄", "평균")


def interaction_svg(study: Study) -> str:
    """부품별 측정자 평균. 선이 나란하면 교호작용이 없다."""
    means = {k: sum(v) / len(v) for k, v in study.data.items()}
    vals = list(means.values())
    fr = _Frame(min(vals), max(vals), study.n_parts, "평균")
    fr.grid()
    for oi, op in enumerate(study.operators):
        color = _SERIES[oi % len(_SERIES)]
        kind = _MARKERS[oi % len(_MARKERS)]
        pts = [(fr.x(i), fr.y(means[(pt, op)])) for i, pt in enumerate(study.parts)]
        fr.parts.append(
            '<polyline fill="none" stroke="' + color + '" stroke-width="2" points="'
            + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + '"/>'
        )
        for (a, b), pt in zip(pts, study.parts):
            fr.parts.append(_marker(kind, a, b, color,
                                    f"{op} · 부품 {pt} · 평균 {_fmt(means[(pt, op)])}"))
    for i, pt in enumerate(study.parts):
        fr.parts.append(
            f'<text x="{fr.x(i):.1f}" y="{fr.H - fr.B + 18}" text-anchor="middle" '
            f'font-size="11.5" fill="var(--ink2)">{_xml_esc(pt)}</text>'
        )
    fr.parts.append(
        f'<text x="{(fr.L + fr.W - fr.R) / 2:.0f}" y="{fr.H - 8}" text-anchor="middle" '
        f'font-size="11" fill="var(--ink3)">부품</text>'
    )
    return fr.svg()


def by_part_svg(study: Study) -> str:
    """부품별 측정값 전체 (점) 과 부품 평균 (가로선)."""
    vals = study.values()
    fr = _Frame(min(vals), max(vals), study.n_parts, "측정값")
    fr.grid()
    o = study.n_operators
    for i, pt in enumerate(study.parts):
        cx = fr.x(i)
        slot = (fr.W - fr.L - fr.R) / study.n_parts
        for oi, op in enumerate(study.operators):
            color = _SERIES[oi % len(_SERIES)]
            kind = _MARKERS[oi % len(_MARKERS)]
            dx = (oi - (o - 1) / 2) * min(9.0, slot / (o + 1))
            for t, v in enumerate(study.data[(pt, op)], start=1):
                fr.parts.append(_marker(kind, cx + dx, fr.y(v), color,
                                        f"부품 {pt} · {op} · {t}회 · {_fmt(v)}"))
        m = study.part_mean(pt)
        fr.parts.append(
            f'<line x1="{cx - slot * 0.38:.1f}" x2="{cx + slot * 0.38:.1f}" '
            f'y1="{fr.y(m):.1f}" y2="{fr.y(m):.1f}" stroke="var(--ink)" stroke-width="2">'
            f'<title>부품 {_xml_esc(pt)} 평균 {_fmt(m)}</title></line>'
        )
        fr.parts.append(
            f'<text x="{cx:.1f}" y="{fr.H - fr.B + 18}" text-anchor="middle" '
            f'font-size="11.5" fill="var(--ink2)">{_xml_esc(pt)}</text>'
        )
    fr.parts.append(
        f'<text x="{(fr.L + fr.W - fr.R) / 2:.0f}" y="{fr.H - 8}" text-anchor="middle" '
        f'font-size="11" fill="var(--ink3)">부품</text>'
    )
    return fr.svg()


# ---------------------------------------------------------------------------
# 예제 데이터
# ---------------------------------------------------------------------------

#: 임펠러 외경 [mm] — 임펠러 10개, 측정자 3명(A·B·C), 3회씩.
#: 도면 치수 Ø250.00 ±0.05 (공차 0.10 mm). 웹 화면이 처음 열릴 때 쓴다.
EXAMPLE_CSV = """부품,A-1,A-2,A-3,B-1,B-2,B-3,C-1,C-2,C-3
1,250.012,250.016,250.013,250.019,250.015,250.021,250.010,250.008,250.013
2,249.981,249.985,249.979,249.988,249.990,249.984,249.979,249.976,249.982
3,250.031,250.027,250.030,250.036,250.034,250.038,250.028,250.031,250.026
4,250.004,250.001,250.007,250.010,250.006,250.009,250.000,250.003,249.999
5,249.968,249.972,249.970,249.977,249.973,249.979,249.966,249.969,249.965
6,250.022,250.019,250.024,250.027,250.030,250.025,250.017,250.021,250.020
7,249.994,249.990,249.993,250.000,249.997,250.002,249.989,249.992,249.987
8,250.040,250.044,250.041,250.048,250.045,250.043,250.037,250.039,250.042
9,249.959,249.955,249.960,249.964,249.968,249.963,249.953,249.956,249.958
10,250.009,250.006,250.011,250.015,250.012,250.017,250.003,250.007,250.005
"""
EXAMPLE_LSL = 249.95
EXAMPLE_USL = 250.05


# ---------------------------------------------------------------------------
# 명령줄
# ---------------------------------------------------------------------------

def _tolerance(lsl: Optional[float], usl: Optional[float],
               tol: Optional[float]) -> Optional[float]:
    if tol is not None:
        if tol <= 0:
            raise ValueError("공차는 0 보다 커야 합니다.")
        return tol
    if lsl is not None and usl is not None:
        if usl <= lsl:
            raise ValueError("상한(USL)이 하한(LSL)보다 커야 합니다.")
        return usl - lsl
    return None


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m turbochiller.gagerr",
        description="게이지 R&R (AIAG MSA) — ANOVA 법과 평균·범위 법",
    )
    ap.add_argument("csv", nargs="?", help="측정 데이터 CSV (없으면 예제 데이터)")
    ap.add_argument("--lsl", type=float, help="규격 하한")
    ap.add_argument("--usl", type=float, help="규격 상한")
    ap.add_argument("--tol", type=float, help="공차 폭 (USL−LSL). --lsl/--usl 대신")
    ap.add_argument("--process-sd", type=float,
                    help="공정 표준편차를 따로 알 때 (총변동 대신 씀)")
    ap.add_argument("--alpha", type=float, default=0.05,
                    help="교호작용을 오차에 합치는 기준 p 값 (기본 0.05)")
    args = ap.parse_args(argv)

    try:
        if args.csv:
            study = read_csv(args.csv)
            tol = _tolerance(args.lsl, args.usl, args.tol)
        else:
            print("(데이터 파일을 안 줘서 예제 — 임펠러 외경 — 로 계산합니다)\n")
            study = parse_table(EXAMPLE_CSV)
            tol = _tolerance(args.lsl, args.usl, args.tol) or (EXAMPLE_USL - EXAMPLE_LSL)
        res = anova_method(study, tol, args.alpha, args.process_sd)
        try:
            xr = xbar_r_method(study, tol, args.process_sd)
        except ValueError:
            xr = None
    except (OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    print(format_gagerr_report(res, xr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
