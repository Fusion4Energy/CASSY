import math

from cassy.bolts.geometry import BoltGeom, InsertGeom
from cassy.general.material import Material
import pytest


class MockMaterial(Material):
    def __init__(self):
        pass


class TestBoltGeom:
    def test_defaults(self):
        # Create a BoltGeom instance with only the required parameters
        bolt_geom = BoltGeom(name="TestBolt", material=MockMaterial(), p=1.75, d=12)
        # Check that the default values are set correctly
        assert pytest.approx(bolt_geom.df, 0.01) == 10.86
        assert pytest.approx(bolt_geom.dn, 0.01) == 9.85
        assert pytest.approx(bolt_geom.D, 0.01) == 10.11
        assert pytest.approx(bolt_geom.d1, 0.01) == 12.00
        assert pytest.approx(bolt_geom.a, 0.01) == 18.00
        assert pytest.approx(bolt_geom.H, 0.01) == 7.50

    def test_none_fields_are_computed(self):
        bolt_geom = BoltGeom(
            name="TestBolt", material=MockMaterial(), p=1.75, d=12, dn=None, Dp=None
        )
        assert pytest.approx(bolt_geom.dn, 0.01) == 9.85
        assert pytest.approx(bolt_geom.Dp, 0.01) == 13.2

    def test_section_thread_root(self):
        # standard bolt: the thread root is the section of least diameter
        bolt_geom = BoltGeom(name="TestBolt", material=MockMaterial(), p=1.75, d=12)
        assert bolt_geom.ds == bolt_geom.dn
        assert pytest.approx(bolt_geom.An) == math.pi / 4 * bolt_geom.dn**2

    def test_section_reduced_shank(self):
        # reduced shank: the smooth shank is the section of least diameter
        bolt_geom = BoltGeom(
            name="TestBolt", material=MockMaterial(), p=1.75, d=12, d1=9, d_vh=2
        )
        assert bolt_geom.ds == 9
        assert pytest.approx(bolt_geom.An) == math.pi / 4 * (9**2 - 2**2)
        assert pytest.approx(bolt_geom.Z) == math.pi / 32 * (9**4 - 2**4) / 9


class TestInsertGeom:
    def test_defaults(self):
        insert_geom = InsertGeom(
            name="TestInsert", material=MockMaterial(), p=1.75, d=12
        )
        assert pytest.approx(insert_geom.dn, 0.01) == 9.85
        assert insert_geom.ds == insert_geom.dn
