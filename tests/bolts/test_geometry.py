from importlib.resources import as_file, files

from cassy.bolts.geometry import BoltGeom, InsertGeom
from cassy.general.material import Material
from tests.bolts import res
from cassy.additional_data.templates import bolts as bolt_default
import pytest


class MockMaterial(Material):
    def __init__(self):
        pass


class TestBoltGeom:
    def test_from_excel(self):
        mat = MockMaterial()
        matlist = {"SS660 (non leak-tight)": mat}
        with as_file(files(res).joinpath("M12_bolt.xlsx")) as test_data:
            # Create a BoltGeom instance from the test data
            bolt_geom = BoltGeom.from_excel(test_data, matlist)

    def test_default_excel_templates(self):
        mat = MockMaterial()
        matlist = {"Inconel 718 (non leak tight) SDC-IC": mat}
        with as_file(files(bolt_default).joinpath("M12_bolt.xlsx")) as test_data:
            # Create a BoltGeom instance from the test data
            bolt_geom = BoltGeom.from_excel(test_data, matlist)

        assert bolt_geom.d1 > 10

        matlist = {"SS316L(N)-IG_SDC-IC": mat}
        with as_file(files(bolt_default).joinpath("M12_insert.xlsx")) as test_data:
            # Create a BoltGeom instance from the test data
            insert_geom = InsertGeom.from_excel(test_data, matlist)

        assert insert_geom.dn > 10

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


class TestInsertGeom:
    def test_from_excel(self):
        mat = MockMaterial()
        matlist = {"SS660 (non leak-tight)": mat}
        with as_file(files(res).joinpath("M12_insert.xlsx")) as test_data:
            # Create a BoltGeom instance from the test data
            insert_geom = InsertGeom.from_excel(test_data, matlist)
