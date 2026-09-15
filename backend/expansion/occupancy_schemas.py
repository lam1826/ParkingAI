"""Bounded, normalized calibration input. Slot geometry never changes inventory."""
import math
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OccupancySettings(Input):
    pixel_delta: int = Field(default=30, strict=True, ge=10, le=80)
    empty_ratio: float = Field(default=0.06, ge=0.01, le=0.20)
    occupied_ratio: float = Field(default=0.25, ge=0.15, le=0.80)
    max_lighting_shift: int = Field(default=35, strict=True, ge=10, le=80)
    min_blur_variance: float = Field(default=15, ge=0, le=200)
    stale_after_seconds: int = Field(default=30, strict=True, ge=5, le=300)
    confirmation_frames: int = Field(default=2, strict=True, ge=1, le=3)

    @model_validator(mode="after")
    def distinct_thresholds(self):
        if self.occupied_ratio < self.empty_ratio + 0.05:
            raise ValueError("Ngưỡng có xe phải lớn hơn ngưỡng trống ít nhất 0,05.")
        return self


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _intersects(a, b, c, d):
    def on_segment(x, y, z):
        return min(x[0], y[0]) - 1e-9 <= z[0] <= max(x[0], y[0]) + 1e-9 and min(x[1], y[1]) - 1e-9 <= z[1] <= max(x[1], y[1]) + 1e-9
    values = (_cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b))
    if values[0] * values[1] < 0 and values[2] * values[3] < 0:
        return True
    return any(abs(value) < 1e-9 and on_segment(x, y, z) for value, x, y, z in (
        (values[0], a, b, c), (values[1], a, b, d), (values[2], c, d, a), (values[3], c, d, b)))


class SlotRegion(Input):
    slot_id: int = Field(strict=True, gt=0)
    polygon: list[tuple[float, float]] = Field(min_length=3, max_length=12)

    @field_validator("polygon")
    @classmethod
    def valid_polygon(cls, points):
        if any(not math.isfinite(value) or not 0 <= value <= 1 for point in points for value in point):
            raise ValueError("Các điểm phải nằm trong ảnh, với tọa độ từ 0 đến 1.")
        if len(set(points)) != len(points):
            raise ValueError("Các đỉnh vùng không được trùng nhau.")
        if any(abs(_cross(points[i - 1], points[i], points[(i + 1) % len(points)])) < 1e-9 for i in range(len(points))):
            raise ValueError("Chỉ chọn các góc; ba đỉnh liên tiếp không được thẳng hàng.")
        area = abs(sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1] for i in range(len(points)))) / 2
        if not 0.0005 <= area <= 0.95:
            raise ValueError("Vùng chỗ đỗ quá nhỏ hoặc chiếm gần toàn bộ khung hình.")
        edges = [(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]
        for i, (a, b) in enumerate(edges):
            for j in range(i + 1, len(edges)):
                if j == i + 1 or (i == 0 and j == len(edges) - 1):
                    continue
                if _intersects(a, b, *edges[j]):
                    raise ValueError("Các cạnh vùng chỗ đỗ không được tự cắt nhau.")
        return points


class CalibrationCreate(Input):
    camera_id: int = Field(strict=True, gt=0)
    reference_observation_id: UUID
    regions: list[SlotRegion] = Field(min_length=1, max_length=64)
    settings: OccupancySettings = Field(default_factory=OccupancySettings)
    empty_reference_confirmed: Literal[True]
    request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("empty_reference_confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Cần xác nhận các vùng trong ảnh nền đang trống.")
        return value

    @model_validator(mode="after")
    def unique_slots(self):
        if len({region.slot_id for region in self.regions}) != len(self.regions):
            raise ValueError("Mỗi chỗ chỉ có một vùng trong một phiên bản cấu hình.")
        return self


class OccupancyAnalyze(Input):
    camera_id: int = Field(strict=True, gt=0)
    calibration_id: UUID
    observation_id: UUID
