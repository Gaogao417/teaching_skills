from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Mapping

Point2D = tuple[float, float]
AngleMode = Literal["minor", "reflex"]


@dataclass(frozen=True)
class NormalizedAngleMarker:
    arms: tuple[str, str]
    sweep_deg: float
    swapped: bool


def normalize_angle_marker(
    points: Mapping[str, Point2D],
    *,
    vertex: str,
    arms: tuple[str, str],
    mode: AngleMode = "minor",
    epsilon_deg: float = 1e-6,
) -> NormalizedAngleMarker:
    """Order the rays so TikZ draws the requested directed angle.

    TikZ's ``angles`` pic follows the counterclockwise sweep from the first ray
    to the second. Wolfram may return a reflected layout, so author-provided arm
    order cannot safely stand in for minor/reflex angle intent.
    """

    vertex_point = points[vertex]
    first_point = points[arms[0]]
    second_point = points[arms[1]]
    first = first_point[0] - vertex_point[0], first_point[1] - vertex_point[1]
    second = second_point[0] - vertex_point[0], second_point[1] - vertex_point[1]
    if math.hypot(*first) <= 1e-12 or math.hypot(*second) <= 1e-12:
        raise ValueError(f"angle marker at {vertex} has a zero-length arm")

    cross = first[0] * second[1] - first[1] * second[0]
    dot = first[0] * second[0] + first[1] * second[1]
    sweep = math.degrees(math.atan2(cross, dot)) % 360.0
    if sweep <= epsilon_deg or abs(sweep - 180.0) <= epsilon_deg:
        raise ValueError(
            f"angle marker at {vertex} is degenerate ({sweep:.6f} degrees); "
            "a drawable angle must be strictly between the boundary rays"
        )

    should_swap = (mode == "minor" and sweep > 180.0) or (mode == "reflex" and sweep < 180.0)
    if should_swap:
        return NormalizedAngleMarker(
            arms=(arms[1], arms[0]),
            sweep_deg=round(360.0 - sweep, 6),
            swapped=True,
        )
    return NormalizedAngleMarker(arms=arms, sweep_deg=round(sweep, 6), swapped=False)
