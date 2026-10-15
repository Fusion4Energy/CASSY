from cassy.runners.run_project import load_project  # noqa: F401  (used by the tests)


def assert_equation_terms_linked(df) -> None:
    """Check that the applied stress and allowable of every equation in a trace point
    (via the ``source`` column) to a recorded value of the same event with the same
    value."""
    import numpy as np

    event = ["component", "item", "position", "event", "analysis"]
    results = df[(df["kind"] == "result") & df["name"].isin(["applied", "allowable"])]
    assert not results.empty
    assert results["source"].notna().all(), results[results["source"].isna()]
    values = df[df["kind"] != "result"].copy()
    to_pa = np.where(values["unit"].eq("MPa").fillna(False), 1e6, 1.0)
    values["value_pa"] = values["value"].astype(float) * to_pa
    merged = results.merge(
        values[event + ["rule", "name", "value_pa", "text"]],
        left_on=event + ["source"],
        right_on=event + ["name"],
        suffixes=("", "_term"),
    )
    # allowables are recorded inside the rule, stresses can be event wide (bolts)
    same_rule = (merged["rule_term"] == merged["rule"]) | merged["rule_term"].isna()
    merged = merged[same_rule]
    linked = merged.drop_duplicates(["seq"])
    assert len(linked) == len(results), "some terms are not recorded in the event"
    numeric = linked["value"].notna()
    np.testing.assert_allclose(
        linked.loc[numeric, "value"].astype(float),
        linked.loc[numeric, "value_pa"],
        rtol=1e-9,
    )
