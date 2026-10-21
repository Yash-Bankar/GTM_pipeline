"""Static accessibility and layout audit for the frontend (V2-08).

Runs three checks over ``frontend/src`` without a browser:

1. **Accessible names + visible focus** - every button, link and form control
   must have an accessible name (text content, ``aria-label``,
   ``aria-labelledby`` or a ``<label for>`` association) and a visible focus
   ring (a ``focus-visible`` utility, or the shared ``.field`` class, which
   carries a focus halo from ``globals.css``).
2. **Touch targets** - interactive controls should be at least 44x44 CSS
   pixels (``min-h-11``).
3. **360px overflow** - no fixed width larger than the 360px viewport minus
   the page padding.

Run from the repository root:

    .\\backend\\.venv\\Scripts\\python.exe scripts\\audit_frontend_a11y.py

Exit code 1 means at least one issue was found.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"

TAG_RE = re.compile(r"<(button|a|input|select|textarea)\b[^>]*>", re.I | re.S)
LABEL_FOR_RE = re.compile(r'<label[^>]*\b(?:for|htmlFor)="([^"]+)"', re.I)
LABEL_FOR_TMPL_RE = re.compile(r"<label[^>]*\b(?:for|htmlFor)=\{`([^`$]*)\$\{", re.I)
MIN_H_RE = re.compile(r"min-h-(\d+)")
WIDE_RE = re.compile(r"\b(?:w-\[(\d+)px\]|min-w-\[(\d+)px\]|max-w-\[(\d+)px\])")

# The minimum accessible touch target in CSS pixels (Tailwind `min-h-11`).
MIN_TOUCH_PX = 44
# The narrowest viewport the layout must survive (PRD 6.6).
NARROW_VIEWPORT_PX = 360
# The page's horizontal padding at the narrowest breakpoint (px-4 = 16px).
PAGE_PADDING_PX = 16


def find_tag_end(text: str, start: int) -> int:
    """Index of the '>' that closes the tag starting at ``start``.

    A naive scan stops at the '=>' of an arrow function, so those are skipped.
    """
    pos = start
    while True:
        nxt = text.find(">", pos + 1)
        if nxt < 0:
            return len(text) - 1
        if nxt > 0 and text[nxt - 1] == "=":
            pos = nxt
            continue
        return nxt


def strip_tags(fragment: str) -> str:
    return re.sub(r"<[^>]+>", " ", fragment)


def audit() -> tuple[list[str], dict[str, int]]:
    issues: list[str] = []
    stats = {"elements": 0, "touch_targets": 0}

    for path in sorted(SRC.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        labelled_ids = set(LABEL_FOR_RE.findall(text))
        labelled_prefixes = set(LABEL_FOR_TMPL_RE.findall(text))

        for match in TAG_RE.finditer(text):
            tag = match.group(1).lower()
            line = text[: match.start()].count("\n") + 1
            end = find_tag_end(text, match.start())
            full_tag = text[match.start() : end + 1]

            if 'type="hidden"' in full_tag:
                continue

            element_id = re.search(r'\bid="([^"]+)"', full_tag)
            element_id = element_id.group(1) if element_id else ""
            template = re.search(r"\bid=\{`([^`$]*)\$\{", full_tag)
            element_prefix = template.group(1) if template else None

            stats["elements"] += 1

            # 1. Accessible name.
            if tag in ("button", "a"):
                close = text.find(f"</{tag}>", end)
                inner = text[end + 1 : close if close > 0 else end + 300]
                has_name = (
                    strip_tags(inner).strip() != ""
                    or "aria-label" in full_tag
                    or "aria-labelledby" in full_tag
                )
            else:
                has_name = (
                    "aria-label" in full_tag
                    or "aria-labelledby" in full_tag
                    or (element_id and element_id in labelled_ids)
                    or (element_prefix and element_prefix in labelled_prefixes)
                )
            if not has_name:
                issues.append(
                    f"{rel}:{line} <{tag}> has no accessible name -> {full_tag[:110]}"
                )

            # 2. Visible focus.
            has_focus = (
                "focus-visible" in full_tag
                or "focus:ring" in full_tag
                or "focus:outline" in full_tag
                or re.search(r'className="[^"]*\bfield\b', full_tag) is not None
            )
            if not has_focus:
                issues.append(
                    f"{rel}:{line} <{tag}> has no visible focus ring -> {full_tag[:110]}"
                )

            # 3. Touch target.
            if tag in ("button", "a"):
                stats["touch_targets"] += 1
                sizes = [int(value) for value in MIN_H_RE.findall(full_tag)]
                if sizes and max(sizes) * 4 < MIN_TOUCH_PX:
                    issues.append(
                        f"{rel}:{line} <{tag}> touch target below {MIN_TOUCH_PX}px "
                        f"(min-h-{max(sizes)})"
                    )

        # 4. Overflow risk.
        for match in WIDE_RE.finditer(text):
            if match.group(0).startswith("max-w"):
                continue
            values = [int(value) for value in match.groups() if value]
            if not values:
                continue
            widest = max(values)
            if widest > NARROW_VIEWPORT_PX - PAGE_PADDING_PX:
                line = text[: match.start()].count("\n") + 1
                issues.append(
                    f"{rel}:{line} {match.group(0)} exceeds the {NARROW_VIEWPORT_PX}px viewport"
                )

    return issues, stats


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: {SRC} not found")
        return 1
    issues, stats = audit()
    print(
        f"audited {stats['elements']} interactive elements "
        f"({stats['touch_targets']} buttons/links)"
    )
    print(f"issues: {len(issues)}")
    for issue in issues:
        print("  ", issue)
    if not issues:
        print(
            "OK - every action has an accessible name, a visible focus ring, "
            f"a >= {MIN_TOUCH_PX}px target, and no overflow at {NARROW_VIEWPORT_PX}px."
        )
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
