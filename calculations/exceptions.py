"""calculations/exceptions.py – Domain exceptions for the calculation engine."""


class CalculationError(Exception):
    """Base exception for all calculation errors."""
    pass


class InvalidInputError(CalculationError):
    """Raised when input values are physically or logically invalid."""
    pass


class InsufficientDataError(CalculationError):
    """Raised when minimum required measurements for an evaluation are not met."""
    pass

