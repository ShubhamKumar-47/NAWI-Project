"""calculations/base.py – Abstract Base Classes and Data Structures for Calculators."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class TestInput:
    """Base input data class containing metrological parameters."""
    accuracy_class: str
    max_capacity: Decimal
    min_capacity: Decimal
    scale_interval: Decimal          # d (actual scale interval)
    actual_scale_interval: Decimal   # e (verification scale interval)
    is_initial_verification: bool = True  # True: initial; False: in-service


@dataclass
class TestResult:
    """Standardized output returned by all calculators."""
    pass_fail: str                     # "PASS" | "FAIL" | "PENDING"
    error: Optional[Decimal] = None
    mpe: Optional[Decimal] = None
    computed_fields: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


class AbstractTestCalculator(ABC):
    """Abstract Base Class for all OIML R 76 test calculators."""

    @abstractmethod
    def calculate(self, *args, **kwargs) -> TestResult:
        """Execute calculation and return a TestResult."""
        pass

    @abstractmethod
    def validate_input(self, *args, **kwargs) -> List[str]:
        """Validate input parameters and return a list of error messages."""
        pass

