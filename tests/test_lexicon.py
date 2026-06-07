from __future__ import annotations

import pytest

from crawler.seeds.lexicon import Lexicon


def test_load_packaged_lexicon_has_geo_and_food_terms():
    lex = Lexicon.load()
    assert len(lex) > 0
    assert "chicago" in lex
    assert "restaurant" in lex
    assert lex.category("chicago") == "geo"
    assert lex.category("restaurant") == "food"


def test_from_mapping_with_weights_and_list_section():
    lex = Lexicon.from_mapping(
        {
            "geo_terms": {"Chicago": 1.0, "West Loop": 0.9},
            "food_terms": ["restaurant", "menu"],  # bare list defaults to weight 1.0
        }
    )
    assert lex.weight("chicago") == 1.0
    assert lex.weight("west loop") == 0.9
    assert lex.weight("restaurant") == 1.0
    assert lex.category("west loop") == "geo"


def test_terms_are_normalized_and_membership_is_case_insensitive():
    lex = Lexicon.from_mapping({"geo_terms": {"  CHICAGO  ": 1.0}})
    assert "chicago" in lex
    assert "Chicago" in lex
    assert "chicago" in lex.terms


@pytest.mark.parametrize("bad_weight", [0.0, -0.1, 1.5, 2])
def test_invalid_weight_rejected(bad_weight):
    with pytest.raises(ValueError):
        Lexicon.from_mapping({"geo_terms": {"chicago": bad_weight}})


def test_overlapping_categories_rejected():
    with pytest.raises(ValueError):
        Lexicon(geo_terms={"chicago": 1.0}, food_terms={"chicago": 1.0})


def test_find_matches_counts_occurrences_with_word_boundaries():
    lex = Lexicon.from_mapping({"food_terms": {"bar": 1.0, "deep dish": 1.0}})
    text = "The bar served a deep dish; another deep dish followed. Embarrassing barbecue."
    matches = lex.find_matches(text)
    assert matches["deep dish"] == 2
    # "bar" should match the standalone word but not "Embarrassing" or "barbecue".
    assert matches["bar"] == 1


def test_find_matches_multiword_flexible_whitespace():
    lex = Lexicon.from_mapping({"food_terms": {"tasting menu": 1.0}})
    assert lex.find_matches("an amazing tasting   menu tonight") == {"tasting menu": 1}


def test_find_path_matches_handles_slugs():
    lex = Lexicon.from_mapping(
        {"geo_terms": {"west loop": 0.9}, "food_terms": {"best restaurants": 1.0}}
    )
    matches = lex.find_path_matches("/west-loop/best-restaurants-2026/")
    assert matches == {"west loop": 1, "best restaurants": 1}


def test_no_matches_returns_empty():
    lex = Lexicon.from_mapping({"geo_terms": {"chicago": 1.0}})
    assert lex.find_matches("a story about new york delis") == {}
    assert lex.find_matches("") == {}
