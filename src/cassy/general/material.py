import logging
import os
from abc import ABC, abstractmethod
from enum import Enum

import numpy as np
import pandas as pd
import yaml
from scipy.interpolate import LinearNDInterpolator
from scipy.optimize import root_scalar
from scipy.spatial import Delaunay

from cassy.auxiliary.custom_errors import ConfigError, OutOfBoundsError
from cassy.auxiliary.types import PathLike

MATH_SUBSTITUTIONS = {"EXP": np.exp, "SQRT": np.sqrt, "^": "**"}


class PropertyType(Enum):
    CONSTANT = "constant"
    POLYNOMIAL = "polynomial"
    TABLE1D = "table1D"
    TABLE2D = "table2D"
    TABLE3D = "table3D"
    EQUATION = "equation"
    MULTI = "multi"
    FATIGUE = "fatigue"


class Property(ABC):
    def __init__(self, data: dict, name: str, material_name: str) -> None:
        """
        Initialize the Property with a dictionary.

        Parameters
        ----------
        dict : dict
            Dictionary containing property data.
        name : str
            Name of the property.
        material_name : str
            Name of the material this property belongs to.
        """
        if "type" not in data:
            raise ConfigError("Property 'type' is missing in the data dictionary.")
        self.type = PropertyType(data["type"])

        self.lower_bound = data.get("lower_bound", None)
        self.upper_bound = data.get("upper_bound", None)
        self.scale_result = float(data.get("scale_result", 1.0))  # Default scale is 1.0

        # particular flags used in fatigue. Defined here for linter
        self.mean_stress = None
        self.ftype = None
        self.name = name
        self.material_name = material_name

    def __call__(self, *args) -> float:
        """
        Compute the property value and bounds.
        """
        # For legacy purposes, allow to provide all input in a tuple
        if len(args) == 1 and isinstance(args[0], tuple):
            args = args[0]
        # Check bounds if they are defined
        for i, arg in enumerate(args):
            if (
                self.lower_bound is not None
                and self.lower_bound[i] is not None
                and arg < self.lower_bound[i]
            ):
                raise OutOfBoundsError(
                    f"Argument {arg} is below the lower bound {self.lower_bound[i]}."
                    f" Property: {self.name}, Material: {self.material_name}"
                )
            if (
                self.upper_bound is not None
                and self.upper_bound[i] is not None
                and arg > self.upper_bound[i]
            ):
                raise OutOfBoundsError(
                    f"Argument {arg} is above the upper bound {self.upper_bound[i]}."
                    f" Property: {self.name}, Material: {self.material_name}"
                )

        # if in boounds, safely call the function
        return self._function_to_call(*args) * self.scale_result

    @abstractmethod
    def _function_to_call(self, *args) -> float:
        """
        Call the function associated with the property.

        Parameters
        ----------
        *args : tuple
            Arguments to pass to the function.

        Returns
        -------
        float
            Result of the function call.
        """
        pass


class NotImplementedProperty(Property):
    def __init__(self, name: str, material_name: str) -> None:
        """
        Placeholder for properties that are not implemented. Helps keep clean the
        intellisense.
        """
        self.name = name
        self.material_name = material_name
        self.lower_bound = None
        self.upper_bound = None

    def _function_to_call(self, *args) -> float:
        raise NotImplementedError(
            f"Property {self.name} not implemented for {self.material_name}"
        )


class Table1DProperty(Property):
    def __init__(self, data: dict, name: str, material_name: str) -> None:
        """
        Initialize the Table1DProperty with a table of values.

        Parameters
        ----------
        data : dict
            Dictionary containing table data.
        name : str
            Name of the property.
        material_name : str
            Name of the material this property belongs to.
        """
        super().__init__(data, name, material_name)
        self.x = data["values"]["x"]
        self.y = data["values"]["y"]
        # override the lower and upper bounds
        self.lower_bound = [min(self.x)]
        self.upper_bound = [max(self.x)]

    def _function_to_call(self, x: float) -> float:
        """Return the value from the table at a given point.

        Parameters
        ----------
        x : float
            x value to look up in the table.
        Returns
        -------
        float
            Value from the table at x.
        """
        return np.interp(x, self.x, self.y)


