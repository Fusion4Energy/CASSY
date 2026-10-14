import json

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


def test_save_load_roundtrip_and_html(tmp_path):
    tracer = trace.Tracer({"module": "test"})
    with trace.activate(tracer), trace.scope(component="C 1", item="P1"):
        with trace.scope(rule="R1", equation="eq 1"):
            trace.record("applied/allowable", 1.2, kind="result")
        trace.record("text", "<b>escaped</b>")
    tracer.save(tmp_path)

    df = trace.load_trace(tmp_path)
    assert len(df) == 2
    assert df.attrs["metadata"]["module"] == "test"
    assert df.loc[0, "value"] == pytest.approx(1.2)

    index = write_html(df, tmp_path, df.attrs["metadata"])
    page = (tmp_path / "C_1.html").read_text(encoding="utf-8")
    assert "&lt;b&gt;escaped&lt;/b&gt;" in page
    assert "fail" in page  # ratio >= 1 is flagged
    assert "C_1.html" in open(index, encoding="utf-8").read()
