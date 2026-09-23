"""Unit tests for the pure functions inside the renderer.

Unlike the other two suites, which validate data and generated output, these
test a function in isolation: given an input, is the return value correct?

`contiguous_ranges` is the only piece of real logic in the generator. It turns
"every port that is not a trunk" into the fewest `interface range` statements.
A fault here produces configurations that look plausible while leaving ports
unconfigured, which is why it is worth testing directly rather than only
through its output.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "automation"))
from render import contiguous_ranges  # noqa: E402


def as_pairs(ranges):
    return [(r["first"], r["last"]) for r in ranges]


def test_empty_input_yields_nothing():
    assert contiguous_ranges(set()) == []


def test_single_port_is_its_own_range():
    assert as_pairs(contiguous_ranges({7})) == [(7, 7)]


def test_consecutive_ports_collapse_into_one_range():
    assert as_pairs(contiguous_ranges({3, 4, 5, 6})) == [(3, 6)]


def test_a_gap_starts_a_new_range():
    assert as_pairs(contiguous_ranges({1, 2, 5, 6})) == [(1, 2), (5, 6)]


def test_isolated_port_between_ranges():
    """The real case: trunks on 1, 3 and 4 leave port 2 alone and 5-24 whole."""
    ports = set(range(1, 25)) - {1, 3, 4}
    assert as_pairs(contiguous_ranges(ports)) == [(2, 2), (5, 24)]


def test_unordered_input_is_sorted():
    assert as_pairs(contiguous_ranges({9, 3, 4, 8})) == [(3, 4), (8, 9)]


def test_alternating_ports_do_not_collapse():
    assert as_pairs(contiguous_ranges({1, 3, 5})) == [(1, 1), (3, 3), (5, 5)]


def test_every_input_port_appears_in_exactly_one_range():
    """The property that matters: nothing is lost and nothing is invented."""
    ports = {2, 3, 4, 7, 11, 12, 20, 21, 22}
    covered = set()
    for r in contiguous_ranges(ports):
        assert r["first"] <= r["last"]
        span = set(range(r["first"], r["last"] + 1))
        assert not covered & span, "ranges overlap"
        covered |= span
    assert covered == ports


@pytest.mark.parametrize("trunks", [{1}, {1, 2}, {1, 3, 4}, {4, 8, 12}, {24}])
def test_trunk_ports_are_never_included(trunks):
    """Whatever the trunk layout, no trunk port may appear as access."""
    access = set(range(1, 25)) - trunks
    covered = set()
    for r in contiguous_ranges(access):
        covered |= set(range(r["first"], r["last"] + 1))
    assert covered & trunks == set()
    assert covered == access