class Table2DProperty(Property):
    def __init__(self, data: dict, name: str, material_name: str) -> None:
        """
        Initialize the Table2DProperty with a table of values.

        Parameters
        ----------
        data : dict
            Dictionary containing table data.
        name : str
            Name of the property.
        material_name : str
            Name of the material this property belongs to.
        """
        super().__init__(data, name, material_name)
        # Ensure that x and y are read as floats using np arrays
        self.x = np.array(data["values"]["x"], dtype=float)
        self.y = np.array(data["values"]["y"], dtype=float)
        self.vals = np.array(data["values"]["vals"], dtype=float)
        # perform some quality checks on the table
        assert self.vals.shape == (len(self.x), len(self.y))

        # get scale x, y if they are defined
        self.scale_x = float(data.get("scale_x", 1.0))
        self.scale_y = float(data.get("scale_y", 1.0))

        # override the lower and upper bounds
        self.lower_bound = [min(self.x) / self.scale_x, min(self.y) / self.scale_y]
        self.upper_bound = [max(self.x) / self.scale_x, max(self.y) / self.scale_y]

        # Initialize the grid interpolator
        points = []
        for x in self.x:
            for y in self.y:
                points.append([x, y])
        points = np.array(points)
        # Compute the triangulation
        tri = Delaunay(points)
        # Perform the interpolation with the given values:
        self.interpolator = LinearNDInterpolator(tri, self.vals.flatten())

    def _function_to_call(self, x: float, y: float) -> float:
        """Return the value from the table at a given point.

        Parameters
        ----------
        x : float
            x value to look up in the table.
        y : float
            y value to look up in the table.
        Returns
        -------
        float
            Value from the table at (x, y).
        """
        return self.interpolator(x * self.scale_x, y * self.scale_y)


class Table3DProperty(Property):
    def __init__(self, data: dict, name: str, material_name: str) -> None:
        """
        Initialize the Table3DProperty with a table of values.

        Parameters
        ----------
        data : dict
            Dictionary containing table data.
        name : str
            Name of the property.
        material_name : str
            Name of the material this property belongs to.
        """
        super().__init__(data, name, material_name)
        self.scale_x = float(data.get("scale_x", 1.0))
        self.scale_y = float(data.get("scale_y", 1.0))
        self.scale_z = float(data.get("scale_z", 1.0))

        df_values = data["values"]
        cols = data["columns"]
        df = pd.DataFrame(df_values, columns=cols, dtype=float)

        points = []
        values = []
        for _, row in df.iterrows():
            x = row["x"]
            y = row["y"]
            z = row["z"]
            val = row["val"]
            points.append([x, y, z])
            values.append(val)

        # Compute the triangulation
        tri = Delaunay(points)
        # Perform the interpolation with the given values:
        self.interpolator = LinearNDInterpolator(tri, values)

        # Update the bounds. For the number of cycles extrapolation needs to be in the
        # table values
        self.lower_bound = [
            min(df["x"]) / self.scale_x,
            min(df["y"]) / self.scale_y,
            min(df["z"]) / self.scale_z,
        ]
        self.upper_bound = [
            max(df["x"]) / self.scale_x,
            max(df["y"]) / self.scale_y,
            max(df["z"]) / self.scale_z,
        ]

    def _function_to_call(self, x: float, y: float, z: float) -> float:
        """Return the value from the table at a given point.

        Parameters
        ----------
        x : float
            x value to look up in the table.
        y : float
            y value to look up in the table.
        Returns
        -------
        float
            Value from the table at (x, y).
        """
        return self.interpolator(x * self.scale_x, y * self.scale_y, z * self.scale_z)


