from importlib.resources import as_file, files

from cassy.additional_data import materials
from cassy.general.material import Material

# Add path to material files
RES = files(materials)


class TestMaterial:
    def _test_Sy(self, material, T, DPA, expected):
        tolerance = 1e-4
        assert abs(material.Sy_min((T, DPA)) - expected) < tolerance

    def _test_Su(self, material, T, DPA, expected):
        tolerance = 1e-4
        assert abs(material.Su_min((T, DPA)) - expected) < tolerance

    def test_SS316LNIG(self):
        with as_file(RES.joinpath("SS316L(N)-IG.xlsx")) as mat_path:
            material = Material(mat_path)

        self._test_Sy(material, 227, 0, 138.95969295515 * 1e6)

    def test_eurofer(self):
        with as_file(RES.joinpath("EUROFER.xlsx")) as mat_path:
            material = Material(mat_path)

        self._test_Sy(material, 295, 0, 429.3 * 1e6)
        self._test_Su(material, 295, 0, 545.9 * 1e6)
