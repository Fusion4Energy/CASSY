import pytest

from cassy.auxiliary.functions import format_terms, parse_legacy_combination
from cassy.auxiliary.types import LoadTerm


class TestLoadTerm:
    def test_roundtrip_dict(self):
        term = LoadTerm("-", "Thermal", 5)
        assert LoadTerm.from_dict(term.to_dict()) == term

    def test_from_dict_casts_step(self):
        assert LoadTerm.from_dict({"sign": "+", "analysis": "X", "step": "3"}).step == 3

    @pytest.mark.parametrize(
        "sign, analysis, step",
        [
            ("*", "X", 1),
            ("+", "", 1),
            ("+", "  ", 1),
            ("+", "X", 1.5),
            ("+", "X", True),
        ],
    )
    def test_invalid(self, sign, analysis, step):
        with pytest.raises(ValueError):
            LoadTerm(sign, analysis, step)


class TestParseLegacyCombination:
    def test_single_step(self):
        assert parse_legacy_combination("A", 3) == [LoadTerm("+", "A", 3)]

    def test_combination_with_spaces(self):
        assert parse_legacy_combination("A", " 2- 1+5 ") == [
            LoadTerm("+", "A", 2),
            LoadTerm("-", "A", 1),
            LoadTerm("+", "A", 5),
        ]

    def test_leading_minus(self):
        assert parse_legacy_combination("A", "-4+1") == [
            LoadTerm("-", "A", 4),
            LoadTerm("+", "A", 1),
        ]

    @pytest.mark.parametrize("expr", ["", "abc", "1*2", "1--2"])
    def test_invalid(self, expr):
        with pytest.raises(ValueError):
            parse_legacy_combination("A", expr)


def test_format_terms():
    terms = [{"sign": "-", "analysis": "X", "step": 2}, LoadTerm("+", "Y", 5)]
    assert format_terms(terms) == "-X:2 + Y:5"
    assert format_terms([]) == ""
