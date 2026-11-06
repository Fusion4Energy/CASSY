import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Set as AbstractSet
from enum import Enum

import numpy as np
import pandas as pd
import yaml
from scipy.interpolate import LinearNDInterpolator
from scipy.optimize import root_scalar
from scipy.spatial import Delaunay

from cassy.auxiliary import trace
from cassy.auxiliary.custom_errors import (
    ConfigError,
    MissingPropertyError,
    OutOfBoundsError,
)
from cassy.auxiliary.types import PathLike

MATH_SUBSTITUTIONS = {"EXP": np.exp, "SQRT": np.sqrt, "^": "**"}

# keys accepted by all property formats that do not compute their own bounds
COMMON_KEYS = frozenset({"type", "lower_bound", "upper_bound", "scale_result"})


def _check_keys(data: dict, allowed: AbstractSet[str], where: str) -> None:
    """Raise a ConfigError if data contains keys that would be silently ignored,
    typically a wrong indentation in the YAML file (e.g. scale_result under values).
    """
    unknown = set(data) - allowed
    if unknown:
        raise ConfigError(
            f"Unknown key(s) {sorted(unknown)} in {where}. Allowed keys: "
            f"{sorted(allowed)}. Check the indentation of the material file."
        )


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader raising a ConfigError on duplicate keys, which PyYAML would
    otherwise silently overwrite with the last one."""

    def construct_mapping(self, node, deep=False):
        keys = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                mark = key_node.start_mark
                raise ConfigError(
                    f"Duplicate key '{key}' in {mark.name}, line {mark.line + 1}. "
                    "Check the indentation of the material file."
                )
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


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
    # keys of the property data dictionary, any other key raises a ConfigError
    ALLOWED_KEYS: frozenset[str] = COMMON_KEYS

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
        _check_keys(
            data, self.ALLOWED_KEYS, f"property '{name}' of material {material_name}"
        )
        self.type = PropertyType(data["type"])

        self.lower_bound = data.get("lower_bound", None)
        self.upper_bound = data.get("upper_bound", None)
        self.scale_result = float(data.get("scale_result", 1.0))  # Default scale is 1.0

        # particular flags used in fatigue. Defined here for linter
        self.mean_stress = None
        self.ftype = None
        self.name = name
        self.material_name = material_name

    def __call__(self, *args) -> float | np.ndarray:
        """
        Compute the property value and bounds.

        Array inputs broadcast; invalid entries are NaN. Scalar inputs retain
        their original return types and raise OutOfBoundsError outside the bounds.
        """
        # For legacy purposes, allow to provide all input in a tuple
        if len(args) == 1 and isinstance(args[0], tuple):
            args = args[0]
        if any(np.ndim(arg) > 0 for arg in args):
            arrays = np.broadcast_arrays(*(arg for arg in args if arg is not None))
            array_iter = iter(arrays)
            broadcast_args = tuple(
                next(array_iter) if arg is not None else None for arg in args
            )
            valid = self._array_in_bounds(*broadcast_args)
            result = np.full(valid.shape, np.nan)
            result[valid] = self._function_to_call(
                *(arg[valid] if arg is not None else None for arg in broadcast_args)
            ) * self.scale_result
            if np.any(~valid):
                logging.warning(
                    "Invalid array arguments for property %s of material %s: %d entries",
                    self.name, self.material_name, np.count_nonzero(~valid),
                )
            return result
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
        with trace.nested() as outermost:
            result = self._function_to_call(*args) * self.scale_result
        if outermost:
            trace.record_property(self.name, result, args, self.material_name)
        return result

    def _array_in_bounds(self, *args) -> np.ndarray:
        valid = np.ones(next(arg.shape for arg in args if arg is not None), dtype=bool)
        for i, arg in enumerate(args):
            if arg is None:
                continue
            valid &= np.isfinite(arg)
            if self.lower_bound is not None and self.lower_bound[i] is not None:
                valid &= arg >= self.lower_bound[i]
            if self.upper_bound is not None and self.upper_bound[i] is not None:
                valid &= arg <= self.upper_bound[i]
        return valid

    @abstractmethod
    def _function_to_call(self, *args) -> float | np.ndarray:
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
        raise MissingPropertyError(
            f"Property {self.name} not implemented for {self.material_name}"
        )


class Table1DProperty(Property):
    # bounds are computed from the table
    ALLOWED_KEYS = frozenset({"type", "scale_result", "values"})

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
        _check_keys(
            data["values"],
            {"x", "y"},
            f"values of property '{name}' of {material_name}",
        )
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
    # bounds are computed from the table
    ALLOWED_KEYS = frozenset({"type", "scale_result", "scale_x", "scale_y", "values"})

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
        _check_keys(
            data["values"],
            {"x", "y", "vals"},
            f"values of property '{name}' of {material_name}",
        )
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
    # bounds are computed from the table
    ALLOWED_KEYS = frozenset(
        {
            "type",
            "scale_result",
            "scale_x",
            "scale_y",
            "scale_z",
            "columns",
            "values",
        }
    )

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
    # bounds are computed from the table
    ALLOWED_KEYS = frozenset(
        {
            "type",
            "scale_result",
            "scale_x",
            "scale_y",
            "ftype",
            "mean_stress",
            "rccmrx_inconel",
            "values",
            "tables",
        }
    )

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

        # Each table is stored as (T, N_cycles, y), y having one row per N and one
        # column per T. See _interpolate for the interpolation scheme.
        self.tables = {}
        for mean_stress, table in tables.items():
            _check_keys(
                table,
                {"T", "N_cycles", "y"},
                f"table {mean_stress} of property '{name}' of {material_name}",
            )
            T = np.array(table["T"], dtype=float)
            N_cycles = np.array(table["N_cycles"], dtype=float)
            matrix = np.array(table["y"], dtype=float)
            self.tables[mean_stress] = (T, N_cycles, matrix)

        # Update the bounds. For the number of cycles extrapolation needs to be in the
        # table values.
        self.lower_bound = [min(T), None]
        self.upper_bound = [max(T), None]
        if self.mean_stress:
            # do not put limits for mean stress
            self.lower_bound.append(None)
            self.upper_bound.append(None)

    def _function_to_call(
        self, x: float | np.ndarray, y: float | np.ndarray,
        s_mean: float | np.ndarray | None = None,
    ) -> float | np.ndarray:
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
        if s_mean is not None and np.ndim(s_mean) > 0:
            x, y, s_mean = np.broadcast_arrays(x, y, s_mean)
            result = np.full(x.shape, np.nan)
            remaining = np.ones(x.shape, dtype=bool)
            for mean_stress, table in self.tables.items():
                selected = remaining & (s_mean <= float(mean_stress))
                if np.any(selected):
                    result[selected] = self._interpolate(table, x[selected], y[selected])
                remaining &= ~selected
            if np.any(remaining):
                logging.warning(
                    "Mean stress is above the maximum fatigue table for %s: "
                    "using the last table for %d entries",
                    self.material_name, np.count_nonzero(remaining),
                )
                result[remaining] = self._interpolate(table, x[remaining], y[remaining])
            return result
        if s_mean is None:
            # Use the All table
            table = self.tables["All"]
        else:
            table = None
            for mean_stress, table_s in self.tables.items():
                if s_mean <= float(mean_stress):
                    table = table_s
                    break
            if table is None:
                # insteading of raising an error, we can use the last table
                # with a warning
                logging.warning(
                    f"Mean stress {s_mean} is above the maximum defined in the "
                    f"fatigue table. Using the last table."
                )
                trace.record(
                    "mean stress",
                    f"{s_mean} above the fatigue table maximum: last curve used",
                    kind="warning",
                    source=self.material_name,
                )
                table = table_s

        return self._interpolate(table, x, y)

    def _interpolate(
        self, table: tuple[np.ndarray, np.ndarray, np.ndarray],
        x: float | np.ndarray, y: float | np.ndarray,
    ) -> float | np.ndarray:
        """Interpolate the number of cycles. The curve at temperature x is obtained
        interpolating linearly in T the strain/stress of each N row, then N is
        interpolated log-log on that curve. Below the last row the allowable is the
        last N of the table, above the first row an OutOfBoundsError is raised."""
        T, N_cycles, matrix = table
        if np.ndim(x) > 0 or np.ndim(y) > 0:
            x, y = np.broadcast_arrays(x, y)
            T_val = x.ravel() * self.scale_x
            y_val = y.ravel() * self.scale_y
            if len(T) == 1:
                curves = np.broadcast_to(matrix[:, 0], (T_val.size, len(N_cycles)))
            else:
                j = np.clip(np.searchsorted(T, T_val), 1, len(T) - 1)
                w = (T_val - T[j - 1]) / (T[j] - T[j - 1])
                curves = matrix[:, j - 1].T * (1 - w[:, None]) + matrix[:, j].T * w[:, None]
            n_above = np.sum(curves >= y_val[:, None], axis=1)
            result = np.full(y_val.shape, np.nan)
            result[n_above == len(N_cycles)] = N_cycles[-1]
            bracket = (n_above > 0) & (n_above < len(N_cycles))
            rows = np.flatnonzero(bracket)
            i = n_above[bracket] - 1
            y1, y2 = curves[rows, i], curves[rows, i + 1]
            N1, N2 = N_cycles[i], N_cycles[i + 1]
            exact = y_val[bracket] == y1
            values = N1.copy()
            interpolate = ~exact
            values[interpolate] = 10 ** (
                np.log10(N1[interpolate])
                + np.log10(y_val[bracket][interpolate] / y1[interpolate])
                * np.log10(N2[interpolate] / N1[interpolate])
                / np.log10(y2[interpolate] / y1[interpolate])
            )
            result[bracket] = values
            if np.any(n_above == 0):
                logging.warning(
                    "Array entries above the fatigue curve for %s: %d entries",
                    self.material_name, np.count_nonzero(n_above == 0),
                )
            return result.reshape(x.shape)
        T_val = x * self.scale_x
        y_val = y * self.scale_y
        if len(T) == 1:
            curve = matrix[:, 0]
        else:
            j = min(max(int(np.searchsorted(T, T_val)), 1), len(T) - 1)
            w = (T_val - T[j - 1]) / (T[j] - T[j - 1])
            curve = matrix[:, j - 1] * (1 - w) + matrix[:, j] * w

        # The curve is non-increasing with N: the bracket starts at the last row
        # with curve >= y_val, which also picks the largest N on flat segments.
        n_above = int(np.sum(curve >= y_val))
        if n_above == 0:
            raise OutOfBoundsError(
                f"{self.ftype.capitalize()} {y} at T={x} is above the fatigue curve."
                f" Property: {self.name}, Material: {self.material_name}"
            )
        if n_above == len(curve):
            return float(N_cycles[-1])
        i = n_above - 1
        y1, y2 = curve[i], curve[i + 1]
        N1, N2 = N_cycles[i], N_cycles[i + 1]
        if y_val == y1:
            # on a table row, avoid the round-off of the log interpolation
            return float(N1)
        log_N = np.log10(N1) + np.log10(y_val / y1) * np.log10(N2 / N1) / np.log10(
            y2 / y1
        )
        return float(10**log_N)


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
        self, x: float | np.ndarray, y: float | np.ndarray,
        Sm: float | np.ndarray, Smb: float | np.ndarray, ds_tot: float | np.ndarray,
    ) -> float | np.ndarray:
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
        if any(np.ndim(arg) > 0 for arg in (x, y, Sm, Smb, ds_tot)):
            x, y, Sm, Smb, ds_tot = np.broadcast_arrays(x, y, Sm, Smb, ds_tot)
            curve1 = (ds_tot < 2.7 * Sm) | (ds_tot < 2.7 * Smb)
            curve2 = np.logical_not(curve1) & (
                ((ds_tot < 3 * Sm) & (ds_tot >= 2.7 * Sm))
                | ((ds_tot < 3 * Smb) & (ds_tot >= 2.7 * Smb))
            )
            result = np.full(x.shape, np.nan)
            for curve, selected in (("Curve1", curve1), ("Curve2", curve2)):
                if np.any(selected):
                    result[selected] = self._interpolate(
                        self.tables[curve], x[selected], y[selected],
                    )
            if np.any(~(curve1 | curve2)):
                logging.warning(
                    "Total stress range above Inconel fatigue limits for %s: %d entries",
                    self.material_name, np.count_nonzero(~(curve1 | curve2)),
                )
            return result
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
        return self._interpolate(self.tables[curve], x, y)


class PolynomialProperty(Property):
    ALLOWED_KEYS = COMMON_KEYS | {"coefficients"}

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
    ALLOWED_KEYS = COMMON_KEYS | {"value"}

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
    ALLOWED_KEYS = COMMON_KEYS | {"equation", "args"}

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
    ALLOWED_KEYS = COMMON_KEYS | {"ranges"}

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
        self.ranges = []
        for i, prop in enumerate(data["ranges"]):
            range_name = f"{property_name} (range {i + 1})"
            self.ranges.append(
                PropertyFactory.create_property(
                    {range_name: prop}, range_name, material_name
                )
            )

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

    def _array_in_bounds(self, *args) -> np.ndarray:
        valid = super()._array_in_bounds(*args)
        in_range = np.zeros(valid.shape, dtype=bool)
        for prop in self.ranges:
            in_range |= prop._array_in_bounds(*args)
        return valid & in_range

    def _function_to_call(self, *args) -> float | np.ndarray:
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
        if any(np.ndim(arg) > 0 for arg in args):
            args = np.broadcast_arrays(*args)
            result = np.full(args[0].shape, np.nan)
            remaining = np.ones(result.shape, dtype=bool)
            for prop in self.ranges:
                selected = remaining & prop._array_in_bounds(*args)
                if np.any(selected):
                    values = prop(*(arg[selected] for arg in args))
                    result[selected] = values
                    remaining[selected] = False
            if np.any(remaining):
                logging.warning(
                    "Array arguments outside all ranges for %s of %s: %d entries",
                    self.name, self.material_name, np.count_nonzero(remaining),
                )
            return result
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
            config = yaml.load(file, Loader=_UniqueKeyLoader)

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

    @trace.traced_method
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

    @trace.traced_method
    def cyclic_stress_strain(
        self, T: float | np.ndarray, ds: float | np.ndarray,
        dpa: float | np.ndarray = 0,
    ) -> float | np.ndarray:
        """returns the plastic cyclic de_strain given a d_sigma (Pa) and T"""
        E = self.E(T, dpa) * 1e-6  # convert from Pa to MPa
        K = self.K(T)
        m = self.m(T)
        ds = ds / 1e6  # convert from Pa to MPa

        de_tot = 100 * ds * (2 * (1 + self.nu()) / (3 * E)) + (ds / K) ** (1 / m)

        return de_tot / 100

    @trace.traced_method
    def get_Keff(self, T: float, dpa: float, K: float) -> float:
        """Compute the effective K value for the material at given temperature and dpa."""
        # To check if it is the same for all materials
        try:
            k_rect = self.Keff_rec(T, dpa)
        except NotImplementedError:
            # If data is not available assume
            k_rect = 1.5
        return 1 + 2 * (K - 1) * (k_rect - 1)

    @trace.traced_method
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

    @trace.traced_method
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
