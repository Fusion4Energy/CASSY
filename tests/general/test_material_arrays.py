from importlib.resources import as_file, files
from itertools import product

import numpy as np
import pytest
import yaml

from cassy.additional_data import materials
from cassy.auxiliary import trace
from cassy.auxiliary.custom_errors import OutOfBoundsError
from cassy.general.material import FatigueInconelRCCMRx, PropertyFactory


def make_property(data):
    return PropertyFactory.create_property({"test": data}, "test", "array test")


@pytest.mark.parametrize("values", [
    np.array([]), np.array([1.]), np.array([0., 1., 2.]), np.array([-1., 1., 3.]),
])
@pytest.mark.parametrize("definition", [
    {"type": "table1D", "values": {"x": [0, 2], "y": [1, 5]}},
    {"type": "multi", "ranges": [
        {"type": "table1D", "values": {"x": [0, 2], "y": [1, 5]}},
    ]},
])
def test_array_lookup_skips_trace_and_preserves_scalar_trace(values, definition, monkeypatch):
    prop = make_property(definition)
    expected = prop(values)
    tracer = trace.Tracer()

    def unexpected_trace(*args, **kwargs):
        pytest.fail("Array interpolation must not enter or record a trace")

    with monkeypatch.context() as patch:
        patch.setattr(trace, "nested", unexpected_trace)
        patch.setattr(trace, "record_property", unexpected_trace)
        with trace.activate(tracer):
            actual = prop(values)
    np.testing.assert_array_equal(actual, expected)
    assert isinstance(actual, np.ndarray)
    assert tracer.records == []

    with trace.activate(tracer):
        scalar = prop(1.)
    assert scalar == 3.
    assert len(tracer.records) == 1
    assert tracer.records[0]["name"] == "test"
    assert tracer.records[0]["value"] == 3.


def assert_scalar_parity(prop, *args):
    arrays = np.broadcast_arrays(*args)
    expected = np.full(arrays[0].shape, np.nan)
    for index in np.ndindex(expected.shape):
        try:
            expected[index] = prop(*(float(arg[index]) for arg in arrays))
        except OutOfBoundsError:
            pass
    actual = prop(*args)
    assert isinstance(actual, np.ndarray)
    assert actual.shape == expected.shape
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=0, equal_nan=True)
    return actual


def property_grid(prop, data):
    arity = max(len(prop.lower_bound or []), len(prop.upper_bound or []),
                len(data.get("args", [])), 2)
    if data["type"] == "table1D":
        arity = 1
    elif data["type"] == "table3D":
        arity = 3
    axes = []
    for index in range(arity):
        lower = (prop.lower_bound or [None] * arity)[index]
        upper = (prop.upper_bound or [None] * arity)[index]
        lower = (20.0 if index == 0 else 0.0) if lower is None else lower
        upper = (400.0 if index == 0 else 2.0) if upper is None else upper
        axes.append(np.unique([lower, (lower + upper) / 2, upper]))
    return np.meshgrid(*axes, indexing="ij")


def check_definition(data, name):
    if data.get("rccmrx_inconel"):
        prop = FatigueInconelRCCMRx(data, name, "array test")
        assert_scalar_parity(
            prop, np.array([20., 150., 300., 500.])[:, None],
            np.array([0., .001, .005, .05])[None, :],
            500e6, 350e6, np.array([250e6, 960e6, 1.1e9, 1.5e9])[None, :],
        )
    else:
        prop = PropertyFactory.create_property({name: data}, name, "array test")
        if data["type"] == "fatigue":
            for mean, (temperatures, cycles, matrix) in prop.tables.items():
                for temperature in np.unique(
                    np.concatenate((temperatures, (temperatures[:-1] + temperatures[1:]) / 2))
                ):
                    values = np.unique(np.concatenate(
                        (matrix.ravel(), (matrix[:-1] + matrix[1:]).ravel() / 2,
                         [0, matrix.max() * 1.1])
                    )) / prop.scale_y
                    args = (np.full(values.shape, temperature / prop.scale_x), values)
                    if prop.mean_stress:
                        args += (np.full(values.shape, float(mean)),)
                    assert_scalar_parity(prop, *args)
        else:
            assert_scalar_parity(prop, *property_grid(prop, data))
    for range_data in data.get("ranges", []):
        check_definition(range_data, name + " range")


@pytest.mark.parametrize("resource", sorted(
    (entry for entry in files(materials).iterdir() if entry.name.endswith(".yaml")),
    key=lambda entry: entry.name,
), ids=lambda entry: entry.name)
def test_every_bundled_property_matches_scalar_calls(resource):
    with as_file(resource) as path:
        with path.open() as stream:
            data = yaml.safe_load(stream)
    for name, definition in data["properties"].items():
        check_definition(definition, name)


