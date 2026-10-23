import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cassy.auxiliary import trace
from cassy.office.trace_report import write_html


def test_record_is_noop_when_inactive():
    trace.record("x", 1.0)
    with trace.scope(item="a"):
        trace.record("y", 2.0)
    assert not trace.is_active()


def test_scope_nesting_and_values():
    tracer = trace.Tracer()
    with trace.activate(tracer):
        trace.record("top", 1)
        with trace.scope(component="C1", item="P1"):
            with trace.scope(rule="R1"):
                trace.record("Sm", np.float64(150e6), kind="material", inputs=[20, 0])
            trace.record("branch", "level A", kind="branch")
    assert not trace.is_active()

    df = tracer.to_dataframe()
    assert list(df["name"]) == ["top", "Sm", "branch"]
    sm = df.iloc[1]
    assert sm["component"] == "C1" and sm["item"] == "P1" and sm["rule"] == "R1"
    assert sm["value"] == pytest.approx(150e6)
    assert json.loads(sm["inputs"]) == [20, 0]
    branch = df.iloc[2]
    assert pd.isna(branch["rule"])
    assert branch["text"] == "level A" and pd.isna(branch["value"])


def test_unknown_scope_key():
    with trace.activate(trace.Tracer()):
        with pytest.raises(KeyError):
            with trace.scope(foo="bar"):
                pass


def test_nested_suppresses_inner_records():
    tracer = trace.Tracer()
    with trace.activate(tracer):
        with trace.nested() as outer:
            assert outer
            with trace.nested() as inner:
                assert not inner
            trace.record("hidden", 1)
        trace.record("visible", 2)
    assert list(tracer.to_dataframe()["name"]) == ["visible"]


def _embedded_payload(page: str) -> dict:
    start = page.index("id='data'>") + len("id='data'>")
    return json.loads(page[start : page.index("</script>", start)])


def test_save_load_roundtrip_and_html(tmp_path):
    tracer = trace.Tracer({"module": "test"})
    with trace.activate(tracer), trace.scope(component="C 1", item="P1"):
        with trace.scope(rule="R1", equation="eq 1"):
            trace.record("applied", 1.2e6, kind="result", unit="Pa")
            trace.record("allowable", 1e6, kind="result", unit="Pa")
            trace.record("applied/allowable", 1.2, kind="result")
        trace.record("text", "<b>escaped</b>")
    tracer.save(tmp_path)

    df = trace.load_trace(tmp_path)
    assert len(df) == 4
    assert df.attrs["metadata"]["module"] == "test"
    assert df.loc[0, "value"] == pytest.approx(1.2e6)

    index = write_html(df, tmp_path, df.attrs["metadata"])
    page = (tmp_path / "C_1.html").read_text(encoding="utf-8")
    assert "<b>escaped</b>" not in page
    payload = _embedded_payload(page)
    assert "<b>escaped</b>" in payload["strings"]
    # [group, applied, allowable, ratio, verdict, superseded]
    assert payload["equations"][0][1:] == [1.2e6, 1e6, pytest.approx(1.2), 1, 0]
    assert payload["summary"]["failed"]
    assert payload["summary"]["counts"]["FAILED"] == 1
    index_page = Path(index).read_text(encoding="utf-8")
    # a single component: the index redirects to its page
    assert "url=C_1.html" in index_page and "FAILED" in index_page


def _equation(applied, allowable, superseded=False):
    with trace.scope(equation="eq"):
        if superseded:
            trace.record("superseded", "yes", kind="branch")
        trace.record("applied", applied, kind="result", unit="Pa")
        trace.record("allowable", allowable, kind="result", unit="Pa")


def test_html_verdicts_and_index(tmp_path):
    tracer = trace.Tracer()
    with trace.activate(tracer):
        with trace.scope(component="A", item="P1", position="begin", event="LS1"):
            with trace.scope(analysis="immediate", rule="R1"):
                _equation(2.0, 1.0, superseded=True)  # not counted
            with trace.scope(analysis="immediate", rule="R2"):
                _equation(1.0, float("nan"))  # no limit
            with trace.scope(analysis="immediate", rule="R3"):
                _equation(0.5, 1.0)
                trace.record("x", "not computed", kind="warning")
        with trace.scope(component="B", item="P2", position="begin"):
            for event, vj in (("F1", 0.7), ("F2", 0.6)):
                with trace.scope(event=event, analysis="fatigue"):
                    trace.record("Vj", vj, kind="result")
    metadata = {"damage types": {"R1": "Ratcheting"}}
    index = write_html(tracer.to_dataframe(), tmp_path, metadata)

    summ_a = _embedded_payload((tmp_path / "A.html").read_text("utf-8"))["summary"]
    assert not summ_a["failed"]
    assert summ_a["counts"] == {
        "OK": 1,
        "FAILED": 0,
        "Assessment not required": 1,
        "superseded": 1,
    }
    assert summ_a["worst_ratio"] == pytest.approx(0.5)
    assert summ_a["warnings"] == 1
    # [failed items, assessed items] per damage type, rules not listed are immediate
    assert summ_a["damage"] == {"Immediate": [0, 1], "Ratcheting": [0, 1]}
    # cumulative fatigue usage above 1 fails the item
    summ_b = _embedded_payload((tmp_path / "B.html").read_text("utf-8"))["summary"]
    assert summ_b["failed"] and summ_b["worst_usage"] == pytest.approx(1.3)
    assert summ_b["damage"] == {"Fatigue": [1, 1]}
    index_page = Path(index).read_text(encoding="utf-8")
    assert "url=" not in index_page
    assert "A.html" in index_page and "B.html" in index_page
    assert "Ratcheting: failed items" in index_page
    assert "damage types" not in index_page


