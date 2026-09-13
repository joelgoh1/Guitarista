from __future__ import annotations

from guitarista_api.solver.cost import BaselineCost, BaselineWeights
from guitarista_api.solver.model import ChordFretting, NoteFretting


def cf(*pairs: tuple[int, int]) -> ChordFretting:
    return ChordFretting(tuple(NoteFretting(s, f) for s, f in pairs))


COST = BaselineCost()


def test_exact_repeat_is_free() -> None:
    a = cf((1, 3), (2, 5))
    assert COST.transition(a, cf((1, 3), (2, 5))) == 0.0


def test_rest_transitions_are_free() -> None:
    assert COST.transition(ChordFretting.rest(), cf((1, 3))) == 0.0
    assert COST.transition(cf((1, 3)), ChordFretting.rest()) == 0.0
    assert COST.local(ChordFretting.rest()) == 0.0


def test_open_strings_are_rewarded_and_high_frets_penalised() -> None:
    assert COST.local(cf((1, 0))) < COST.local(cf((2, 5))) < COST.local(cf((3, 9)))


def test_move_distance_grows_with_fret_jump() -> None:
    base = cf((3, 5))
    assert COST.transition(base, cf((3, 6))) < COST.transition(base, cf((3, 12)))


def test_all_open_side_has_zero_move_cost() -> None:
    w = BaselineWeights(string_change=0.0)
    cost = BaselineCost(w)
    assert cost.transition(cf((1, 0)), cf((3, 9))) == 0.0


def test_position_shift_gate() -> None:
    small = COST.transition(cf((3, 5)), cf((3, 7)))
    big = COST.transition(cf((3, 5)), cf((3, 12)))
    # the big jump pays the gate on top of the distance
    assert big - small > COST.w.position_shift * 0.5


def test_skipped_strings_and_spread_add_cost() -> None:
    compact = cf((1, 1), (2, 1))
    skipped = cf((1, 1), (3, 1))
    assert COST.local(skipped) > COST.local(compact)


def test_open_move_charges_distance_to_the_nut() -> None:
    lead = BaselineCost(BaselineWeights(open_move=0.6, string_change=0.0))
    assert lead.transition(cf((2, 7)), cf((1, 0))) == 0.6 * 7
    assert lead.transition(cf((1, 0)), cf((2, 7))) == 0.6 * 7
    assert lead.transition(cf((1, 0)), cf((2, 0))) == 0.0  # open to open: no hand position
    assert COST.transition(cf((2, 7)), cf((1, 0))) == 0.15  # tabgen: only the string change


def test_profiles_are_distinct_and_tabgen_is_default() -> None:
    from guitarista_api.solver.cost import COST_PROFILES, cost_for_profile

    assert COST_PROFILES["tabgen"] == BaselineWeights()
    assert cost_for_profile("lead").w.open_move > 0
    assert cost_for_profile("beginner").w.open_string_bonus < BaselineWeights().open_string_bonus


def test_hint_mismatch_is_charged_locally() -> None:
    from guitarista_api.solver.model import ChordFretting, NoteFretting

    miss = ChordFretting((NoteFretting(5, 0),), hint_misses=1)
    hit = ChordFretting((NoteFretting(5, 0),), hint_misses=0)
    assert COST.local(miss) - COST.local(hit) == COST.w.hint_mismatch
    assert miss == hit  # misses never change fretting identity
