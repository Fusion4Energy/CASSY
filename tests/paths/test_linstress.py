import pytest
import math
import numpy as np
import pandas as pd
from cassy.paths.linstress import (
    LinStress,
    LinStressConfig,
    _combine_linstresses,
    _combine_inertial_stresses,
    von_mises,
    STRESS_ORDER,
    SpatialRecMethod,
    StressClassification,
    LoadType,
    PathType,
    ReferenceEvent,
    ReferenceEventConfig,
)
from copy import deepcopy

DF1 = pd.DataFrame(
    [[2, -2, 2, 1, 1, 1], [1, 0, 0, 0, 0, 0], [3, 0, 0, 0, 0, 0]],
    index=["Pm", "Pb", "F"],
    columns=STRESS_ORDER,
)


@pytest.fixture
def config_inertial() -> LinStressConfig:
    return LinStressConfig(
        name="ACC",
        stress_classification=StressClassification.PRIMARY,
        load_type=LoadType.INERTIAL,
        spatial_rec_method=SpatialRecMethod.SRSS,
    )


@pytest.fixture
def inertial_list(config_inertial: LinStressConfig) -> list[LinStress]:
    stresses = []
    for label in ["A", "B", "C"]:
        df = DF1.copy()
        config = deepcopy(config_inertial)
        config.name = f"{config.name} {label}"
        stresses.append(LinStress(df, config))
    return stresses


@pytest.fixture
def vol_stress() -> LinStress:
    df = DF1.copy()
    config = LinStressConfig(
        name="VOL",
        stress_classification=StressClassification.PRIMARY,
        load_type=LoadType.VOLUMETRIC,
    )
    return LinStress(df, config)


def test_combine_linstresses():
    df1 = DF1.copy()
    df2 = DF1.copy()

    assert _combine_linstresses([]) is None

    combined = _combine_linstresses(
        [df1.values, df2.values], SpatialRecMethod.ALGEBRAIC
    )
    assert np.allclose(combined[0, :], np.array([4, -4, 4, 2, 2, 2]))

    combined = _combine_linstresses([df1.values, df2.values], SpatialRecMethod.ABS)
    assert np.allclose(combined[0, :], np.array([4, 4, 4, 2, 2, 2]))

    combined = _combine_linstresses([df1.values, df2.values], SpatialRecMethod.SRSS)
    assert np.allclose(combined[2, :], np.array([4.24264069, 0, 0, 0, 0, 0]))


def test_combine_inertial_stresses(inertial_list: list[LinStress]):
    combined = _combine_inertial_stresses(inertial_list)
    assert len(combined) == 1
    assert np.allclose(
        combined[0].primary.loc["F"].values,
        np.array([math.sqrt(3**2 * 3), 0, 0, 0, 0, 0]),
    )

    with pytest.raises(AssertionError):
        _combine_inertial_stresses(inertial_list[1:])


def test_von_mises():
    vol = np.array([1, 2, 4, 0, 7, 1])
    ine = np.array([2, 3, 1, 0, 0, 0])

    _ = von_mises(vol, ine)
    _ = von_mises(
        vol,
    )
    _ = von_mises(None, ine)
    _ = von_mises(None, None)


class TestLinStress:
    def test_init(self):
        df = DF1.copy()
        config = LinStressConfig(
            name="Test",
            stress_classification=StressClassification.PRIMARY,
            load_type=LoadType.VOLUMETRIC,
            isPressure=True,
            ptype=PathType.FILLET,
        )
        ls = LinStress(df, config)
        assert np.allclose(ls.primary.loc["B"].values, np.zeros(6))
        assert ls.secondary.loc["B"].values[0] == 1


class TestReferenceEvent:
    def test_init(self, vol_stress: LinStress, inertial_list: list[LinStress]):
        refevent_config = ReferenceEventConfig(
            service_lvl="A",
            re_ID="Test",
            T=20,
        )
        refevent = ReferenceEvent([vol_stress] + inertial_list, refevent_config)
        assert len(refevent.inertial) == 1
        assert len(refevent.volumetric) == 1

        # Check that all properties can be computed. No check of values here
        for name in dir(refevent):
            attr = getattr(refevent, name)
            if isinstance(attr, property):
                print(name, getattr(refevent, name))
