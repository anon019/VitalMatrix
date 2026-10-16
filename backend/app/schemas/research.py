"""Owner-authorized journal input; research keys can only read."""

from typing import Literal
import uuid

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.services.research_schema import MEASUREMENTS


class Measurement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=40)
    method: Literal["measured", "self_reported", "estimated", "lab"] = "self_reported"

    @model_validator(mode="after")
    def check_unit_and_range(self):
        if self.code in MEASUREMENTS:
            unit, low, high = MEASUREMENTS[self.code]
            if self.unit != unit:
                raise ValueError(
                    f"{self.code} requires unit {unit}; convert explicitly before submission"
                )
            if not low <= self.value <= high:
                raise ValueError(f"{self.code} outside accepted input range")
        return self


class JournalEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(default="manual", pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    external_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), min_length=1, max_length=200
    )
    kind: Literal[
        "measurement",
        "lab",
        "medication",
        "supplement",
        "symptom",
        "lifestyle",
        "nutrition_coverage",
    ]
    occurred_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    measurements: list[Measurement] = Field(default_factory=list, max_length=50)
    label: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    severity: int | None = Field(default=None, ge=0, le=10)
    dose: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    dose_unit: str | None = Field(default=None, max_length=40)
    complete: bool | None = None
    supersedes_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_entry(self):
        if self.source in ("oura", "polar", "nutrition"):
            raise ValueError("reserved device source")
        if self.ended_at and self.ended_at < self.occurred_at:
            raise ValueError("ended_at must not precede occurred_at")
        if self.ended_at and (self.ended_at - self.occurred_at).days > 366:
            raise ValueError("split intervals longer than 366 days")
        if len({m.code for m in self.measurements}) != len(self.measurements):
            raise ValueError("measurement codes must be unique within an entry")
        if any(len(tag) > 80 for tag in self.tags):
            raise ValueError("tag too long")
        if self.kind in ("measurement", "lab") and not self.measurements:
            raise ValueError("measurements required")
        if self.kind == "nutrition_coverage" and self.complete is None:
            raise ValueError("complete is required for nutrition_coverage")
        if (
            self.kind not in ("measurement", "lab", "nutrition_coverage")
            and not self.label
        ):
            raise ValueError("label required")
        if (self.dose is None) != (self.dose_unit is None):
            raise ValueError("dose and dose_unit must be supplied together")
        return self
