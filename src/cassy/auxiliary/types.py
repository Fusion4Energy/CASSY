import os
from dataclasses import dataclass
from pathlib import Path
from typing import Union

# Create a custom type
PathLike = Union[str, os.PathLike, Path]


@dataclass(frozen=True)
class LoadTerm:
    """Single signed term of a linear combination of FEM results.

    Parameters
    ----------
    sign : str
        either '+' or '-'.
    analysis : str
        name of the analysis the step belongs to.
    step : int
        load step (or time step) within the analysis.
    """

    sign: str
    analysis: str
    step: int

    def __post_init__(self):
        if self.sign not in ("+", "-"):
            raise ValueError(f"Sign must be '+' or '-', got {self.sign!r}")
        if not str(self.analysis).strip():
            raise ValueError("Analysis name is required")
        if isinstance(self.step, bool) or not isinstance(self.step, int):
            raise ValueError(f"Step must be an integer, got {self.step!r}")

    @classmethod
    def from_dict(cls, data: dict) -> "LoadTerm":
        return cls(data["sign"], str(data["analysis"]), int(data["step"]))

    def to_dict(self) -> dict:
        return {"sign": self.sign, "analysis": self.analysis, "step": self.step}

    def __str__(self) -> str:
        return f"{self.sign}{self.analysis}:{self.step}"
