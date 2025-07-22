import os
from abc import ABC, abstractmethod
from enum import Enum

import numpy as np
import yaml
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import Delaunay

from cassy.auxiliary.custom_errors import ConfigError, OutOfBoundsError
from cassy.auxiliary.types import PathLike

MATH_SUBSTITUTIONS = {"EXP": np.exp, "SQRT": np.sqrt, "^": "**"}


class PropertyType(Enum):
    CONSTANT = "constant"
    POLYNOMIAL = "polynomial"
    TABLE1D = "table1D"
    TABLE2D = "table2D"
    EQUATION = "equation"
    MULTI = "multi"
    FATIGUE = "fatigue"


class Property(ABC):
    def __init__(self, data: dict) -> None:
        """
        Initialize the Property with a dictionary.

        Parameters
        ----------
        dict : dict
            Dictionary containing property data.
        """
        if "type" not in data:
            raise ConfigError("Property 'type' is missing in the data dictionary.")
        self.type = PropertyType(data["type"])

        self.lower_bound = data.get("lower_bound", None)
        self.upper_bound = data.get("upper_bound", None)
        self.scale_result = float(data.get("scale_result", 1.0))  # Default scale is 1.0

    def __call__(self, *args) -> float:
        """
        Compute the property value and bounds.
        """
        # Check bounds if they are defined
        for i, arg in enumerate(args):
            if (
                self.lower_bound is not None
                and self.lower_bound[i] is not None
                and arg < self.lower_bound[i]
            ):
                raise OutOfBoundsError(
                    f"Argument {arg} is below the lower bound {self.lower_bound[i]}."
                )
            if (
                self.upper_bound is not None
                and self.upper_bound[i] is not None
                and arg > self.upper_bound[i]
            ):
                raise OutOfBoundsError(
                    f"Argument {arg} is above the upper bound {self.upper_bound[i]}."
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


class Table1DProperty(Property):
    def __init__(self, data: dict) -> None:
        """
        Initialize the Table1DProperty with a table of values.

        Parameters
        ----------
        data : dict
            Dictionary containing table data.
        """
        super().__init__(data)
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
    def __init__(self, data: dict) -> None:
        """
        Initialize the Table2DProperty with a table of values.

        Parameters
        ----------
        data : dict
            Dictionary containing table data.
        """
        super().__init__(data)
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


class Fatigue(Property):
    def __init__(self, data: dict) -> None:
        """
        Initialize the Fatigue property with a table of values.

        Parameters
        ----------
        data : dict
            Dictionary containing fatigue data.
        """
        super().__init__(data)
        self.scale_x = float(data.get("scale_x", 1.0))
        self.scale_y = float(data.get("scale_y", 1.0))
        # For fatigue, values are provided as N cycles Vs strain/stress. Some
        # reorganization of the input is needed to fit the Table2DProperty structure.

        # Add a point for eps 0 and one for eps>max
        T = np.array(data["values"]["T"], dtype=float)
        N_cyles = np.array(data["values"]["N_cyles"], dtype=float)

        matrix_original = data["values"]["y"]

        # add extrapolation to the table
        matrix = [matrix_original[0]]
        matrix.extend(matrix_original)
        matrix.append([0] * len(matrix_original[0]))
        N_cycles = [0]
        N_cycles.extend(N_cyles.tolist())
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
        self.interpolator = LinearNDInterpolator(tri, values)
        self.ftype = data["ftype"]

        # Update the bounds. For the number of cycles extrapolation needs to be in the
        # table values
        self.lower_bound = [min(T), None]
        self.upper_bound = [max(T), None]

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


class PolynomialProperty(Property):
    def __init__(self, data: dict) -> None:
        """
        Initialize the PolynomialProperty with coefficients.

        Parameters
        ----------
        coeff : list of float
            Coefficients of the polynomial.
        """
        super().__init__(data)
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
    def __init__(self, data: dict) -> None:
        """
        Initialize the ConstantProperty with a constant value.

        Parameters
        ----------
        value : float
            The constant value.
        """
        super().__init__(data)
        self.value = data["value"]

    def _function_to_call(self, *args) -> float:
        return self.value


class EquationProperty(Property):
    def __init__(self, data: dict) -> None:
        """
        Initialize the EquationProperty with an equation function.

        Parameters
        ----------
        equation_func : Callable
            Function that computes the property value based on arguments.
        """
        super().__init__(data)
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
    def __init__(self, data: dict) -> None:
        """
        Initialize the MultiProperty with a list of properties. This property is an
        arbitrary combinations of other property types, each specified in a specific
        validity range.

        Parameters
        ----------
        properties : list of Property
            List of Property instances.
        """
        super().__init__(data)
        self.ranges = [PropertyFactory.create_property(prop) for prop in data["ranges"]]

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
        raise OutOfBoundsError("Input arguments are out of bounds for all ranges.")


class PropertyFactory:
    @staticmethod
    def create_property(data: dict) -> Property:
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
        if "type" not in data:
            raise ConfigError("Property 'type' is missing in the data dictionary.")
        prop_type = data["type"]
        if prop_type == PropertyType.CONSTANT.value:
            return ConstantProperty(data)
        elif prop_type == PropertyType.POLYNOMIAL.value:
            return PolynomialProperty(data)
        elif prop_type == PropertyType.TABLE1D.value:
            return Table1DProperty(data)
        elif prop_type == PropertyType.EQUATION.value:
            return EquationProperty(data)
        elif prop_type == PropertyType.TABLE2D.value:
            return Table2DProperty(data)
        elif prop_type == PropertyType.FATIGUE.value:
            return Fatigue(data)
        elif prop_type == PropertyType.MULTI.value:
            return MultiProperty(data)
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
        self.nu = PropertyFactory.create_property(data["Poisson Ratio"])
        self.E = PropertyFactory.create_property(data["Young Modulus"])
        self.K = PropertyFactory.create_property(data["K"])
        self.m = PropertyFactory.create_property(data["m"])
        self.Keps = PropertyFactory.create_property(data["Keps"])
        self.Kmu = PropertyFactory.create_property(data["Kmu"])
        self.Keff_rec = PropertyFactory.create_property(data["Keff_rec"])
        self.N = PropertyFactory.create_property(data["Fatigue"])
        self.Sm = PropertyFactory.create_property(data["Sm"])
        self.Sy_min = PropertyFactory.create_property(data["Min Yield Strength"])
