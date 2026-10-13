import math
from abc import ABC
from dataclasses import dataclass

from cassy.general.material import Material


@dataclass
class BoltLikeGeom(ABC):
    """
    stores data related to a bolt-like geometry. All units are in mm.

    Parameters
    ----------
    name : str
        identifier for the point of application.
    material : material.Material
        material of the bolt
    p : float
        thread pitch.
    d : float
        maximum nominal diameter.
    dn : float
        core diameter (minor).
    d1 : float
        diameter of smooth shank.
    df : float
        pitch diameter (mean).
    D : float
        minor diameter of tapping.
    Dp : float
        diameter of drilling circle.
    Dm : float
        mean diameter under head
    Le : float
        insertion length.
    d_vh : float
        diameter of the venting hole.
    f : float, optional
        friction coefficient between engaged threads.
    f_prime : float, optional
        friction coefficient under head.
    """

    name: str
    material: Material

    p: float = 0
    d: float = 0
    Le: float = 0
    d_vh: float = 0
    f: float = 0.15

    # either computed or provided but guaranteed to be not None after __post_init__
    dn: float = None
    df: float = None
    D: float = None

    def __post_init__(self):
        # compute if not provided
        if not self.dn:
            self.dn = self.d - 1.22687 * self.p
        if not self.df:
            self.df = self.d - 0.64952 * self.p
        if not self.D:
            self.D = self.d - 1.08253 * self.p

        # --- Additional geometrical feature ---
        # length for shear calculation
        self.Le_shear = min(0.8 * self.d, self.Le)
        # Minimum cross-sectional area at the root of thread
        self.An = self.dn**2 * math.pi / 4 - self.d_vh**2 * math.pi / 4
        # Section Module
        self.Z = (self.dn**4 - self.d_vh**4) * math.pi / 32 / self.dn


@dataclass
class InsertGeom(BoltLikeGeom):
    """
    stores data related to an insert. All units are in mm.

    Parameters
    ----------
    name : str
        identifier for the point of application.
    material : material.Material
        material of the bolt
    p : float
        thread pitch.
    d : float
        maximum nominal diameter.
    dn : float
        core diameter (minor).
    d1 : float
        diameter of smooth shank.
    df : float
        pitch diameter (mean).
    D : float
        minor diameter of tapping.
    Dp : float
        diameter of drilling circle.
    Dm : float
        mean diameter under head
    Le : float
        insertion length.
    f : float, optional
        friction coefficient between engaged threads.
    f_prime : float, optional
        friction coefficient under head.
    """

    # no additional data needed for an insert
    pass


@dataclass
class BoltGeom(BoltLikeGeom):
    """
    stores data related to an insert. All units are in mm.

    Parameters
    ----------
    name : str
        identifier for the point of application.
    material : material.Material
        material of the bolt
    p : float
        thread pitch.
    d : float
        maximum nominal diameter.
    dn : float
        core diameter (minor).
    d1 : float
        diameter of smooth shank.
    df : float
        pitch diameter (mean).
    D : float
        minor diameter of tapping.
    Dp : float
        diameter of drilling circle.
    Dm : float
        mean diameter under head
    Le : float
        insertion length.
    H : float
        height of head.
    a : float
        diameter of head.
    B : float
        inside diameter of washer.
    C : float
        washer thickness
    KF : float, optional
        fatigue stress reduction factor (IC 2753) for the application
        of the Neuber's rule. The default value is 4.
    f : float, optional
        friction coefficient between engaged threads.
    f_prime : float, optional
        friction coefficient under head.
    """

    f_prime: float = 0.15
    B: float = 0
    C: float = 0
    KF: float = 4

    # guaranteed to be not None after __post_init__
    d1: float = None
    H: float = None
    a: float = None
    Dm: float = None
    Dp: float = None

    def __post_init__(self):
        super().__post_init__()
        # --- Additional geometrical feature ---
        # diameter of head
        if not self.a:
            self.a = 1.5 * self.d
        if not self.H:
            self.H = 0.625 * self.d
        if not self.d1:
            self.d1 = self.d
        if not self.Dm:
            if self.B > 0:
                self.Dm = (self.B + self.a) / 2
            else:
                self.Dm = 0.8 * self.a
        if not self.Dp:
            self.Dp = self.d * 1.1
