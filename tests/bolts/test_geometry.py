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


class TestInsertGeom:
    def test_defaults(self):
        insert_geom = InsertGeom(
            name="TestInsert", material=MockMaterial(), p=1.75, d=12
        )
        assert pytest.approx(insert_geom.dn, 0.01) == 9.85
