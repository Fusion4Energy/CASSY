from importlib.resources import as_file, files

from cassy.bolts.geometry import BoltGeom, InsertGeom
from cassy.general.material import Material
from tests.bolts import res


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


class TestInsertGeom:
    def test_from_excel(self):
        mat = MockMaterial()
        matlist = {"SS660 (non leak-tight)": mat}
        with as_file(files(res).joinpath("M12_insert.xlsx")) as test_data:
            # Create a BoltGeom instance from the test data
            insert_geom = InsertGeom.from_excel(test_data, matlist)
