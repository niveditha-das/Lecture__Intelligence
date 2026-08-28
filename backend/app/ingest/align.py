"""Align transcript segments to slides.

A lecturer moves through slides in order, so the mapping
    segment index -> slide index
is monotonically non-decreasing. That turns "which slide was he on?" into a
tiny dynamic-programming problem over the segment x slide cosine-similarity
matrix (a constrained DTW).

Payoff: a transcript chunk gains a *slide* number, and a slide chunk gains a
*timestamp*. One citation can then say "Lecture 7, slide 23 @ 06:52" and the
tutor can answer "what did he actually say about this slide?".
"""
from __future__ import annotations

import numpy as np

NEG = -1e9


def _cosine_matrix(seg_emb: np.ndarray, slide_emb: np.ndarray) -> np.ndarray:
    a = seg_emb / (np.linalg.norm(seg_emb, axis=1, keepdims=True) + 1e-9)
    b = slide_emb / (np.linalg.norm(slide_emb, axis=1, keepdims=True) + 1e-9)
    return a @ b.T


def align(
    seg_emb: np.ndarray,
    slide_emb: np.ndarray,
    stay_bonus: float = 0.25,
    max_skip: int = 3,
) -> list[int]:
    """Return, for each segment, the 0-based slide index it belongs to.

    stay_bonus rewards staying on the current slide (lecturers linger);
    max_skip caps how many slides can be jumped in one segment.
    """
    n, m = seg_emb.shape[0], slide_emb.shape[0]
    if n == 0 or m == 0:
        return [0] * n

    sim = _cosine_matrix(seg_emb, slide_emb)
    dp = np.full((n, m), NEG, dtype=np.float64)
    back = np.zeros((n, m), dtype=np.int32)

    dp[0, 0] = sim[0, 0] + stay_bonus
    for j in range(1, min(m, max_skip + 1)):      # allow starting mid-deck
        dp[0, j] = sim[0, j]

    for i in range(1, n):
        for j in range(m):
            lo = max(0, j - max_skip)
            best_prev, best_j = NEG, j
            for k in range(lo, j + 1):
                val = dp[i - 1, k] + (stay_bonus if k == j else 0.0)
                if val > best_prev:
                    best_prev, best_j = val, k
            if best_prev > NEG / 2:
                dp[i, j] = best_prev + sim[i, j]
                back[i, j] = best_j

    # backtrace from the best final slide
    path = [0] * n
    j = int(np.argmax(dp[n - 1]))
    for i in range(n - 1, -1, -1):
        path[i] = j
        j = int(back[i, j])
    return path


def slide_time_ranges(
    path: list[int], seg_times: list[tuple[float, float]], n_slides: int
) -> dict[int, tuple[float, float]]:
    """Invert the alignment: slide index -> (t_start, t_end)."""
    out: dict[int, tuple[float, float]] = {}
    for seg_i, slide_i in enumerate(path):
        t0, t1 = seg_times[seg_i]
        if slide_i in out:
            a, b = out[slide_i]
            out[slide_i] = (min(a, t0), max(b, t1))
        else:
            out[slide_i] = (t0, t1)
    return {k: v for k, v in out.items() if 0 <= k < n_slides}
