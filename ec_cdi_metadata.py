"""Lightweight filename-only CDI metadata suggestions for the GUI."""
from pathlib import Path
import re


def suggest_cdi_mass(path):
    """Return an explicit sample-mass suggestion and its source, never apply it.

    Parenthesized sample masses take precedence over other filename amounts
    (for example FTO@C1(25mg)-200mg). Otherwise a level must contain exactly
    one distinct mg amount. An ambiguous filename is not resolved by guessing.
    """
    path = Path(path)
    number = r"(\d+(?:\.\d+)?)\s*mg\b"

    def unique(text):
        values = {float(v) for v in re.findall(number, text, re.I)}
        return next(iter(values)) if len(values) == 1 else None

    brackets = re.findall(r"[（(]([^）)]+)[）)]", path.stem)
    bracket_text = " ".join(brackets)
    if re.search(number, bracket_text, re.I):
        value = unique(bracket_text)
        return {"mass_mg": value, "source": path.name + "（括号内质量）"} if value and value > 0 else None
    if re.search(number, path.stem, re.I):
        value = unique(path.stem)
        return {"mass_mg": value, "source": path.name} if value and value > 0 else None
    for parent in path.parents:
        if re.search(number, parent.name, re.I):
            value = unique(parent.name)
            return {"mass_mg": value, "source": parent.name + "（所在文件夹）"} if value and value > 0 else None
    return None