@pytest.mark.parametrize("data", [
    {"type": "constant", "value": 7, "lower_bound": [0], "upper_bound": [2]},
    {"type": "polynomial", "coefficients": [1, 2], "lower_bound": [0], "upper_bound": [2]},
    {"type": "table1D", "values": {"x": [0, 2], "y": [1, 5]}},
    {"type": "equation", "args": ["x"], "equation": "SQRT(x) + EXP(x)",
     "lower_bound": [0], "upper_bound": [2]},
])
def test_bounds_broadcast_empty_tuple_and_scalar_preservation(data):
    prop = make_property(data)
    values = np.array([-1., 0., 1., 2., 3.])
    original = values.copy()
    result = assert_scalar_parity(prop, values)
    np.testing.assert_array_equal(values, original)
    np.testing.assert_array_equal(prop((values,)), result)
    assert prop(np.array([], dtype=float)).shape == (0,)
    assert np.isnan(prop(np.array([-1., 3.]))).all()
    with pytest.raises(OutOfBoundsError):
        prop(-1.)
    scalar = prop(1.)
    assert np.ndim(scalar) == 0
    assert prop(np.array(1.)) == scalar
    np.testing.assert_array_equal(result, prop(values))


def test_multi_first_range_nan_and_gap():
    prop = make_property({
        "type": "multi", "scale_result": 2,
        "ranges": [
            {"type": "constant", "value": None, "lower_bound": [0], "upper_bound": [1]},
            {"type": "constant", "value": 3, "lower_bound": [1], "upper_bound": [2]},
            {"type": "constant", "value": 5, "lower_bound": [3], "upper_bound": [4]},
        ],
    })
    values = np.array([0., 1., 1.5, 2.5, 3.5, 5.])
    result = assert_scalar_parity(prop, values)
    np.testing.assert_allclose(result, [np.nan, np.nan, 6, np.nan, 10, np.nan])


def test_nested_multi_gap_falls_through_to_next_range():
    prop = make_property({
        "type": "multi",
        "ranges": [
            {"type": "multi", "ranges": [
                {"type": "constant", "value": 1, "lower_bound": [0], "upper_bound": [1]},
                {"type": "constant", "value": 3, "lower_bound": [3], "upper_bound": [4]},
            ]},
            {"type": "constant", "value": 2, "lower_bound": [1], "upper_bound": [3]},
        ],
    })
    result = assert_scalar_parity(prop, np.array([.5, 1., 1.5, 2.5, 3., 3.5]))
    np.testing.assert_array_equal(result, [1, 1, 2, 2, 3, 3])


def test_fatigue_flat_segments_mean_stress_and_broadcast():
    table = {"T": [20, 100], "N_cycles": [10, 100, 1000, 10000],
             "y": [[4, 3], [2, 2], [2, 2], [1, 1]]}
    prop = make_property({
        "type": "fatigue", "ftype": "strain", "mean_stress": True,
        "tables": {100: table, 200: {**table, "y": [[8, 6], [4, 4], [4, 4], [2, 2]]}},
    })
    result = assert_scalar_parity(
        prop, np.array([20., 60., 100.])[:, None],
        np.array([0., 1., 2., 2.5, 3., 4., 8., 9.])[None, :], 100.,
    )
    assert np.all(result[:, 2] == 1000)
    assert np.isnan(result[:, -1]).all()
    assert_scalar_parity(prop, np.full(6, 60.), 2.5, np.array([0, 100, 101, 200, 201, 300]))


def test_table3d_and_multidimensional_broadcast():
    data = {"type": "table3D", "columns": ["x", "y", "z", "val"],
            "values": [[x, y, z, x + 2*y + 3*z] for x, y, z in product([0, 1], repeat=3)]}
    prop = make_property(data)
    result = assert_scalar_parity(prop, np.array([0, .5, 1])[:, None], .5,
                                  np.array([0, .5, 1])[None, :])
    assert result.shape == (3, 3)
    assert np.isnan(prop(np.array([-1, 2]), .5, .5)).all()


def test_constant_broadcasts_unused_arguments_and_keeps_scalar_type():
    prop = make_property({"type": "constant", "value": 7})
    assert type(prop()) is float
    assert_scalar_parity(prop, np.array([0, 1])[:, None], np.array([2, 3, 4])[None, :])


def test_traced_method_skips_array_calls():
    with as_file(files(materials).joinpath("SS316L(N)-IG_SDC-IC.yaml")) as path:
        from cassy.general.material import Material
        material = Material(path)
    tracer = trace.Tracer()
    with trace.activate(tracer):
        values = material.cyclic_stress_strain(np.array([20., 200.]), np.array([1e8, 2e8]))
    assert isinstance(values, np.ndarray)
    # scalar lookups done inside (e.g. nu()) are still traced, the array one is not
    assert "cyclic_stress_strain" not in [record["name"] for record in tracer.records]
    tracer = trace.Tracer()
    with trace.activate(tracer):
        material.cyclic_stress_strain(20., 1e8)
    assert [record["name"] for record in tracer.records] == ["cyclic_stress_strain"]
