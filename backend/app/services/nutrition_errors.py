"""Expected nutrition failures with stable API handling."""


class MealAnalysisBusyError(RuntimeError):
    """The same upload or meal is already being processed."""


class InvalidMealImageError(ValueError):
    """Input cannot be decoded safely; retrying the model cannot fix it."""
