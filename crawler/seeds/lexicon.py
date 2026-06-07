"""Topic lexicon parsing and term matching.

The :class:`Lexicon` is the single source of truth for relevance terms. It is
consumed by both the discovery-time URL scorer (``crawler/relevance``) and the
content-time relevance scorer (``processing/relevance``). This module only
parses terms/weights and exposes matching primitives; the actual scoring
formulas live with their respective scorers.
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path
from typing import Literal

import yaml

Category = Literal["geo", "food"]

_DEFAULT_RESOURCE = "lexicon.yaml"
# Replace runs of non-alphanumeric characters (slashes, hyphens, underscores,
# dots) with a single space so URL slugs like "west-loop-dining" tokenize the
# same way as prose.
_NON_WORD = re.compile(r"[^0-9a-z]+")


def _normalize_term(term: str) -> str:
    return _NON_WORD.sub(" ", term.strip().lower()).strip()


def _compile_term(term: str) -> re.Pattern[str]:
    """Word-boundary, whitespace-flexible matcher for a (possibly multi-word) term."""
    words = term.split()
    body = r"\s+".join(re.escape(w) for w in words)
    return re.compile(rf"(?<![0-9a-z]){body}(?![0-9a-z])", re.IGNORECASE)


class Lexicon:
    """Parsed topic lexicon with geo and food terms and their weights."""

    def __init__(
        self,
        geo_terms: dict[str, float] | None = None,
        food_terms: dict[str, float] | None = None,
    ) -> None:
        self.geo_terms: dict[str, float] = self._clean(geo_terms or {})
        self.food_terms: dict[str, float] = self._clean(food_terms or {})

        overlap = set(self.geo_terms) & set(self.food_terms)
        if overlap:
            raise ValueError(f"terms present in both geo and food categories: {sorted(overlap)}")

        self._weights: dict[str, float] = {**self.geo_terms, **self.food_terms}
        self._categories: dict[str, Category] = {
            **{t: "geo" for t in self.geo_terms},
            **{t: "food" for t in self.food_terms},
        }
        self._patterns: dict[str, re.Pattern[str]] = {
            t: _compile_term(t) for t in self._weights
        }

    @staticmethod
    def _clean(terms: dict[str, float]) -> dict[str, float]:
        cleaned: dict[str, float] = {}
        for raw_term, weight in terms.items():
            term = _normalize_term(str(raw_term))
            if not term:
                continue
            w = float(weight)
            if not 0.0 < w <= 1.0:
                raise ValueError(f"weight for {term!r} must be in (0, 1], got {w}")
            cleaned[term] = w
        return cleaned

    # --- factories ---

    @classmethod
    def from_mapping(cls, data: dict) -> Lexicon:
        if not isinstance(data, dict):
            raise ValueError("lexicon data must be a mapping")
        return cls(
            geo_terms=cls._coerce_section(data.get("geo_terms", {})),
            food_terms=cls._coerce_section(data.get("food_terms", {})),
        )

    @staticmethod
    def _coerce_section(section: object) -> dict[str, float]:
        """Accept either a mapping of term->weight or a bare list (weight 1.0)."""
        if section is None:
            return {}
        if isinstance(section, dict):
            return {str(k): float(v) for k, v in section.items()}
        if isinstance(section, list):
            return {str(item): 1.0 for item in section}
        raise ValueError(f"lexicon section must be a mapping or list, got {type(section).__name__}")

    @classmethod
    def load(cls, path: str | Path | None = None) -> Lexicon:
        """Load the lexicon from a YAML file, or the packaged default when ``path`` is None."""
        if path is None:
            text = resources.files(__package__).joinpath(_DEFAULT_RESOURCE).read_text("utf-8")
        else:
            text = Path(path).read_text("utf-8")
        return cls.from_mapping(yaml.safe_load(text) or {})

    # --- accessors ---

    @property
    def terms(self) -> dict[str, float]:
        """All terms (geo + food) mapped to their weight."""
        return dict(self._weights)

    def __len__(self) -> int:
        return len(self._weights)

    def __contains__(self, term: object) -> bool:
        return _normalize_term(str(term)) in self._weights

    def weight(self, term: str) -> float:
        return self._weights[_normalize_term(term)]

    def category(self, term: str) -> Category:
        return self._categories[_normalize_term(term)]

    # --- matching ---

    def find_matches(self, text: str) -> dict[str, int]:
        """Return {term: occurrence_count} for every lexicon term found in ``text``."""
        if not text:
            return {}
        matches: dict[str, int] = {}
        for term, pattern in self._patterns.items():
            count = len(pattern.findall(text))
            if count:
                matches[term] = count
        return matches

    def find_path_matches(self, url_path: str) -> dict[str, int]:
        """Like :meth:`find_matches`, but normalizes URL slugs first.

        ``/west-loop/best-restaurants`` is tokenized to ``west loop best
        restaurants`` so multi-word terms match across hyphen/slash boundaries.
        """
        normalized = _NON_WORD.sub(" ", (url_path or "").lower())
        return self.find_matches(normalized)
