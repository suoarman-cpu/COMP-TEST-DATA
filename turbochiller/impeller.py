"""터보(원심) 압축기 임펠러 개략 설계.

사이클 해석에서 나온 '단열 일(헤드)'과 '흡입 체적유량'만 있으면
임펠러 외경·회전수·주속·마하수를 1차 근사로 잡을 수 있다.

쓰는 무차원수
    압력(헤드)계수   psi = dh_is / u2^2              통상 0.50 ~ 0.65
    비속도          Ns  = w * sqrt(Q) / dh_is^0.75   최적 0.6 ~ 0.8
    유량계수        phi = Q / (u2 * D2^2)            통상 0.02 ~ 0.15
    선단 마하수      Mu2 = u2 / a1

여기 나오는 값은 어디까지나 '초기 치수 잡기'용이다.
실제 설계는 깃 형상·확산기·CFD 로 다시 확인해야 한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Optional

from . import props
from .cycle import StageResult

#: 원심 압축기 1단의 통상 설계 범위 (경고 판정용)
LIMITS = {
    "psi": (0.45, 0.70),
    "specific_speed": (0.4, 1.0),
    "flow_coefficient": (0.01, 0.16),
    "tip_mach": (0.0, 1.5),
    "tip_speed": (0.0, 420.0),   # [m/s] 알루미늄 임펠러 기준 대략적인 상한
}


@dataclass
class ImpellerSizing:
    """임펠러 개략 치수."""

    stage_name: str
    dh_isentropic: float        # 단열 헤드 [kJ/kg]
    dh_actual: float            # 실제 엔탈피 상승 [kJ/kg]
    volume_flow: float          # 흡입 체적유량 [m3/s]
    rpm: float                  # 회전수 [rpm]
    tip_speed: float            # 임펠러 선단 주속 u2 [m/s]
    diameter: float             # 임펠러 외경 D2 [m]
    eye_diameter: float         # 흡입구(아이) 외경 추정 [m]
    head_coefficient: float     # psi
    work_coefficient: float     # lambda = dh_actual / u2^2
    specific_speed: float       # Ns
    specific_diameter: float    # Ds
    flow_coefficient: float     # phi
    tip_mach: float             # Mu2 (선단)
    eye_mach: float             # 흡입구 축방향 마하수
    inlet_sound_speed: float    # [m/s]
    warnings: list[str]

    @property
    def diameter_mm(self) -> float:
        return self.diameter * 1000.0

    @property
    def eye_diameter_mm(self) -> float:
        return self.eye_diameter * 1000.0


@dataclass
class Given:
    """미리 정해 놓고 들어가는 값들.

    psi(압력계수) · rpm(회전수) · diameter(외경) 셋은 아래 관계로 묶여 있다.

        u2 = sqrt(dh_is / psi)          헤드가 주속을 정한다
        u2 = omega * D2 / 2             주속 = 각속도 x 반지름

    그래서 셋 중 **둘을 정하면 나머지 하나는 따라 나온다.**
    하나만 정하거나 아무것도 안 정하면 비속도(Ns)로 회전수를 잡는다.

    흡입구 외경(eye_diameter)은 따로다. 정해 주면 흡입 축방향 마하수가
    역산되고, 안 정하면 목표 마하수에서 외경이 나온다.
    """

    head_coefficient: Optional[float] = None    # psi [-]
    rpm: Optional[float] = None                 # 축 회전수 [rpm]
    diameter: Optional[float] = None            # 임펠러 외경 [m]
    eye_diameter: Optional[float] = None        # 흡입구 외경 [m]

    specific_speed: float = 0.70                # 아무것도 안 정했을 때 쓸 Ns
    default_head_coefficient: float = 0.60      # psi 를 안 정했을 때
    eye_hub_ratio: float = 0.35                 # 흡입구 허브/팁 비
    inlet_axial_mach: float = 0.30              # 흡입구 축방향 마하수 목표

    @property
    def fixed_count(self) -> int:
        return sum(
            v is not None
            for v in (self.head_coefficient, self.rpm, self.diameter)
        )


def size_impeller(
    stage: StageResult,
    refrigerant: str,
    given: Optional[Given] = None,
) -> ImpellerSizing:
    """임펠러 한 단의 치수를 개략 산정한다.

    주의: 여러 단짜리 압축기는 이 함수를 단마다 따로 부르면 안 된다.
    단일축 직결이면 모든 단의 회전수가 같아야 하는데, 단마다 부르면
    단별 최적 비속도에 맞춘 '서로 다른 회전수' 가 나와 버린다.
    그럴 때는 size_machine() 을 쓸 것.
    """
    g = given or Given()
    warnings: list[str] = []

    dh_is_j = stage.dh_isentropic * 1000.0          # [J/kg]
    q = stage.mass_flow / stage.suction_density      # [m3/s]
    if q <= 0:
        raise ValueError("흡입 체적유량이 0 이하다")
    if dh_is_j <= 0:
        raise ValueError("단열 헤드가 0 이하다")

    psi, rpm, d2 = g.head_coefficient, g.rpm, g.diameter

    if g.fixed_count >= 3:
        warnings.append(
            "psi·회전수·외경을 셋 다 지정했다. 셋은 서로 묶여 있어서 "
            "보통 둘만 정하면 된다. 여기서는 회전수와 외경을 쓰고 "
            "psi 는 그 둘에서 역산했다"
        )
        psi = None

    # --- psi / rpm / D2 를 서로 풀어낸다 -----------------------------------
    if rpm is not None and d2 is not None:
        # 회전수와 외경이 정해졌다 -> 낼 수 있는 주속이 정해지고, psi 가 따라 나온다
        omega = rpm * 2.0 * math.pi / 60.0
        u2 = omega * d2 / 2.0
        psi = dh_is_j / u2**2
        if psi > LIMITS["psi"][1]:
            warnings.append(
                f"이 회전수·외경으로는 psi 가 {psi:.3f} 나 필요하다. "
                f"임펠러가 헤드를 못 낸다 (보통 {LIMITS['psi'][1]} 이하). "
                "회전수를 올리거나 외경을 키울 것"
            )
    else:
        if psi is None:
            psi = g.default_head_coefficient
        if psi <= 0:
            raise ValueError("압력계수(psi)는 0보다 커야 한다")
        u2 = math.sqrt(dh_is_j / psi)

        if rpm is not None:
            omega = rpm * 2.0 * math.pi / 60.0
            d2 = 2.0 * u2 / omega
        elif d2 is not None:
            omega = 2.0 * u2 / d2
            rpm = omega * 60.0 / (2.0 * math.pi)
        else:
            # 아무것도 안 정했다 -> 비속도로 회전수를 잡는다
            omega = g.specific_speed * dh_is_j**0.75 / math.sqrt(q)
            rpm = omega * 60.0 / (2.0 * math.pi)
            d2 = 2.0 * u2 / omega

    ns = omega * math.sqrt(q) / dh_is_j**0.75
    ds = d2 * dh_is_j**0.25 / math.sqrt(q)
    phi = q / (u2 * d2**2)

    a1 = props.a_tp(refrigerant, stage.t_in, stage.p_in)
    mu2 = u2 / a1

    # --- 흡입구 ---
    if g.eye_diameter is not None:
        d_eye = g.eye_diameter
        area = math.pi / 4.0 * d_eye**2 * (1.0 - g.eye_hub_ratio**2)
        c_axial = q / area if area > 0 else float("inf")
        eye_mach = c_axial / a1
        if eye_mach > 0.45:
            warnings.append(
                f"흡입구 축방향 마하수가 {eye_mach:.2f} 다. 너무 빠르다 "
                "(0.25~0.35 가 보통). 초킹으로 유량이 막힐 수 있으니 "
                "흡입구를 키울 것"
            )
        elif eye_mach < 0.12:
            warnings.append(
                f"흡입구 축방향 마하수가 {eye_mach:.2f} 로 낮다. "
                "흡입구가 필요 이상으로 크다"
            )
    else:
        eye_mach = g.inlet_axial_mach
        c_axial = eye_mach * a1
        area = q / c_axial
        d_eye = math.sqrt(4.0 * area / (math.pi * (1.0 - g.eye_hub_ratio**2)))

    _check(warnings, "압력계수 psi", psi, *LIMITS["psi"])
    _check(warnings, "비속도 Ns", ns, *LIMITS["specific_speed"])
    _check(warnings, "유량계수 phi", phi, *LIMITS["flow_coefficient"])
    _check(warnings, "선단 마하수 Mu2", mu2, *LIMITS["tip_mach"])
    _check(warnings, "선단 주속 u2 [m/s]", u2, *LIMITS["tip_speed"])
    if d_eye >= d2:
        warnings.append(
            f"흡입구 외경({d_eye * 1000:.0f} mm)이 임펠러 외경"
            f"({d2 * 1000:.0f} mm)보다 크다 — 단수를 늘리거나 유량을 나눌 것"
        )

    return ImpellerSizing(
        stage_name=stage.name,
        dh_isentropic=stage.dh_isentropic,
        dh_actual=stage.dh_actual,
        volume_flow=q,
        rpm=rpm,
        tip_speed=u2,
        diameter=d2,
        eye_diameter=d_eye,
        eye_mach=eye_mach,
        head_coefficient=psi,
        work_coefficient=stage.dh_actual * 1000.0 / u2**2,
        specific_speed=ns,
        specific_diameter=ds,
        flow_coefficient=phi,
        tip_mach=mu2,
        inlet_sound_speed=a1,
        warnings=warnings,
    )


@dataclass
class MachineSizing:
    """압축기 한 대(여러 단)의 개략 치수.

    단일축 직결이면 모든 단이 같은 회전수로 돌아간다.
    """

    rpm: float
    drive: str                      # "단일축 직결" 또는 "기어 내장형"
    stages: list[ImpellerSizing]
    warnings: list[str]

    @property
    def largest_diameter_mm(self) -> float:
        return max(s.diameter_mm for s in self.stages)


def size_machine(
    result,
    given: Optional[Given] = None,
    stage_diameters: Optional[list[Optional[float]]] = None,
    stage_eye_diameters: Optional[list[Optional[float]]] = None,
    geared: bool = False,
) -> MachineSizing:
    """압축기 한 대(여러 단)를 통째로 개략 산정한다.

    result              : cycle.solve() 가 돌려준 사이클 결과
    given               : 미리 정해 둔 값 (회전수·psi·외경 등)
    stage_diameters     : 단별 임펠러 외경 [m]. 주면 given.diameter 보다 우선한다
    stage_eye_diameters : 단별 흡입구 외경 [m]
    geared              : True 면 기어 내장형으로 보고 단마다 회전수를 따로 잡는다

    터보 냉동기의 2단 압축기는 보통 임펠러 두 개가 한 축에 직결이라
    회전수가 같다. 그래서 기본값은 단일축이다.
    """
    stages = result.stage_results
    if not stages:
        raise ValueError("압축기 단 정보가 없다")

    g = given or Given()
    fluid = result.refrigerant
    warnings: list[str] = []

    def per_stage(i: int, rpm: Optional[float]) -> Given:
        d = None
        if stage_diameters and i < len(stage_diameters):
            d = stage_diameters[i]
        if d is None and i == 0:
            d = g.diameter
        eye = None
        if stage_eye_diameters and i < len(stage_eye_diameters):
            eye = stage_eye_diameters[i]
        if eye is None and i == 0:
            eye = g.eye_diameter
        return replace(g, rpm=rpm, diameter=d, eye_diameter=eye)

    if geared:
        sizings = [
            size_impeller(st, fluid, per_stage(i, g.rpm))
            for i, st in enumerate(stages)
        ]
        if len({round(s.rpm) for s in sizings}) > 1:
            warnings.append(
                "기어 내장형으로 계산했다. 단별 회전수가 다르므로 "
                "실제로 증속기어가 단마다 따로 있는 구조여야 한다"
            )
        drive = "기어 내장형"
    else:
        # --- 단일축: 회전수를 하나로 정한다 ---
        rpm = g.rpm
        if rpm is None:
            # 1단은 체적유량이 가장 커서 회전수를 지배한다. 여기에 맞춘다.
            rpm = size_impeller(stages[0], fluid, per_stage(0, None)).rpm
        sizings = [
            size_impeller(st, fluid, per_stage(i, rpm))
            for i, st in enumerate(stages)
        ]
        drive = "단일축 직결"

        if len(sizings) > 1:
            ns_min = min(s.specific_speed for s in sizings)
            if ns_min < LIMITS["specific_speed"][0]:
                warnings.append(
                    f"축 회전수를 하나로 묶으니 뒷단 비속도가 {ns_min:.2f} 까지 "
                    "떨어진다. 뒷단 효율이 낮아지므로, 회전수를 올리거나 "
                    "뒷단 압력계수(psi)를 달리 잡는 것을 검토할 것"
                )

    for sz in sizings:
        warnings.extend(f"{sz.stage_name}: {w}" for w in sz.warnings)

    return MachineSizing(
        rpm=sizings[0].rpm, drive=drive, stages=sizings, warnings=warnings
    )


def _check(bucket: list[str], label: str, value: float, low: float, high: float) -> None:
    if value < low:
        bucket.append(f"{label} = {value:.3f} : 통상 범위({low}~{high}) 아래")
    elif value > high:
        bucket.append(f"{label} = {value:.3f} : 통상 범위({low}~{high}) 초과")
