import re

ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def valid_id(v) -> bool:
    return isinstance(v, str) and bool(ID_RE.match(v))


def is_int(v) -> bool:
    """True for real JSON integers (bool is NOT an int here)."""
    return isinstance(v, int) and not isinstance(v, bool)
