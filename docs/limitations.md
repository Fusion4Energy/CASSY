This page lists all the known limitations of cassy.

# General disclaimer
cassy assessment can be considered valid only in the following hypothesis:

- only linear elastic analysis routes are implemented.
- creep/swelling can be neglected.

# Implemented design codes

## Bolts
Only the following design codes are implemented in cassy for bolts assessments:
- RCC-MRx
- SDC-IC
- EN 13445 (only for bolts fatigue)

These are also the name tags that can be used in the excel config files.

## Paths
Only the following design codes are implemented in cassy for paths assessments:
- RCC-MRx
- RCC-MR
- SDC-IC

These are also the name tags that can be used in the excel config files.

# Materials
## Material properties
Material properties should be always double checked, in particular the validity ranges that not always are taken into account by the code. It is responsability of the users to ensure that material properties are coherent with the design code used.

## Triaxiality factor
triaxility factor has been considered equal to 2 by default. This is a conservative assumption considering the related allowable stresses.

# Paths assessment
## Stress based fatigue curves
Stress based fatigue curves (i.e. sigma Vs n. of cycles) are not supported for paths assessments.

## Efficiency index rules in RCC-MRx
In RCC-MRx ratcheting efficieny index rules are commented out and should be double checked if are to be used.

## Significant irradiation in RCC-MRx
RCC-MRx rules for significant irradiation (RB 3251.21) are not yet implemented.

# Bolts assessments

## Fatigue $f_{t^*}$ in EN 13445
For the computation of the $f_{t^*}$ parameter the code requires a minimum temperature to be considered in the
fatigue cycle. This is a bit difficult to introduce into CASSY structure so, for the moment, $T_{min}=25 deg$ has been hardcoded. 