class Fatigue(Property):
    def __init__(self, data: dict, name: str, material_name: str) -> None:
        """
        Initialize the Fatigue property with a table of values.

        Parameters
        ----------
        data : dict
            Dictionary containing fatigue data.
        name : str
            Name of the property.
        material_name : str
            Name of the material this property belongs to.
        """
        super().__init__(data, name, material_name)
        self.scale_x = float(data.get("scale_x", 1.0))
        self.scale_y = float(data.get("scale_y", 1.0))
        self.mean_stress = data.get("mean_stress", False)
        self.ftype = data["ftype"]
        # For fatigue, values are provided as N cycles Vs strain/stress. Some
        # reorganization of the input is needed to fit the Table2DProperty structure.
        if self.mean_stress:
            tables = data["tables"]
        else:
            tables = {"All": data["values"]}

        interpolators = {}
        for mean_stress, table in tables.items():
            # Add a point for eps 0 and one for eps>max
            T = np.array(table["T"], dtype=float)
            N_cycles_or = np.array(table["N_cycles"], dtype=float)

            matrix_original = table["y"]

            # add extrapolation to the table
            matrix = [matrix_original[0]]
            matrix.extend(matrix_original)
            matrix.append([0] * len(matrix_original[0]))
            N_cycles = [0]
            N_cycles.extend(N_cycles_or.tolist())
            N_cycles.append(max(N_cycles))

            N_cycles = np.array(N_cycles, dtype=float)
            matrix = np.array(matrix, dtype=float)

            points = []
            values = []
            for i, eps_row in enumerate(matrix):
                for j, eps in enumerate(eps_row):
                    point = [T[j], eps]
                    val = N_cycles[i]
                    points.append(point)
                    values.append(val)

            # Compute the triangulation
            tri = Delaunay(points)
            # Perform the interpolation with the given values:
            interpolator = LinearNDInterpolator(tri, values)
            interpolators[mean_stress] = interpolator
        self.interpolators = interpolators

        # Update the bounds. For the number of cycles extrapolation needs to be in the
        # table values.
        self.lower_bound = [min(T), None]
        self.upper_bound = [max(T), None]
        if self.mean_stress:
            # do not put limits for mean stress
            self.lower_bound.append(None)
            self.upper_bound.append(None)

    def _function_to_call(
        self, x: float, y: float, s_mean: float | None = None
    ) -> float:
        """Return the value from the table at a given point.

        Parameters
        ----------
        x : float
            x value to look up in the table.
        y : float
            y value to look up in the table.
        s_mean : float, optional
            Mean stress value, if applicable. If None, the All table is used.
        Returns
        -------
        float
            Value from the table at (x, y).
        """
        if s_mean is None:
            # Use the All table
            interpolator = self.interpolators["All"]
        else:
            interpolator = None
            for mean_stress, interpolator_s in self.interpolators.items():
                if s_mean <= float(mean_stress):
                    interpolator = interpolator_s
                    break
            if interpolator is None:
                # insteading of raising an error, we can use the last interpolator
                # with a warning
                logging.warning(
                    f"Mean stress {s_mean} is above the maximum defined in the "
                    f"fatigue table. Using the last interpolator."
                )
                interpolator = interpolator_s

        return interpolator(x * self.scale_x, y * self.scale_y)


class FatigueInconelRCCMRx(Fatigue):
    def __init__(self, data: dict, name: str, material_name: str) -> None:
        """
        Initialize the FatigueInconelRCCMRx property with a table of values.

        Parameters
        ----------
        data : dict
            Dictionary containing fatigue data.
        name : str
            Name of the property.
        material_name : str
            Name of the material this property belongs to.
        """
        super().__init__(data, name, material_name)
        # add no limits for Sm, Smb, and dstot as they are not used in the
        # interpolation itself
        self.lower_bound.extend([None, None])  # first one added already for mean stress
        self.upper_bound.extend([None, None])  # first one added already for mean stress

    def _function_to_call(
        self, x: float, y: float, Sm: float, Smb: float, ds_tot: float
    ) -> float:
        """Return the value from the table at a given point.

        Parameters
        ----------
        x : float
            x value to look up in the table.
        y : float
            y value to look up in the table.
        Sm : float
            Sm allowable
        Smb : float
            Smb allowable
        ds_tot : float
            Total stress range
        Returns
        -------
        float
            Value from the table at (x, y).
        """
        # Use the All table for this specific fatigue property
        if ds_tot < 2.7 * Sm or ds_tot < 2.7 * Smb:
            curve = "Curve1"
        elif (ds_tot < 3 * Sm and ds_tot >= 2.7 * Sm) or (
            ds_tot < 3.0 * Smb and ds_tot >= 2.7 * Smb
        ):
            curve = "Curve2"
        else:
            raise OutOfBoundsError(
                f"Total stress range {ds_tot} is above the maximum defined in the "
                f"fatigue table."
            )
        interpolator = self.interpolators[curve]

        return interpolator(x * self.scale_x, y * self.scale_y)


