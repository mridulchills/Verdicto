"""
Indian Supreme Court citation extraction and normalisation.

This is the single highest-leverage module in the evaluation stack: it feeds
  (1) the citation graph        -> the 0.35 authority signal, currently identically zero
  (2) the ground-truth qrels    -> every retrieval metric in the paper
  (3) leakage stripping         -> without which every metric is invalid

Reporter formats covered (Supreme Court of India):
    AIR 1973 SC 1461              All India Reporter
    (1973) 4 SCC 225              Supreme Court Cases
    2017 (10) SCC 1               SCC, alternate ordering
    (1973) 2 SCR 1                Supreme Court Reports
    2023 INSC 456                 neutral citation (2022 onwards)
    AIRONLINE 2020 SC 123         AIR Online
    2019 SCC OnLine SC 1234       SCC OnLine

Deliberately NOT covered: High Court reporters. The corpus is SC-only, so an HC
citation can never resolve to an in-corpus case; counting them would inflate the
"citations found" figure while contributing nothing to the graph. `find_citations`
reports them separately as `out_of_scope` so the distinction is measurable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Reporter patterns ────────────────────────────────────────────────────────
# Each pattern must expose named groups that normalise_citation() understands.

# Reporter abbreviations appear with or without periods and with either bracket
# style. VERIFIED against the real AWS bucket metadata, where the canonical form is
# "[2020] 4 S.C.R. 552" (square brackets, periods) — NOT the "(2020) 4 SCR 552" form
# assumed before the data was inspected. Both are accepted.
_SCR = r"S\.?\s?C\.?\s?R\.?"          # SCR / S.C.R. / S. C. R.
_SCC = r"S\.?\s?C\.?\s?C\.?"          # SCC / S.C.C.
_YB = r"[\(\[]\s*(?P<year>\d{4})\s*[\)\]]"   # (2020) or [2020]

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AIR", re.compile(r"\bAIR\s+(?P<year>\d{4})\s+SC\s+(?P<num>\d{1,5})\b", re.I)),
    ("AIRONLINE", re.compile(r"\bAIRONLINE\s+(?P<year>\d{4})\s+SC\s+(?P<num>\d{1,5})\b", re.I)),
    # [2020] 4 S.C.R. 552   /   (2020) 4 SCR 552
    ("SCR", re.compile(_YB + r"\s*(?P<vol>\d{1,2})\s*" + _SCR + r"\s*(?P<num>\d{1,5})\b", re.I)),
    # 2020 (4) S.C.R. 552
    ("SCR", re.compile(r"\b(?P<year>\d{4})\s*\(\s*(?P<vol>\d{1,2})\s*\)\s*" + _SCR + r"\s*(?P<num>\d{1,5})\b", re.I)),
    # [1973] 4 S.C.C. 225   /   (1973) 4 SCC 225
    ("SCC", re.compile(_YB + r"\s*(?P<vol>\d{1,2})\s*" + _SCC + r"\s*(?P<num>\d{1,5})\b", re.I)),
    # 2017 (10) SCC 1
    ("SCC", re.compile(r"\b(?P<year>\d{4})\s*\(\s*(?P<vol>\d{1,2})\s*\)\s*" + _SCC + r"\s*(?P<num>\d{1,5})\b", re.I)),
    # 2023 INSC 456  and the compact metadata form 2023INSC456
    ("INSC", re.compile(r"\b(?P<year>\d{4})\s*INSC\s*(?P<num>\d{1,5})\b", re.I)),
    ("SCCONLINE", re.compile(r"\b(?P<year>\d{4})\s+SCC\s+OnLine\s+SC\s+(?P<num>\d{1,5})\b", re.I)),
]

# High Court / other reporters — matched only so they can be counted and excluded.
_OUT_OF_SCOPE = re.compile(
    r"\bAIR\s+\d{4}\s+(?!SC\b)[A-Z]{2,4}\s+\d{1,5}\b"
    r"|\b\d{4}\s+SCC\s+OnLine\s+(?!SC\b)[A-Z][a-z]{1,10}\s+\d{1,5}\b",
    re.I,
)

# Case-name pattern: "X v. Y", "X vs Y", "X versus Y".
# Bounded on both sides to avoid swallowing whole sentences.
CASE_NAME_RE = re.compile(
    r"\b([A-Z][A-Za-z.&'()\- ]{2,60}?)\s+(?:v\.?|vs\.?|versus)\s+([A-Z][A-Za-z.&'()\- ]{2,60}?)"
    r"(?=[,.;:\n\)]|\s+\(|\s*$)",
    re.M,
)

# Signals that a citation is being discussed rather than merely listed (Q52 grading).
_DISCUSSION_CUES = re.compile(
    r"\b(held|relied|relying|followed|following|applied|applying|approved|"
    r"overruled|distinguished|referred|reiterated|affirmed)\b",
    re.I,
)


@dataclass
class FoundCitation:
    """One citation occurrence in a document."""
    raw: str
    canonical: str
    reporter: str
    year: int
    start: int
    end: int
    discussed: bool = False


@dataclass
class ExtractionResult:
    citations: list[FoundCitation] = field(default_factory=list)
    case_names: list[str] = field(default_factory=list)
    out_of_scope: int = 0

    @property
    def canonical_set(self) -> set[str]:
        return {c.canonical for c in self.citations}


def normalise_citation(reporter: str, groups: dict[str, str]) -> str:
    """
    Canonical form: REPORTER:YEAR:VOL:NUM  (VOL omitted as 0 where the reporter has none).
    Both the corpus metadata and extracted text are normalised through this function,
    so matching is exact-string and cheap.
    """
    year = int(groups["year"])
    num = int(groups["num"])
    vol = int(groups.get("vol") or 0)
    rep = reporter.upper()
    if rep == "AIRONLINE":
        rep = "AIR"          # same series, different imprint
    return f"{rep}:{year}:{vol}:{num}"


def find_citations(text: str, mark_discussed: bool = True) -> ExtractionResult:
    """
    Extract every in-scope SC citation from a document.

    mark_discussed: if True, a citation within 200 characters of a discussion cue
    ("held", "relied", "followed", ...) is flagged. Used for graded relevance (Q52):
      discussed -> grade 2, listed-only -> grade 1.
    """
    result = ExtractionResult()
    seen_spans: list[tuple[int, int]] = []

    for reporter, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            # Skip overlaps — several patterns can match the same string.
            if any(s < span[1] and span[0] < e for s, e in seen_spans):
                continue
            seen_spans.append(span)
            gd = {k: v for k, v in m.groupdict().items() if v is not None}
            canonical = normalise_citation(reporter, gd)
            discussed = False
            if mark_discussed:
                lo = max(0, m.start() - 200)
                hi = min(len(text), m.end() + 200)
                discussed = bool(_DISCUSSION_CUES.search(text[lo:hi]))
            result.citations.append(
                FoundCitation(
                    raw=m.group(0), canonical=canonical, reporter=reporter.upper(),
                    year=int(gd["year"]), start=m.start(), end=m.end(), discussed=discussed,
                )
            )

    result.out_of_scope = len(_OUT_OF_SCOPE.findall(text))
    result.case_names = [
        f"{a.strip()} v. {b.strip()}" for a, b in CASE_NAME_RE.findall(text)
    ]
    return result


def strip_leakage(text: str) -> str:
    """
    Remove citation strings and case names from query text.

    MANDATORY when a judgment is used as a query and its own citations are the labels
    (Q48). Without this the query literally contains its answer key, and every reported
    number is invalid in a way a reviewer will detect immediately.

    Applied to the SAME text that is embedded AND that is passed to the lexical channel.
    """
    out = text
    for _, pattern in _PATTERNS:
        out = pattern.sub(" ", out)
    out = _OUT_OF_SCOPE.sub(" ", out)
    out = CASE_NAME_RE.sub(" ", out)
    # Collapse whitespace introduced by the substitutions
    return re.sub(r"\s{2,}", " ", out).strip()


def normalise_metadata_citation(raw: str | None) -> str | None:
    """First canonical form found in a metadata citation string, or None."""
    forms = normalise_metadata_citations(raw)
    return forms[0] if forms else None


def normalise_metadata_citations(raw: str | None) -> list[str]:
    """
    ALL canonical forms found in a metadata citation string.

    The AWS metadata gives a case two independent citations — the reporter form
    ("[2020] 4 S.C.R. 552") and the neutral form ("2020 INSC 395"). load_metadata.py
    stores both, separated by " | ", so that a citing judgment which uses EITHER form
    still resolves. Indexing both roughly doubles the achievable resolution rate.
    """
    if not raw:
        return []
    res = find_citations(raw, mark_discussed=False)
    seen: set[str] = set()
    out: list[str] = []
    for c in res.citations:
        if c.canonical not in seen:
            seen.add(c.canonical)
            out.append(c.canonical)
    return out


def name_key(title: str | None) -> str | None:
    """
    Loose key for case-name fallback matching: lowercase, punctuation stripped,
    'v'/'vs'/'versus' unified. Collisions are possible, so this is only ever used
    as a fallback after canonical citation matching fails.
    """
    if not title:
        return None
    t = title.lower()
    t = re.sub(r"\b(versus|vs\.?|v\.)\b", " v ", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or None
