from math import sqrt

Z95 = 1.959963984540054


def wilson(k: float, n: float, z: float = Z95) -> tuple[float, float]:
    if n <= 0 or k < 0 or k > n:
        raise ValueError("wilson needs 0 <= k <= n and n > 0")
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None
    return 2 * precision * recall / (precision + recall)