def test_duplicates_units_and_named_inputs():
    tracer = trace.Tracer()
    with trace.activate(tracer):
        trace.record("E", 2e11, kind="material")
        trace.record("E", 2e11, kind="material")
        with trace.scope(item="P1"):
            trace.record("E", 2e11, kind="material")
        trace.record("allowable 1", 1e8, kind="allowable")
        trace.record_property("Sm", 1e8, (20, 0.0), "steel")
        trace.record_property("unknown", 1.0, (20, 0.0), "steel")
    df = tracer.to_dataframe()
    assert list(df["name"]) == ["E", "E", "allowable 1", "Sm", "unknown"]
    assert list(df["seq"]) == [0, 1, 2, 3, 4]
    assert df.loc[2, "unit"] == "Pa"
    assert df.loc[3, "unit"] == "Pa"
    assert json.loads(df.loc[3, "inputs"]) == {"T": 20, "dpa": 0.0}
    assert json.loads(df.loc[4, "inputs"]) == [20, 0.0]


def test_superseded_equations():
    from types import SimpleNamespace

    from cassy.designcodes.codes import superseded_equations

    rule = SimpleNamespace(sequential=True)
    # screening failed, follow-ups govern (lower max ratio)
    assert superseded_equations(rule, [(3.0, 2.0), (1.0, 2.0), (2.5, 2.0)]) == {0}
    # everything failed but the screening has the lowest ratio: it governs
    assert superseded_equations(rule, [(3.0, 2.0), (1.0, 2.0), (4.0, 2.0)]) == {1, 2}
    # follow-ups not evaluated
    assert superseded_equations(rule, [(1.0, 2.0), (None, None), (None, None)]) == set()
    assert superseded_equations(rule, None) == set()
    # not a sequential rule
    assert superseded_equations(SimpleNamespace(), [(3.0, 2.0), (1.0, 2.0)]) == set()


def test_record_equations_unique_names_and_superseded():
    from types import SimpleNamespace

    from cassy.designcodes.codes import _record_equations

    rule = SimpleNamespace(
        description=["3Sm rule", "Efficiency Index", "Efficiency Index"],
        sequential=True,
    )
    tracer = trace.Tracer()
    with trace.activate(tracer):
        with trace.scope(item="evaluated"):
            trace.equation_terms(("s1", "a1"), ("s2", "a2"), ("s3", "a3"))
            _record_equations(rule, [(3.0, 2.0), (1.0, 2.0), (1.5, 2.0)])
        with trace.scope(item="skipped"):
            _record_equations(rule, [(1.0, 2.0), (None, None), (None, None)])
    df = tracer.to_dataframe()
    evaluated = df[df["item"] == "evaluated"]
    assert set(evaluated["equation"]) == {
        "3Sm rule",
        "Efficiency Index (eq. 2)",
        "Efficiency Index (eq. 3)",
    }
    superseded = df[df["name"] == "superseded"]
    assert list(superseded["item"]) == ["evaluated"]
    assert list(superseded["equation"]) == ["3Sm rule"]
    assert (df[df["item"] == "skipped"]["name"] == "equation").sum() == 2
    # declared terms go to the source of the results and are consumed by the rule
    applied = df[(df["name"] == "applied") & (df["item"] == "evaluated")]
    assert list(applied["source"]) == ["s1", "s2", "s3"]
    allowable = df[(df["name"] == "allowable") & (df["item"] == "evaluated")]
    assert list(allowable["source"]) == ["a1", "a2", "a3"]
    skipped = df[(df["name"] == "applied") & (df["item"] == "skipped")]
    assert skipped["source"].isna().all()


def test_html_bolts_context_geometries(tmp_path):
    import pyvista as pv

    shared, other = tmp_path / "shared.stl", tmp_path / "other.stl"
    pv.Cube().save(shared)
    pv.Sphere().save(other)
    locations = tmp_path / "loc.csv"
    locations.write_text("flange,boltID,x,y,z\nF1,B1,0,0,0\nF3,B1,1,1,1\n")
    tracer = trace.Tracer({"module": "bolts"})
    with trace.activate(tracer):
        for flange in ("F1", "F3"):
            with trace.scope(component=flange, item="B1", rule="R1"):
                _equation(0.5, 1.0)
    # F2 is not in the trace, F4 shares the geometry of F1, F5 has none
    geometry = {
        "F1": (locations, shared),
        "F2": (locations, other),
        "F3": (locations, None),
        "F4": (locations, shared),
        "F5": (locations, None),
    }
    out = tmp_path / "trace"
    (out / "geometry").mkdir(parents=True)
    (out / "geometry" / "stale.js").write_text("")
    write_html(tracer.to_dataframe(), out, tracer.metadata, geometry)

    page = (out / "F1.html").read_text("utf-8")
    payload = _embedded_payload(page)["geometry"]
    # only the items of the flange, the other geometries as context
    assert set(payload["items"]) == {"B1"}
    assert [c["name"] for c in payload["context"]] == ["F2"]
    key = payload["context"][0]["key"]
    assert f"<script src='geometry/{key}.js'></script>" in page
    context_f3 = _embedded_payload((out / "F3.html").read_text("utf-8"))["geometry"]
    assert [c["name"] for c in context_f3["context"]] == ["F1", "F2"]
    assert "mesh" not in context_f3
    assert sorted(p.name for p in (out / "geometry").iterdir()) == sorted(
        f"{c['key']}.js" for c in context_f3["context"]
    )

    # no context for the paths
    tracer.metadata["module"] = "paths"
    out_paths = tmp_path / "paths"
    write_html(
        tracer.to_dataframe(), out_paths, tracer.metadata, {"F1": (None, shared)}
    )
    assert not (out_paths / "geometry").exists()
