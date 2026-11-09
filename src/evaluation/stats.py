import math
from collections.abc import Sequence


def median_severe(values: Sequence[int]) -> int:
    if not values:
        raise ValueError("median_severe: lista vazia")
    xs = sorted(values)
    n = len(xs)
    if n % 2:
        return xs[n // 2]
    return math.ceil((xs[n // 2 - 1] + xs[n // 2]) / 2)


def quadratic_weighted_kappa(
    pairs: Sequence[tuple[int, int]],
    max_severity: int = 4,
) -> float | None:
    if len(pairs) < 2:
        return None

    categorias = list(range(max_severity + 1))
    n = len(pairs)

    O = {(a, b): 0 for a in categorias for b in categorias}
    for a, b in pairs:
        O[(a, b)] += 1

    linha = {c: sum(O[(c, b)] for b in categorias) for c in categorias}
    coluna = {c: sum(O[(a, c)] for a in categorias) for c in categorias}

    def w(i: int, j: int) -> float: return ((i - j) ** 2) / (max_severity ** 2)

    num = sum(w(i, j) * O[(i, j)] for i in categorias for j in categorias)
    den = sum(w(i, j) * linha[i] * coluna[j] /
              n for i in categorias for j in categorias)

    if den == 0:
        return 1.0 if num == 0 else 0.0
    return 1 - num / den


def _ranks(xs: Sequence[float]) -> list[float]:
    ordem = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(ordem):
        j = i
        while j + 1 < len(ordem) and xs[ordem[j + 1]] == xs[ordem[i]]:
            j += 1
        media = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[ordem[k]] = media
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys):
        raise ValueError("spearman: séries de tamanhos diferentes")
    if len(xs) < 2:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    margem = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, centro - margem), min(1.0, centro + margem)


def wilson_fpc(k: int, n: int, populacao: int, z: float = 1.96) -> tuple[float, float] | None:
    ic = wilson(k, n, z)
    if ic is None or populacao <= 1 or n >= populacao:
        return (k / n, k / n) if ic is not None and n >= populacao else ic
    fator = ((populacao - n) / (populacao - 1)) ** 0.5
    centro, meia = (ic[0] + ic[1]) / 2, (ic[1] - ic[0]) / 2
    return max(0.0, centro - meia * fator), min(1.0, centro + meia * fator)
