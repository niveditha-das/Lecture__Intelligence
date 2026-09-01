"""The mastery maths, with no imports.

Deliberately dependency-free: no database, no config, no model. The update rule
is the part of this system most worth testing and most worth explaining, and it
should not require Postgres to be running to check that a correct answer raises
an ability estimate.

Model: one-parameter logistic (Rasch). Given ability `theta` and question
difficulty `b`,

    p(correct) = sigmoid(theta - b)
    theta     <- theta + K * (correct - p)

which is Elo with the student as one player and the question as the other. K
decays with experience so early answers move the estimate quickly and later
ones refine it.
"""
from __future__ import annotations

import math

K_MIN, K_MAX = 0.15, 0.6
BASE_HALF_LIFE_DAYS = 3.0   # a topic reviewed today should not read as forgotten
MIN_DAYS_FOR_DECAY = 0.5    # below this, treat the material as still fresh


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def k_factor(n_seen: int) -> float:
    """High while the estimate is provisional, low once it has settled."""
    return K_MIN + (K_MAX - K_MIN) / (1.0 + 0.25 * max(0, n_seen))


def update_theta(theta: float, difficulty: float, correct: bool, n_seen: int) -> float:
    p = sigmoid(theta - difficulty)
    return theta + k_factor(n_seen) * ((1.0 if correct else 0.0) - p)


def half_life_days(theta: float, n_correct: int) -> float:
    """Memory lasts longer for material you know well and have recalled often."""
    return BASE_HALF_LIFE_DAYS * (2.0 ** theta) * (1.0 + 0.35 * max(0, n_correct))


def retention(theta: float, n_correct: int, days_since: float) -> float:
    """Exponential forgetting: halves every `half_life_days`."""
    # Decay is calibrated in days. Something answered minutes ago is not
    # "5% retained" — reporting that made the mastery panel say something false.
    if days_since <= MIN_DAYS_FOR_DECAY:
        return 1.0
    return 2.0 ** (-days_since / half_life_days(theta, n_correct))


def urgency(theta: float, n_correct: int, days_since: float | None,
            days_to_exam: float) -> float:
    """How badly a topic needs revising before the exam.

    Never-assessed topics are treated as weak rather than skipped — that is what
    makes a first plan cover the whole course instead of only known failures.
    """
    predicted = (
        0.25 if days_since is None
        else retention(theta, n_correct, days_since + days_to_exam)
    )
    weakness = max(0.0, 1.0 - (theta + 1.5) / 3.0)   # theta -1.5..1.5 -> 1..0
    return (1.0 - predicted) * (1.0 + weakness)