class PolynomialProperty(Property):
    def __init__(self, data: dict, name: str, material_name: str) -> None:
        """
        Initialize the PolynomialProperty with coefficients.

        Parameters
        ----------
        coeff : list of float
            Coefficients of the polynomial.
        data : dict
            Dictionary containing polynomial data.
        name : str
            Name of the property.
        """
        super().__init__(data, name, material_name)
        self.coeff = data["coefficients"]

    def _function_to_call(self, *args) -> float:
        """Return the value of the polynomial at a given point.

        Parameters
        ----------
        x : float
            x of the polynomial.
        Returns
        -------
        float
            Value of the polynomial at x.
        """
        x = args[0]
        res = 0
        for i, c in enumerate(self.coeff):
            res += float(c) * (x**i)
        return res


class ConstantProperty(Property):
    def __init__(self, data: dict, name: str, material_name: str) -> None:
        """
        Initialize the ConstantProperty with a constant value.

        Parameters
        ----------
        value : float
            The constant value.
        data : dict
            Dictionary containing constant data.
        name : str
            Name of the property.
        """
        super().__init__(data, name, material_name)
        value = data["value"]
        if value is None:
            value = np.nan
        self.value = float(value)

    def _function_to_call(self, *args) -> float:
        return self.value


class EquationProperty(Property):
    def __init__(self, data: dict, name: str, material_name: str) -> None:
        """
        Initialize the EquationProperty with an equation function.

        Parameters
        ----------
        data : dict
            Dictionary containing equation data.
        name : str
            Name of the property.
        material_name : str
            Name of the material this property belongs to.
        """
        super().__init__(data, name, material_name)
        equation_str = data["equation"]
        args_str = data["args"]
        subs = MATH_SUBSTITUTIONS.copy()

        def equation_func(*args):
            if len(args) != len(args_str):
                raise ConfigError(f"Expected {args_str} arguments, got {args}")
            for i, arg in enumerate(args_str):
                subs[arg] = args[i]

            return eval(equation_str, subs)

        self.equation_func = equation_func

    def _function_to_call(self, *args) -> float:
        return self.equation_func(*args)


class MultiProperty(Property):
    def __init__(
        self, property_dictionary: dict, property_name: str, material_name: str
    ) -> None:
        """
        Initialize the MultiProperty with a list of properties. This property is an
        arbitrary combinations of other property types, each specified in a specific
        validity range.

        Parameters
        ----------
        properties : list of Property
            List of Property instances.
        """
        data = property_dictionary[property_name]
        super().__init__(data, property_name, material_name)
        self.ranges = [
            PropertyFactory.create_property({"A": prop}, "A", material_name)
            for prop in data["ranges"]
        ]

        # go trough the ranges and find the maximum bounds
        for prop in self.ranges:
            if prop.lower_bound is not None:
                if self.lower_bound is None:
                    self.lower_bound = prop.lower_bound
                else:
                    self.lower_bound = [
                        min(self.lower_bound[i], prop.lower_bound[i])
                        for i in range(len(self.lower_bound))
                    ]
            if prop.upper_bound is not None:
                if self.upper_bound is None:
                    self.upper_bound = prop.upper_bound
                else:
                    self.upper_bound = [
                        max(self.upper_bound[i], prop.upper_bound[i])
                        for i in range(len(self.upper_bound))
                    ]

    def _function_to_call(self, *args) -> float:
        """Return the value of the property based on the input arguments.

        Parameters
        ----------
        *args : tuple
            Arguments to pass to the property functions.

        Returns
        -------
        float
            Value of the property based on the input arguments.
        """
        for prop in self.ranges:
            try:
                return prop(*args)
            except OutOfBoundsError:
                continue
        raise OutOfBoundsError(
            f"Input arguments {args} are out of bounds for all ranges."
            f" Property: {self.name}, Material: {self.material_name}"
        )


