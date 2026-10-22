"""Frame list helpers for the character specs."""


def R(row, a, b=None):
    """Frames a..b of one row (b < a plays them backwards)."""
    b = a if b is None else b
    step = 1 if b >= a else -1
    return ["%d.%d" % (row, i) for i in range(a, b + step, step)]


def F(*refs):
    return list(refs)
