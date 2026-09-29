# FEM theory

This section collects all important bits of FEM theory that are used in CASSY.

## Upper Limit Von Mises

### Why an upper formulation is needed?

When recombining single loads contribution in an elastic analysis the Von Mises is usually the equivalent stress chosen for the job. This works fine for "volumetric" loads that have a sign but it breaks down when dealing with inertial loads, whose sign is arbitrary since:

- these values do not occur, in general, at the same time,
- the sign of the components is lost in the combination (e.g. SRSS, CQC).

For these reasons the computed VM equivalent stresses lack physical significance. In addition, their combination with the effects of other loading conditions, e.g. the deadweight, is problematic.
Specifically, the computation of the VM equivalent stress on the basis of the contributions of a single normal mode to the extreme/design stress components is physically sound, since these contributions occur at the same time and correctly retain their sign.

### The upper limit formulation

The standard formulation of the VM equivalent stress is the following:

$$
\sigma_{eq}=\sqrt{(\sigma_x^2+\sigma_y^2+\sigma_z^2+3\tau_{xy}^2+3\tau_{xz}^2+3\tau_{yz}^2-(\sigma_x \sigma_y+\sigma_x \sigma_z+\sigma_y \sigma_z ) )}
$$

When superposition of inertial (i) and static effects (s) is required, the UL formulation is obtained by computing the terms of the standard formulation using the following equations:

$$
	\sigma_j=\sigma_j^{(i)}+\sigma_j^{(s)}
$$

$$
	-(\sigma_j \sigma_k )^{UL}=|\sigma_j^{(i)} \sigma_k^{(i)} |+|\sigma_j^{(i)} \sigma_k^{(s)} |+|\sigma_j^{(s)} \sigma_k^{(i)} |-\sigma_j^{(s)} \sigma_k^{(s)}
$$

$$
(\sigma_j^2 )^{UL}=(\sigma_j^{(i)}+|\sigma_k^{(s)} |)^2
$$

$$
(\tau_{jk}^2 )^{UL}=(\tau_{jk}^{(i)}+|\sigma_{jk}^{(s)} |)^2.
$$


The Von-Mises equivalent stress is the basis of the maximum distortion energy criterion to predict yielding of materials under complex loading from the results of uniaxial tensile tests. 
The Upper-Limit Von-Mises parameter lose this physical meaning and represents an indicator of how severe the stress state at different location of a complex structure. 
Note that the term $(\sigma_j^{(s)} \sigma_k^{(s)})$ has the sign defined by the actual signs of the static effects $\sigma_j^{(s)}$ and $\sigma_k^{(s)}$. All other components need to be sum in absolute value as the inertial part has no sign.

<script id="MathJax-script" src="https://unpkg.com/mathjax@3/es5/tex-mml-chtml.js"></script>
<script>
  window.MathJax = {
    tex: {
      inlineMath: [["\\(", "\\)"]],
      displayMath: [["\\[", "\\]"]],
      processEscapes: true,
      processEnvironments: true
    },
    options: {
      ignoreHtmlClass: ".*|",
      processHtmlClass: "arithmatex"
    }
  };

  document$.subscribe(() => {
    MathJax.startup.output.clearCache()
    MathJax.typesetClear()
    MathJax.texReset()
    MathJax.typesetPromise()
  })
</script>