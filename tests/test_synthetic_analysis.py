import copy

import pytest

from src.eval.statistical_audit import fictional_data, analyze_synthetic
from src.eval.synthetic_analysis import (
    validate, rate, paired_difference, factorial_effects, cluster_mean, holm, exact_sign_flip,
)


def test_hand_calculated_rates_and_discordant_pairs():
    f, r = fictional_data()
    out = rate(f, r, population="eligible", family="synthetic_header", condition="freshness")
    assert out["estimate"] == .75
    assert out["denominator_known_members"] == 4
    p = paired_difference(f, r, families=["synthetic_header"])
    assert p["estimate"] == .25 and p["effective_complete_questions"] == 4
    assert p["p_value_proposed_sign_flip"] == 1


def test_factorial_hand_calculated_main_effect_and_interactions():
    f,r = fictional_data()
    out = factorial_effects(f,r)
    assert out["effects"]["date"]["estimate"] == 1
    assert all(v["estimate"] == 0 for k,v in out["effects"].items() if k != "date")
    assert out["effective_complete_questions"] == 4


def test_question_clusters_reproducible_and_dependent_rows_not_independent():
    f, r = fictional_data()
    extra = [{**row, "family": "second"} for row in r if row["family"] == "synthetic_header"]
    a = paired_difference(f,r, families=["synthetic_header"])
    b = paired_difference(f,r+extra, families=["synthetic_header", "second"])
    assert a["estimate"] == b["estimate"]
    assert a["uncertainty"] == b["uncertainty"]
    assert cluster_mean({"a": 0, "b": 1}, seed=1) == cluster_mean({"b": 1, "a": 0}, seed=1)
    assert b["uncertainty"]["effective_questions"] == 4


@pytest.mark.parametrize("outcome", ["MISSING", "NEEDS_REVIEW"])
def test_missing_outcomes_no_negative_or_denominator_substitution(outcome):
    f,r = fictional_data()
    r[1]["outcome"] = outcome
    out = rate(f,r,population="eligible",family="synthetic_header",condition="freshness")
    assert out["status"] == "UNDEFINED" and out["estimate"] is None
    assert out["denominator_known_members"] == 4
    assert out["known_member_missingness_bounds"] == [.5,.75]
    assert paired_difference(f,r,families=["synthetic_header"])["status"] == "UNDEFINED"


@pytest.mark.parametrize("field,value", [("retrieval","UNKNOWN"),("retrieval","UNAVAILABLE"),
                                         ("generator","TRUNCATED"),("generator","UNVERIFIED")])
def test_exposure_and_input_uncertainty(field,value):
    f,r = fictional_data()
    r[1][field] = value
    population = "retrieved" if field == "retrieval" else "visible"
    out = rate(f,r,population=population,family="synthetic_header",condition="freshness")
    assert out["status"] == "NOT_ESTIMABLE"
    assert out["unknown_membership_ids"] == [f[0]["question_id"]]
    if field == "generator":
        assert paired_difference(f,r,families=["synthetic_header"])["status"] == "UNDEFINED"


@pytest.mark.parametrize("case", ["unknown_eligibility","missing_clean","empty_eligible","missing_pair","failed"])
def test_failure_and_undefined_propagation(case):
    f,r = fictional_data()
    pop = "eligible"
    if case == "unknown_eligibility":
        f[0]["eligibility"] = "UNKNOWN"
    elif case == "missing_clean":
        f[0]["clean"] = "MISSING"
        pop = "clean_correct"
    elif case == "empty_eligible":
        for q in f:
            q["eligibility"] = "INELIGIBLE"
    elif case == "missing_pair":
        r.pop(1)
    else:
        r[1]["construction"] = "FAILED"
        r[1]["outcome"] = "MISSING"
    out = rate(f,r,population=pop,family="synthetic_header",condition="freshness")
    assert out["estimate"] is None
    assert out["status"] in ("UNDEFINED","NOT_ESTIMABLE")


@pytest.mark.parametrize("change", ["missing_cell","unverified","unresolved"])
def test_incomplete_factorial_not_complete_case_effect(change):
    f,r = fictional_data()
    if change == "missing_cell":
        r.pop(2)
    elif change == "unverified":
        r[2]["generator"] = "UNVERIFIED"
    else:
        r[2]["outcome"] = "NEEDS_REVIEW"
    out = factorial_effects(f,r)
    assert out["status"] == "NOT_ESTIMABLE"
    assert out["effects"]["date"]["estimate"] is None


def test_abstention_distinct_and_observed_nonadoption():
    f,r = fictional_data()
    r[1]["outcome"] = "ABSTAIN"
    out = rate(f,r,population="eligible",family="synthetic_header",condition="freshness")
    assert out["estimate"] == .5
    assert out["outcome_counts_full_frame"]["ABSTAIN"] == 1


def test_holm_hand_calculation_and_missing_family():
    out = holm({"a":.01,"b":.04,"c":.03},family=["a","b","c"])
    assert out["adjusted"] == {"a":.03,"c":.06,"b":.06}
    assert holm({"a":None,"b":.04},family=["a","b"])["status"] == "NOT_ESTIMABLE"
    with pytest.raises(ValueError):
        holm({"a":.01},family=["a","b"])


def test_empty_single_and_degenerate_uncertainty():
    assert cluster_mean({})["estimate"] is None
    assert cluster_mean({"q":1})["ci95"] is None
    assert cluster_mean({"q":1,"r":1})["uncertainty_status"] == "DEGENERATE_EMPIRICAL_DISTRIBUTION"
    assert rate([],[],population="eligible",family="x",condition="y")["status"] == "UNDEFINED"
    assert exact_sign_flip([1,1]) == .5
    assert exact_sign_flip([1]*17) is None


@pytest.mark.parametrize("change", ["duplicate","unknown_id","invalid_label","real_id"])
def test_input_validation(change):
    f,r = fictional_data()
    if change == "duplicate":
        r.append(copy.deepcopy(r[0]))
    elif change == "unknown_id":
        r[0]["question_id"] = "synthetic-stat-999"
    elif change == "invalid_label":
        r[0]["outcome"] = "false"
    else:
        f[0]["question_id"] = "real-id"
    with pytest.raises(ValueError):
        validate(f,r)


def test_deterministic_synthetic_calculations():
    assert analyze_synthetic() == analyze_synthetic()


def test_factorial_interaction_scaling():
    f,r = fictional_data()
    for row in r:
        if row["family"] == "rq3":
            row["outcome"] = ("POISON_ADOPTED" if row["condition"] ==
                "incorrect_newer/freshness/incorrect_first" else "CORRECT")
    effects = factorial_effects(f,r)["effects"]
    assert effects["date"]["estimate"] == .25
    assert effects["date:header"]["estimate"] == .5
    assert effects["date:header:order"]["estimate"] == 1


def test_deterministic_output_bytes(tmp_path,monkeypatch):
    import src.eval.statistical_audit as writer
    monkeypatch.setattr(writer,"verify_prerequisites",lambda: {"synthetic_test":True})
    writer.write_reports(tmp_path/"a")
    writer.write_reports(tmp_path/"b")
    for p in (tmp_path/"a").iterdir():
        assert p.read_bytes() == (tmp_path/"b"/p.name).read_bytes()
    (tmp_path/"a"/"synthetic_results.json").write_text("altered")
    with pytest.raises(ValueError):
        writer.write_reports(tmp_path/"a")
