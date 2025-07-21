import os
from abc import ABC, abstractmethod
from enum import Enum

import numpy as np
import yaml

from cassy.auxiliary.custom_errors import ConfigError
from cassy.auxiliary.types import PathLike

MATH_SUBSTITUTIONS = {"EXP": np.exp, "SQRT": np.sqrt, "^": "**"}


class PropertyType(Enum):
    CONSTANT = "constant"
    POLYNOMIAL = "polynomial"
    TABLE = "table"
    EQUATION = "equation"
    MULTI = "multi"


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
                raise ValueError(
                    f"Argument {arg} is below the lower bound {self.lower_bound[i]}."
                )
            if (
                self.upper_bound is not None
                and self.upper_bound[i] is not None
                and arg > self.upper_bound[i]
            ):
                raise ValueError(
                    f"Argument {arg} is above the upper bound {self.upper_bound[i]}."
                )

        # if in boounds, safely call the function
        return self._function_to_call(*args)

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


class TableProperty(Property):
    pass


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

    def _function_to_call(self, x: float) -> float:
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
        res = 0
        for i, c in enumerate(self.coeff):
            res += c * (x**i)
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
    pass


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
        # elif prop_type == PropertyType.TABLE.value:
        #     return TableProperty(data)
        elif prop_type == PropertyType.EQUATION.value:
            return EquationProperty(data)
        # elif prop_type == PropertyType.MULTI.value:
        #     return MultiProperty(data)
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


def _cleanNA(df):
    # Drop all rows containing only NaN
    df.dropna(axis=0, how="all", inplace=True)
    # Drop all columns containing only NaN
    df.dropna(axis=1, how="all", inplace=True)

    return df
