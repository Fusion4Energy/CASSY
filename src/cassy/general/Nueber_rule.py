# -*- coding: utf-8 -*-
"""
Created on Wed Apr  7 17:41:02 2021

@author: s.guidozzi
"""

import numpy as np
import pandas as pd

# import matplotlib.pyplot as plt
from shapely.geometry import LineString, Point


def compute_Nueber(df1, df2, T, s, E):
    if s == 0:
        return {"stress": 0, "Young": 0, "epsilon": 0}
    Ts = [20, 100, 200, 250, 300]
    result = intersect(Ts, df1, s, E)
    if result["epsilon"] > 1.5:
        Ts = [20, 100, 200]
        result = intersect(Ts, df2, s, E)

    return result


def intersect(Ts, df, s, E):
    epses = {}
    sdata = {}
    epses_new = []
    sdata_new = []
    stress_n = s * 1e-6  # MPa

    epses_n = (s / E) * 1e2  # %

    for T in Ts:
        epses[T] = df[str(T) + "strain"].dropna()
        sdata[T] = df[str(T) + "stress"].dropna()

    # get the upper and lower temperature
    for i in range(len(Ts)):
        if T >= Ts[i] and T <= Ts[i + 1]:
            break

    Tinf = Ts[i]

    try:
        Tsup = Ts[i + 1]
        # interpolation of monotonic curve with the actual temperature
        for eps1, eps2 in zip(epses[Tinf], epses[Tsup]):
            if eps1 == "limit" or eps2 == "limit":
                break
            eps_new = (T - Tinf) / (Tsup - Tinf) * eps1 - (T - Tsup) / (
                Tsup - Tinf
            ) * eps2
            epses_new.append(eps_new)

        for s1, s2 in zip(sdata[Tinf], sdata[Tsup]):
            if s1 == "limit" or s2 == "limit":
                break
            s_new = (T - Tinf) / (Tsup - Tinf) * s1 - (T - Tsup) / (Tsup - Tinf) * s2
            sdata_new.append(s_new)

    except IndexError:  # if T > Tmax the last curve is considered
        epses_new = df[str(Ts[i]) + "strain"].dropna()
        sdata_new = df[str(Ts[i]) + "strain"].dropna()

    # hyperbola generation

    pitch = stress_n / 30
    reduction = 1
    flag = True

    while flag is True:
        reduction = reduction * 0.1

        (hyp_e, hyp_s) = hyperbola_gen(epses_n, stress_n, pitch, reduction)

        strain_monotonic = pd.Series(epses_new)
        stresses_monotonic = pd.Series(sdata_new)

        strain_nueber = pd.Series(hyp_e)
        stresses_nueber = pd.Series(hyp_s)

        # plt.plot(strain_monotonic, stresses_monotonic)
        # plt.plot(strain_nueber, stresses_nueber)

        line_1 = LineString(np.column_stack((strain_nueber, stresses_nueber)))

        line_2 = LineString(np.column_stack((strain_monotonic, stresses_monotonic)))

        intersection = line_1.intersection(line_2)  # intersection poit

        try:
            x, y = intersection.xy
            # print(x[0], y[0])
            flag = False
        except AttributeError:  # no intersection, regenerate Hyperbola
            flag = True

    # compute angular coefficient:
    # it takes the nearest value to the intersection point
    d = []
    for eps, s in zip(epses_new, sdata_new):
        d.append(Point(eps, s).distance(Point(x[0], y[0])))

    d1 = min(d)
    i = d.index(d1)
    # point = Point(epses_new[i], sdata_new[i])
    Eplastic = (sdata_new[i] - y[0]) / (epses_new[i] - x[0])

    # plt.plot(x[0], y[0], 'ro')
    # plt.plot(epses_new[i], sdata_new[i], 'bo')

    s_nueber = y[0]
    if s_nueber > stress_n:
        s_nueber = stress_n  # the nominal point is at the right of the curve
    E_nueber = Eplastic

    # values returned in MPa

    return {"stress": s_nueber * 1e6, "Young": E_nueber * 1e8, "epsilon": x[0]}


def hyperbola_gen(x0, y0, pitch, reduction):
    x = []
    y = []
    k = x0 * y0
    y1 = y0 * 1.5  # starting value of stress
    # x1 = k/y1  # starting value of strain
    while y1 > y0 * reduction:
        x.append(k / y1)
        y.append(y1)
        y1 = y1 - pitch
    return (x, y)
