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
from dataclasses import dataclass
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
    tip_mach: float             # Mu2
    inlet_sound_speed: float    # [m/s]
    warnings: list[str]

    @property
    def diameter_mm(self) -> float:
        return self.diameter * 1000.0

    @property
    def eye_diameter_mm(self) -> float:
        return self.eye_diameter * 1000.0


def size_impeller(
    stage: StageResult,
    refrigerant: str,
    head_coefficient: float = 0.60,
    specific_speed: float = 0.70,
    rpm: Optional[float] = None,
    eye_hub_ratio: float = 0.35,
    inlet_axial_mach: float = 0.30,
) -> ImpellerSizing:
    """한 단의 임펠러 치수를 개략 산정한다.

    stage             : cycle.compress() 가 돌려준 단 성능
    head_coefficient  : psi. 후향깃 임펠러는 0.55~0.62 가 흔하다
    specific_speed    : Ns. rpm 을 직접 주면 무시한다
    rpm               : 회전수를 고정하고 싶을 때 [rpm]
    eye_hub_ratio     : 흡입구 허브/팁 비 (보통 0.3~0.45)
    inlet_axial_mach  : 흡입구 축방향 마하수 목표 (보통 0.25~0.35)
    """
    if head_coefficient <= 0:
        raise ValueError("압력계수(psi)는 0보다 커야 한다")

    dh_is_j = stage.dh_isentropic * 1000.0      # [J/kg]
    q = stage.mass_flow / stage.suction_density  # [m3/s]
    if q <= 0:
        raise ValueError("흡입 체적유량이 0 이하다")

    # 주속은 헤드계수로 정해진다.  dh_is = psi * u2^2
    u2 = math.sqrt(dh_is_j / head_coefficient)

    # 회전수: 직접 주거나 비속도로 정한다.
    if rpm is not None:
        omega = rpm * 2.0 * math.pi / 60.0
        ns = omega * math.sqrt(q) / dh_is_j**0.75
    else:
        ns = specific_speed
        omega = ns * dh_is_j**0.75 / math.sqrt(q)
        rpm = omega * 60.0 / (2.0 * math.pi)

    d2 = 2.0 * u2 / omega
    ds = d2 * dh_is_j**0.25 / math.sqrt(q)
    phi = q / (u2 * d2**2)

    a1 = props.a_tp(refrigerant, stage.t_in, stage.p_in)
    mu2 = u2 / a1

    # 흡입구(아이) 외경: 축방향 속도를 마하수 목표로 잡고 환상 면적에서 역산
    c_axial = inlet_axial_mach * a1
    area = q / c_axial
    d_eye = math.sqrt(4.0 * area / (math.pi * (1.0 - eye_hub_ratio**2)))

    warnings: list[str] = []
    _check(warnings, "압력계수 psi", head_coefficient, *LIMITS["psi"])
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
        head_coefficient=head_coefficient,
        work_coefficient=stage.dh_actual * 1000.0 / u2**2,
        specific_speed=ns,
        specific_diameter=ds,
        flow_coefficient=phi,
        tip_mach=mu2,
        inlet_sound_speed=a1,
        warnings=warnings,
    )


def _check(bucket: list[str], label: str, value: float, low: float, high: float) -> None:
    if value < low:
        bucket.append(f"{label} = {value:.3f} : 통상 범위({low}~{high}) 아래")
    elif value > high:
        bucket.append(f"{label} = {value:.3f} : 통상 범위({low}~{high}) 초과")
