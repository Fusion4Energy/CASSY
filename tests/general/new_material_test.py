from importlib.resources import as_file, files

from cassy.general.new_material import Material
from tests.general import res


class TestMaterial:
    def test_init(self):
        with as_file(files(res).joinpath("material_example.yaml")) as config_file:
            material = Material(config_file)

        assert material.nu() == 0.3
        assert int(material.E(500, 100)) == 159
