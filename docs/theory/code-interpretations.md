# Code interpretations

This section lists some key design codes interpretations that guided cassy assessment implementations.

## Common to all codes

### Stress intensity
From path linearization we obtain 6 stress components: Sx, Sy, Sz, Sxy, Sxz, Syz.
Whenever in the code a stress intensity needs to be computed, after all tensors that compose the
stress have been combined, the instensity is computed using the Von Mises stress. In case inertial loads are present (i.e. loads without sign) the upper limit formulation of the Von Mises stress is used.

### The local primary membrane stress intensity P_L

P_L, the local primary membrane stress, in CASSY is always interpreted as the Pm, membrane stress.

## RCC-MRx
TODO

## SDC-IC 

### Effective bending shape factor
In rule IC 3121.1.1.2a to compute Keff one should postulate a value of K which, in principle, is a function of the shape. K=1.5 is always assumed in CASSY and Keff is computed accordingly.

### Distinction between normal and fillet paths

In the classification between primary and secondary stresses, SDC-IC makes some distinctions on how to classify different stresses depending on their source and the geometri on which the path is defined. In particular, it specifies that if a path is defined in a fillet, pressure induced bending stresses should be considered secondary and not primary. Hereafter is an exract of the relevant SDC-IC section:

![image](/images/interpretations/justification_fillet.PNG)

### Plasma disruption derived stresses
TODO

### Efficiency index in ratcheting
For Efficiency index diagram (IC 3131.1.1) the code foresees two routes depending on if secondary membrane stresses are present. Since thermal stresses will always be present in in-vessel components, this is the only route implemented in CASSY.

At this point the rules split again in case of "overstress of short duration". Depending if any of the loads have been flagged as short duration, one or the other path will be followed.

### Goodman's correction in bolts

For bolts material that provide stress-based curves instead of strain-based curves the application of the code is tricky. The reasons are summarized in the slides that can be found in [ITER IDM](https://user.iter.org/default.aspx?uid=4ZUD2K).

When materials fatigue curves are provided with a dependence from the mean stress, it is assumed that no further mean stress correction is needed. Hence, Goodman's correction will not be applied.