class PropertyFactory:
    @staticmethod
    def create_property(
        property_dictionary: dict, property_name: str, material_name: str
    ) -> Property:
        """
        Create a Property instance based on the type specified in the data.

        Parameters
        ----------
        data : dict
            Dictionary containing property data.

        Returns
        -------
        Property
            An instance of a Property subclass.
        """
        data = property_dictionary.get(property_name, None)
        if data is None:
            return NotImplementedProperty(property_name, material_name)
        if "type" not in data:
            raise ConfigError(
                f"Property 'type' is missing in the data dictionary of {property_name} for {material_name}."
            )
        prop_type = data["type"]
        if prop_type == PropertyType.CONSTANT.value:
            return ConstantProperty(data, property_name, material_name)
        elif prop_type == PropertyType.POLYNOMIAL.value:
            return PolynomialProperty(data, property_name, material_name)
        elif prop_type == PropertyType.TABLE1D.value:
            return Table1DProperty(data, property_name, material_name)
        elif prop_type == PropertyType.EQUATION.value:
            return EquationProperty(data, property_name, material_name)
        elif prop_type == PropertyType.TABLE2D.value:
            return Table2DProperty(data, property_name, material_name)
        elif prop_type == PropertyType.FATIGUE.value:
            return Fatigue(data, property_name, material_name)
        elif prop_type == PropertyType.MULTI.value:
            return MultiProperty(property_dictionary, property_name, material_name)
        elif prop_type == PropertyType.TABLE3D.value:
            return Table3DProperty(data, property_name, material_name)
        else:
            raise ConfigError(f"Unknown property type: {prop_type}")


class Material:
    def __init__(self, config_file: PathLike, name: str | None = None) -> None:
        # Assign default name if not provided
        if name is None:
            filename = os.path.basename(config_file)
            self.name = filename.split(".")[0]
        else:
            self.name = name
        with open(config_file) as file:
            config = yaml.safe_load(file)

        # Mandatory properties
        data = config["properties"]
        self.nu = PropertyFactory.create_property(data, "Poisson Ratio", self.name)
        self.E = PropertyFactory.create_property(data, "Young Modulus", self.name)
        if data["Fatigue"].get("rccmrx_inconel", False):
            self.N = FatigueInconelRCCMRx(data["Fatigue"], "Fatigue", self.name)
        else:
            self.N = PropertyFactory.create_property(data, "Fatigue", self.name)
        self.Sy_min = PropertyFactory.create_property(
            data, "Min Yield Strength", self.name
        )
        self.Su_min = PropertyFactory.create_property(
            data, "Min Tensile Strength", self.name
        )

        # Optional properties
        self.Sy_moy = PropertyFactory.create_property(
            data, "Mean Yield Strength", self.name
        )
        self.Se = PropertyFactory.create_property(data, "Se", self.name)
        self.Sd = PropertyFactory.create_property(data, "Sd", self.name)
        self.Sd_nopeak = PropertyFactory.create_property(data, "Sd_nopeak", self.name)
        self.m = PropertyFactory.create_property(data, "m", self.name)
        self.K = PropertyFactory.create_property(data, "K", self.name)
        self.Keps = PropertyFactory.create_property(data, "Keps", self.name)
        self.Kmu = PropertyFactory.create_property(data, "Kmu", self.name)
        self.Keff_rec = PropertyFactory.create_property(data, "Keff_rec", self.name)
        self.Sm = PropertyFactory.create_property(data, "Sm", self.name)
        self.Smb = PropertyFactory.create_property(data, "Smb", self.name)
        self.monotonic_min_stress_strain = PropertyFactory.create_property(
            data, "Monotonic Min True Stress Strain", self.name
        )

        self.type: str | None = config.get("type", None)

    def ft_star(self, T: float) -> float:
        """Compute ft_star according to EN13445 part 3, 18.10.6.2. Min temperature is
        conservatively assumed to be room T= 25 celsius"""

        if self.type is None:
            raise NotImplementedError(
                f"Property ft_star not implemented for {self.name}"
            )
        T_min = 25  # Celsius, fix the min temperature conservatively
        T_star = 0.75 * T + 0.25 * T_min
        if T_star < 100:
            return 1
        if self.type == "ferritic":
            res = 1.03 - 1.5e-4 * T_star - 1.5e-6 * T_star**2
        elif self.type == "austenitic":
            res = 1.043 - 4.3e-4 * T_star
        else:
            raise ConfigError(
                f"Material type '{self.type}' is not recognized. (used in EN13445 fatigue)"
                f"Valid types are: 'ferritic', 'austenitic'. See part 3, 18.10.6.2"
            )
        return res

    def cyclic_stress_strain(self, T: float, ds: float, dpa: float = 0) -> float:
        """returns the plastic cyclic de_strain given a d_sigma (Pa) and T"""
        E = self.E(T, dpa) * 1e-6  # convert from Pa to MPa
        K = self.K(T)
        m = self.m(T)
        ds = ds / 1e6  # convert from Pa to MPa

        de_tot = 100 * ds * (2 * (1 + self.nu()) / (3 * E)) + (ds / K) ** (1 / m)

        return de_tot / 100

    def get_Keff(self, T: float, dpa: float, K: float) -> float:
        """Compute the effective K value for the material at given temperature and dpa."""
        # To check if it is the same for all materials
        try:
            k_rect = self.Keff_rec(T, dpa)
        except NotImplementedError:
            # If data is not available assume
            k_rect = 1.5
        return 1 + 2 * (K - 1) * (k_rect - 1)

    def compute_tangent_young(self, sigma: float, T: float, dpa: float = 0) -> float:
        """Compute the tangent Young modulus for the material at given temperature and dpa.

        Parameters
        ----------
        sigma : float
            Stress value in Pa. Young modulus is to be computed tangent to this
            point.
        T : float
            Temperature in Celsius.
        dpa : float, optional
            DPA value for the material, by default 0.

        Returns
        -------
        float
            Tangent Young modulus at the specified temperature and dpa.
        """
        interval = 0.001
        sigma_lower = sigma - interval * sigma
        sigma_upper = sigma + interval * sigma
        eps_lower = self.monotonic_min_stress_strain(sigma_lower, T, dpa)
        eps_upper = self.monotonic_min_stress_strain(sigma_upper, T, dpa)
        E_tangent = (sigma_upper - sigma_lower) / (eps_upper - eps_lower)
        return E_tangent

    def compute_delta_sigma_Neuber(
        self,
        T: float,
        delta_sigma_N: float,
        Kf: float,
        dpa: float = 0,
        monotonic: bool = False,
    ) -> float:
        """Compute the Neuber's rule for the given material.

        Parameters
        ----------
        T : float
            temperature in celsius
        delta_sigma_N : float
            nominal stress range
        Kf : float
            intensification factor
        dpa : float, optional
            dpa value for the material, by default 0
        monotonic : bool, optional
            if True, the monotonic stress-strain curve is used, by default the cyclic
            stress-strain curve is used.

        Returns
        -------
        float
            resulting equivalent stress range after Neuber
        """
        if monotonic:
            s_lower_bound = self.monotonic_min_stress_strain.lower_bound[0]
            s_upper_bound = self.monotonic_min_stress_strain.upper_bound[0]

        def _hyperbole(x, x1, y1, Kf=4):
            if x == 0:
                return np.inf
            return Kf**2 * x1 * y1 / x

        def _intersection(sigma, epsN, sigmaN, T, Kf=4):
            if monotonic:
                eps = self.monotonic_min_stress_strain(sigma, T, dpa)
            else:
                eps = self.cyclic_stress_strain(T, sigma)
            if np.isnan(eps):
                # just take a large value
                eps = np.inf
            return _hyperbole(sigma, sigmaN, epsN, Kf) - eps

        delta_eps_N = delta_sigma_N / self.E(T, dpa)

        if monotonic:
            bounds = [
                s_lower_bound,
                s_upper_bound,
            ]
        else:
            bounds = [0, 2000 * 1e6]  # should be enough for all application ranges
        sol = root_scalar(
            _intersection,
            args=(delta_eps_N, delta_sigma_N, T, Kf),
            bracket=bounds,
            method="brentq",
        )

        return sol.root


def read_materials(mat_folder: PathLike) -> dict[str, Material]:
    """Parse all materials listed in a folder as excel files.

    Parameters
    ----------
    mat_folder : os.PathLike
        folder containing the excel files describing the materials data

    Returns
    -------
    dict[str, Material]
        parsed material objects
    """
    materials = {}
    for file in os.listdir(mat_folder):
        if file.endswith(".yaml") or file.endswith(".yml"):
            logging.info("Reading {}".format(file))
            filepath = os.path.join(mat_folder, file)
            matname = file.split(".")[0]
            material = Material(filepath, name=matname)
            materials[matname] = material

    return materials
