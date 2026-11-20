# Yarn sliding, material coordinates, and conformability in yarn-level cloth simulation

**Research report for the Brambleloop Visual Department**
Prepared: 2026-09-24 (UTC). Literature/implementation research only. No repository code was written or modified.

Every claim below is labelled **[SOURCED]** (with a URL and, where I read the full text, a quotation or close paraphrase),
**[INFERRED]** (my reasoning from a sourced fact — treat as a hypothesis, not a finding), or
**[UNKNOWN]** (I looked and did not find it; do not fill this gap with reasoning).

---

## 0. Sources actually read

Full text obtained and read (PDF extracted locally):

| # | Work | URL |
|---|------|-----|
| S1 | Kaldor, James, Marschner. *Simulating Knitted Cloth at the Yarn Level*. SIGGRAPH 2008 | https://www.cs.cornell.edu/projects/YarnCloth/sg08_knityarns.pdf |
| S2 | Kaldor, James, Marschner. *Efficient Yarn-based Cloth with Adaptive Contact Linearization*. SIGGRAPH 2010 | https://www.cs.cornell.edu/projects/YarnCloth/sg10_acl.pdf |
| S3 | Yuksel, Kaldor, James, Marschner. *Stitch Meshes for Modeling Knitted Clothing with Yarn-level Detail*. SIGGRAPH 2012 | https://www.cemyuksel.com/research/stitchmeshes/stitchmeshes.pdf |
| S4 | Sueda, Jones, Levin, Pai. *Large-Scale Dynamic Simulation of Highly Constrained Strands*. SIGGRAPH 2011 | https://www.cs.ubc.ca/sites/default/files/research/papers/2011/05/strands2preprint.pdf |
| S5 | Weidner, Piddington, Levin, Sueda. *Eulerian-on-Lagrangian Cloth Simulation*. SIGGRAPH 2018 | https://people.engr.tamu.edu/sueda/projects/eol-cloth/WPLS2018.pdf |
| S6 | Sánchez-Banderas, Rodríguez, Barreiro, Otaduy. *Robust Eulerian-on-Lagrangian Rods*. SIGGRAPH 2020 | https://burjcdigital.urjc.es/server/api/core/bitstreams/89e6b9cc-16bf-4ec7-9094-23c23318c5fd/content (author version; DOI 10.1145/3386569.3392489) |
| S7 | Sperl, Narain, Wojtan. *Homogenized Yarn-Level Cloth*. SIGGRAPH 2020 | https://pub.ista.ac.at/group_wojtan/projects/2020_Sperl_HYLC/2020_HYLC_paper_lowres.pdf |
| S8 | Sperl et al. *Estimation of Yarn-Level Simulation Models for Production Fabrics*. SIGGRAPH 2022 | https://pub.ista.ac.at/group_wojtan/projects/2022_Sperl_Fabric_Estimation/sperl2022eylsmpf.pdf |
| S9 | *Fine-grained Differentiable Physics: A Yarn-level Model for Fabrics*. ICLR 2022 (arXiv 2202.00504) | https://arxiv.org/pdf/2202.00504 |
| S10 | Poincloux, Adda-Bedia, Lechenault. *Geometry and Elasticity of a Knitted Fabric*. Phys. Rev. X 8, 021075 (2018) (arXiv 1801.08355) | https://arxiv.org/pdf/1801.08355 |
| S11 | Poincloux et al. *Crackling Dynamics in the Mechanical Response of Knitted Fabrics*. (arXiv 1803.00815) | https://arxiv.org/pdf/1803.00815 |
| S12 | Miguel, Tamstorf, Bradley, Schvartzman, Thomaszewski, Bickel, Matusik, Marschner, Otaduy. *Modeling and Estimation of Internal Friction in Cloth*. SIGGRAPH Asia 2013 | https://studios.disneyresearch.com/wp-content/uploads/2019/03/Modeling-and-Estimation-of-Internal-Friction-in-Cloth.pdf |
| S13 | Daviet. *Simple and Scalable Frictional Contacts for Thin Nodal Objects*. SIGGRAPH 2020 | https://gdaviet.fr/files/hardContacts.pdf |
| S14 | Li, Kaufman, Jiang. *Codimensional Incremental Potential Contact (C-IPC)*. SIGGRAPH 2021 (arXiv 2012.04457) | https://arxiv.org/pdf/2012.04457 |
| S15 | Luo, Umetani. *CT2Yarn: Yarn-Level Reconstruction of Crochet from Computed Tomography*. Pacific Graphics 2026 (arXiv 2609.06950) | https://arxiv.org/pdf/2609.06950 |
| S16 | Dresselhaus et al. *Textiles: from twisted yarn to topology and mechanics* (review, arXiv 2604.09005) | https://arxiv.org/pdf/2604.09005 |
| S17 | *Volumetric Homogenization for Knitwear Simulation* (arXiv 2405.12484) | https://arxiv.org/pdf/2405.12484 |

Method details for the Cirio line of work were obtained from the corresponding granted patents, which are public,
textual, and written by the same authors/affiliation (Otaduy / SEDDI / Desilico) as the papers:

| # | Work | URL |
|---|------|-----|
| P1 | US 10,810,333 B2 — *…simulating the behavior of a knitted fabric at yarn level* (corresponds to Cirio et al. 2015 SCA / 2017 TVCG) | https://patents.google.com/patent/US10810333B2/en |
| P2 | US 11,250,187 B2 — *…simulating the behavior of a woven fabric at yarn level* (corresponds to Cirio et al. 2014 TOG) | https://patents.google.com/patent/US11250187B2/en |

Primary papers I could **not** obtain in full text (all attempts documented; ACM DL returns 403 from this
environment, mslab.es/gmrv.es sit behind a bot-verification wall, textiles.cs.cmu.edu currently 503s and
presents an unverifiable certificate chain):

- Cirio, López-Moreno, Miraut, Otaduy. *Yarn-level simulation of woven cloth*. TOG 33(6), 2014. DOI 10.1145/2661229.2661279
- Cirio, López-Moreno, Otaduy. *Efficient simulation of knitted cloth using persistent contacts*. SCA 2015
- Cirio, López-Moreno, Otaduy. *Yarn-Level Cloth Simulation with Sliding Persistent Contacts*. TVCG 23(2), 2017. DOI 10.1109/TVCG.2016.2592908
- **Guo, Lin, Narayanan, McCann. *Representing Crochet with Stitch Meshes*. SCF 2020. DOI 10.1145/3424630.3425409** — I have only the abstract (via Semantic Scholar / ACM landing page). Unpaywall reports the only open copy is the ACM PDF, which this environment cannot fetch. **This is a real gap in the report and I have not papered over it.**
- Leaf, Wu, Schweickart, James, Marschner. *Interactive design of periodic yarn-level cloth patterns*. SIGGRAPH Asia 2018
- Wu et al. *Knittable Stitch Meshes*. TOG 2019

---

## 1. Bottom line, stated plainly

**The established yarn-level methods split into exactly two camps, and BOTH of them allow the yarn to move
through the loops. Neither camp obtains conformability from bending alone. Your solver is in neither camp.**

- **Camp A — Kaldor / stitch-mesh lineage (fully Lagrangian, explicit contact).** Material coordinates are
  fixed to spline control points, but **nothing pins a material point to a stitch.** Loops are held together
  *only* by detected penalty contact between arbitrary yarn-segment pairs, with no topological pairing assumed.
  The yarn is therefore free to translate bodily through a loop, and the yarn length lying between two
  neighbouring stitches is an emergent quantity, not a constraint. **[SOURCED, S1]**
- **Camp B — Cirio / Sueda / Otaduy lineage (Eulerian-on-Lagrangian, persistent contact).** The contact between
  two loops is made an explicit, permanent discretisation node, and that node is given **extra scalar degrees of
  freedom that are arc-length (material) coordinates**. The yarn slides *through* the node by changing those
  coordinates. This is literally called "yarn sliding". **[SOURCED, S4, S6, P1, P2, S9]**

Your solver welds material coordinates to loops (Camp B's topology, Camp A's kinematics minus the freedom),
which is a third option the literature does not use and, per S6's own analysis, is the configuration in which
bending is the only compliance available. **[INFERRED from S1, S6, P1]**

Independently, the **experimental physics** literature says the same thing about real knitted fabric:
"*the stitches can undergo large deformations due to their curved nature and the fact that the yarn can slide
from one stitch into the neighbouring ones. Those properties manifest also in the outstanding drapability of
the resultant knitted fabrics*" — Poincloux et al., PRX 2018. **[SOURCED, S10]**
And: "*the yarn is not attached to these topological units and is allowed to slide from one stitch to another.*" **[SOURCED, S10]**

So: **yes, yarn sliding is the established mechanism, it is physically measured, and it is what your solver is
missing.** The rest of this report is about *how* the literature represents it without breaking topology,
length or gauge.

---

## 2. Q1 — How do yarn-level cloth simulations represent yarn sliding through loops?

### FOUND — two distinct, well-documented representations

**(a) Implicitly, by not constraining it at all (Kaldor lineage). [SOURCED, S1]**

Kaldor et al. 2008 represent each yarn as a cubic B-spline with control points `q`, a **hard length constraint
per spline segment**:

> `C_len_i = 1 − (1/ℓ_i) ∫₀¹ ‖y'_i(s)‖ ds`

plus a soft energy `E_len_i` whose stated purpose is that the segment length constraint alone
"*does not necessarily keep the mass of the spline from sliding around inside the curve as the parameterization
speed changes*". So **material coordinates are fixed to control points by design**. **[SOURCED, S1 §4.1]**

But the loop-to-loop interaction is a **penalty contact energy between arbitrary segment pairs** `(i,j)` with
`|i−j| > 1`, and explicitly:

> "*Our collision evaluation makes no assumptions about cloth topology, allowing arbitrary collision regions
> typical of cloth-cloth contact*" **[SOURCED, S1 §2]**

with contacts found at runtime by a bounding-box hierarchy (3.7M contacting pairs per step on the leg-warmer
example). **[SOURCED, S1 §7]**

**Consequence: a "stitch" in Kaldor is not a material label; it is a moving set of contacts.** A control point
that starts outside a loop can end up inside it. The yarn length between two neighbouring stitches is free.
**[INFERRED from the two SOURCED facts above — the paper does not state this consequence in these words, but it
follows directly from "no assumptions about cloth topology" + runtime contact detection.]**

**(b) Explicitly, as an Eulerian degree of freedom at a persistent contact (Sueda / Cirio lineage). [SOURCED, S4, S6, P1, P2]**

Sueda et al. 2011 introduce the **Eulerian node (E-node)**:

> "*A Lagrangian node … represents the motion of material points… An Eulerian node, in contrast, represents
> motion of the strand through a point that is specified in spatial coordinates.*" **[SOURCED, S4 §2.2]**
> "*The material of the strand flows freely through all these E-nodes.*" **[SOURCED, S4 Fig. 2c]**

Cirio et al. specialise this to rod–rod contact. From the woven patent P2:

> "*a yarn crossing is described by its 3D position, x, and the parametric coordinates of the warp and weft
> material points at the yarn crossing*"; `q_i = (x_i, u_i, v_i)`; "*u is the undeformed length of the warp yarn
> between the crossing point and one end point of the yarn*"; "*The variation of u and v coordinates models,
> respectively, the sliding of warp and weft yarns.*" **[SOURCED, P2]**

From the **knit** patent P1 — this is the one that matters for you, because it is loops, not crossings:

> "*In a knit or purl stitch, a loop of a new row is passed through two loops of the previous row, embracing
> them and producing contacts between pair of loops.*" Each stitch is represented by **four contact nodes**,
> "*located at the end of two stitch contacts between pair of loops*".
> "*each contact node q = (x; u; v) constitutes a 5-DoF node, with x the 3D position of the node, and u and v
> the arc lengths of the two yarns in contact, which act as sliding coordinates*" and
> "*yarns are allowed to slide at contact nodes*". **[SOURCED, P1]**

S6 restates the same formulation independently and in the open literature:

> "*a rod node is placed at the contact point between the rod and an arbitrary object O, and its coordinates
> (u, x) store both Lagrangian (spatial) coordinates x and Eulerian (material) coordinates u. We use as Eulerian
> coordinate the undeformed arc length of the rod.*" and for rod–rod contact "*the two EoL nodes have
> coordinates (u, x) and (v, x)*" — i.e. **they share the spatial position and each keeps its own material
> coordinate**, a "*5-dimensional reduced-coordinate formulation*". **[SOURCED, S6 §3.1]**

S9 (open access, ICLR 2022) gives the same discretisation in full algebraic detail including the mass matrix
and its derivatives w.r.t. the Eulerian coordinates — this is the most readable open source for the actual
equations. **[SOURCED, S9 §3.1 and Appendix B]**

### NOT FOUND

- **[UNKNOWN]** No method I found represents sliding by moving the *discretisation vertices themselves along the
  yarn* (an r-adaptive reparameterisation of a normal Lagrangian rod) in a yarn-level cloth context. The closest
  is Wen & Bao, *Cosserat Rod with rh-Adaptive Discretization* (CGF 2020, http://www.cad.zju.edu.cn/home/hj/20/EOL_rod.pdf)
  which I found but did not read in full; I cannot tell you whether it has been applied to knits.
- **[UNKNOWN]** I found **no** crochet-specific yarn-level simulator in the literature at all. CT2Yarn (2026)
  says "*almost all computational work on yarn modeling has focused on synthetic structures*" and cites
  KJM08 / YKJM12 for "*physically based simulation*" of crochet-like structures — i.e. there is no dedicated
  crochet solver to copy. **[SOURCED, S15 §1]**

---

## 3. Q2 — How is yarn length / tension redistributed between neighbouring stitches?

### FOUND

**(a) In EoL models, redistribution IS the Eulerian coordinate, and it is length-exact by construction. [SOURCED, S6, P2, S9]**

The rest (undeformed) length of the segment between two adjacent sliding nodes is `Δu = u₁ − u₀`. Slide one node
and that segment gets shorter while its neighbour gets longer, **by exactly the same amount**. Total yarn length
is conserved by telescoping — it is an identity, not a constraint that has to be enforced. **[SOURCED: S6 Eq. 2
uses `Δu` as the material length of the segment; P2 states "Δu = u₁−u₀ is the rest length of the segment".]**

Stretch energy is then written as a function of the ratio of spatial to material length:

> `V_s = ½ k_s Δu ( ‖Δx‖/Δu − 1 )²` **[SOURCED, S6 Eq. 2, attributed to Cirio et al. 2014]**

**(b) Material conservation as an explicit penalty (knit case). [SOURCED, P1]**

P1 states the knit model adds a penalty `V = ½ k_l L (l/L − 1)²` on arc length between stitch contacts and
describes its purpose as preventing artificial creation/deletion of yarn material during sliding. **[SOURCED, P1]**

**(c) In real knitted fabric, the physically-correct constraint is GLOBAL, not per-stitch. [SOURCED, S10]**

This is the single most directly actionable result I found. Poincloux et al. build a first-principles model
"*based on the yarn bending energy, the conservation of its total length and the topological constraints on the
constitutive stitches*" **[SOURCED, S10 abstract]** and make the key modelling move explicit:

> "*Unlike a weaved fabric which can be modelled by a Chebychev net for which all the edges retain fixed lengths,
> the deformation of a knitted fabric allows for sliding of the yarn from one stitch into the adjacent ones.
> Nevertheless, the assumption that the yarn experiences only bending deformations imposes that its total length
> in the fabric is conserved.*" **[SOURCED, S10 §II.C]**

Operationally: per stitch cell with course size `c` and wale size `w`, the yarn consumed is `ℓ = c + δ w`
with `δ` a single scalar material constant of the stitch, and the constraint imposed is on the **average**:

> "*the constraint on yarn length amounts to require that the average effective length over all stitches
> ⟨ℓ⟩ = ⟨c⟩ + δ⟨w⟩ remains constant upon deformation*" **[SOURCED, S10 §II.C]**

For their stockinette sample they measure `δ = 0.86`, `ℓ* = 5.86 mm`, reference cell `c* = 3.93 mm`,
`w* = 2.08 mm`, and derive a geometric Poisson ratio `ν = δ w*/c* = 0.46`, remarking the hollow fabric
"*behaves like an incompressible elastic bulk material with a conserved effective area*". **[SOURCED, S10]**

**This is a fully specified, experimentally validated, one-parameter redistribution law**, and it is the cheapest
honest thing you could bolt onto an existing solver: replace *N* per-stitch length constraints with *one* global
length constraint plus a per-stitch allotment variable. **[INFERRED — the paper is for stockinette knit, not HDC
crochet; the value of `δ` for half double crochet is UNKNOWN and would have to be measured.]**

### NOT FOUND

- **[UNKNOWN]** The value of `δ` (or any equivalent yarn-consumption-per-stitch geometry parameter) for
  half double crochet, or for any crochet stitch. Poincloux's `δ` is measured for stockinette knit only.
- **[UNKNOWN]** No paper I found quantifies *how much* length actually migrates between stitches under gravity
  drape (as opposed to under in-plane tension, where S10 measures it directly).

---

## 4. Q3 — How are material coordinates represented when they move relative to discretisation vertices?

### FOUND — this is the Eulerian-on-Lagrangian (EoL) literature, and it is mature

**Origin and naming. [SOURCED, S4, S6]**
Sueda et al. 2011 introduced Eulerian nodes for strands; the term "Eulerian-on-Lagrangian" was coined by
Fan et al. 2013; S6 gives the lineage. **[SOURCED, S6 §2]**

**Generalized coordinates.** A node carries `(x, u)`: `x ∈ ℝ³` Lagrangian/spatial, `u ∈ ℝ` Eulerian/material
(undeformed arc length). For rod–rod contact the two nodes **share** `x` and keep separate `u, v`, giving a
5-DOF reduced coordinate. **[SOURCED, S6 §3.1; P1; P2; S9 §3.1]**

**Kinematic ambiguity and how it is resolved.** With both coordinate types the kinematics are ambiguous;
the ambiguity is removed by constraining the node's Lagrangian coordinates to sit on the contact
(`x − x_o = 0`, S6 Eq. 1), or, for rod–rod, by making the two nodes share `x`. **[SOURCED, S6 §3.1]**

**Mass is not invariant.** Because material flows through the node, the mass matrix depends on the Eulerian
coordinates and there are `Ṁ q̇` convective terms in the equations of motion. S9 writes them out:
`F = M q̈ = ∂T/∂q − ∂V/∂q − Ṁ q̇`, with `M₀,₁` an explicit function of `Δu` and `w = (x₁−x₀)/Δu`, and gives
`∂M₀,₁/∂u₀` etc. **[SOURCED, S9 Eq. 1, Eq. 9, Appendix B]**
Sueda et al. stress that mass must be **integrated along the strand, not lumped**, or the strand will not bend
correctly at the node ("*if the mass is integrated along the strand, then it takes on the expected catenary-like
shape*"). **[SOURCED, S4 Fig. 3 discussion]** — This is a concrete trap for anyone implementing EoL naively.

**In 2D (cloth) rather than 1D (rods).** Weidner et al. 2018 insert EOL vertices only where cloth touches a
sharp feature, keep the rest Lagrangian, and derive "*new equations of motion for EOL vertices, a
contact-conforming remesher, and a set of simple constraint assignment rules*". **[SOURCED, S5 abstract]**
Their motivation is *exactly* the failure mode you describe: without the extra DOF the cloth suffers
"*catastrophic locking, wherein the cloth, unable to slide over the edge, simply gets stuck*". **[SOURCED, S5 §1]**

### NOT FOUND

- **[UNKNOWN]** I did not find an EoL formulation where the material coordinate is 1-D along a yarn but the
  "contact" is a *loop* (a closed curve the yarn threads through) rather than a point. All the loop cases I found
  (P1) reduce the loop to **four point contacts per stitch**, not to a curve constraint.

---

## 5. Q4 — Contact with friction that still permits legitimate tangential slip

### FOUND — three families

**(a) Anchored-spring Coulomb friction on the Eulerian coordinate (the yarn-level standard). [SOURCED, P2, S6, P1]**

From P2, in full:

> "*The anchor position is initialized as the warp sliding u₀ at the crossing. Friction is modeled as a
> zero-rest-length viscoelastic spring between the anchor position and the actual warp coordinate.*"
> Stick: "*if the contact is in stick mode, and the force is defined by the spring*". Slip: "*if the limit is
> exceeded, the contact is in slip mode, and the force is given by the Coulomb limit*", and during slip
> "*the anchor position is maintained at a constant distance from the warp coordinate, such that the resulting
> spring force equals the Coulomb limit.*" **[SOURCED, P2]**

The Coulomb limit needs a normal force. For knits, P1 says:

> "*inter-yarn normal compression for knitted cloth is estimated by assuming static equilibrium of stretch,
> bending, and stitch wrapping forces*" **[SOURCED, P1]**

— i.e. they do not measure a contact normal force, they **infer it from the loop's own internal force balance**.
That is a significant simplification and worth knowing before you copy it. **[SOURCED, P1; the characterisation
as a simplification is INFERRED.]**

S6 confirms this model transfers unchanged to their EIL nodes and, crucially, identifies it as the *cause* of
sliding:

> "*Cirio et al. [2014] proposed to model friction for rod-rod contacts as a trivial anchored spring on Eulerian
> coordinates… The joint effect of the contact constraint (1) and the friction force is actually the main reason
> for sliding of contact points, and therefore for the change of the Eulerian coordinates of rod nodes.*" **[SOURCED, S6 §4.3]**

S6 also **validates** this friction model against the textbook inclined-plane test: two cloth patches at
μ = 1 = tan 45°, tested at 30/40/50/60°. **[SOURCED, S6 §4.3 inline figure]** — a cheap validation you can copy.

**(b) Smoothed / mollified Coulomb with guaranteed non-penetration (IPC family). [SOURCED, S14]**
C-IPC couples codimension-0/1/2/3 geometry with frictional contact, guarantees *intersection-free trajectories*,
and uses "*IPC's smoothed, semi-implicit friction (1 lagged iteration)*", parameterised by a velocity threshold
`eps_v` below which motion is treated as sticking. **[SOURCED, S14 §6, §7]**

**(c) Unbiased hard Coulomb at scale for rod assemblies. [SOURCED, S13]**
Daviet 2020 solves "*millions of contacts with unbiased Coulomb friction*" for Discrete Elastic Rod assemblies
(54,450 rods, 1.2M DOFs, 4.5M contacts), integrable into Projected Newton or ADMM. **[SOURCED, S13 abstract]**

**(d) What Kaldor does — and it is weaker than people assume. [SOURCED, S1]**
Kaldor 2008 do **not** implement Coulomb friction. They state plainly: "*Accurate yarn-level modeling of such
phenomena is beyond the scope of this paper*" and instead use three damping models: mass-proportional damping,
a contact damping term with separate tangential/normal coefficients (`k_dt`, `k_dn`) that
"*approximate[s] sliding friction*", and a **non-rigid motion velocity filter** over fixed overlapping regions
(Müller et al. 2006 / Rivers & James 2007) to emulate the "fuzz" between yarns. **[SOURCED, S1 §4.3]**

### NOT FOUND

- **[UNKNOWN]** A measured inter-yarn friction coefficient for a typical craft acrylic/cotton crochet yarn.
  S8 explicitly lists friction estimation as unaddressed future work. **[SOURCED, S8 §4.3: "we have not
  addressed the hysteresis of force-deformation tests… produced by inter-yarn friction… We leave this
  phenomenon as future work, which requires estimating a model of the inter-yarn friction forces."]**

---

## 6. Q5 — How is loop articulation obtained?

### FOUND

**(a) By giving the loop–loop contact its own energy term with its own angle. [SOURCED, P1]**
The knit model includes a **wrapping energy** `V = ½ k_w L (ψ − ψ₀)²` where ψ is the wrapping angle of one loop
around another, alongside bending `V = k_b θ²/Δu` (with `k_b = B π R²`) and stretch. **[SOURCED, P1]**
This is a dedicated articulation degree of freedom: how far the loop is wrapped around the loop below, distinct
from yarn bending.

**(b) By four contact nodes per stitch, so the loop has an internal shape. [SOURCED, P1]**
"*Each loop has typically four stitch contacts, hence it shares eight contact nodes with other loops.*"
**[SOURCED, P1]** A loop represented by ≥4 nodes that can each slide can change aspect ratio (tall/narrow vs
short/wide) without any yarn bending change. **[INFERRED from the SOURCED node count + sliding coordinates.]**

**(c) Emergently, from free contact (Kaldor). [SOURCED, S1]**
With contacts detected at runtime and no topological pairing, articulation is whatever the contact + bending +
inextensibility system produces. Kaldor's stated validation is qualitative comparison against laboratory
deformation of real knit samples. **[SOURCED, S1 abstract/§7]**

**(d) In the real fabric: articulation is geometric, and its kinematics are measured. [SOURCED, S10]**
S10's stitch cell is parameterised by two vectors `(c⃗, w⃗)` whose norms set the local cell dimensions, and they
measure the full displacement field `u⃗(i,j)` of the stitch network optically under load. They find affine
behaviour in `⟨c⟩` and `⟨w⟩` versus strain. **[SOURCED, S10 §II]** They also record a regime, below the onset
strain, where "*the inter-yarn contacts are not established everywhere, thus stitches can slide without further
deformation, providing the fabric with very low stiffness*". **[SOURCED, S10 §II]** — i.e. real knit fabric has a
**near-zero-stiffness articulation regime before contact closes**, which an elastic plate cannot reproduce.

### NOT FOUND

- **[UNKNOWN]** Any treatment of loop articulation for crochet stitches specifically (HDC or otherwise) with
  associated mechanics. The crochet stitch-mesh work (Guo et al. 2020) introduces a face/tile library and a
  "current loop" edge type, but I could not read the paper and **cannot confirm whether it does any physical
  relaxation at all**, let alone articulation mechanics. Treat crochet loop articulation as unmodelled in the
  literature. **[UNKNOWN]**

---

## 7. Q6 — How is topology preserved during sliding?

### FOUND — four distinct and complementary mechanisms, all citable

**(1) Persistent contact: the contact is a permanent node, so it cannot be created or destroyed by the
solver. [SOURCED, P1, S6]**
P1: "*During normal operation… the two yarns at each stitch contact are wrapped around each other persistently*".
**[SOURCED, P1]** S6: "*For intra-fabric contacts, we simply use the initial topology of the weave or knit
pattern.*" **[SOURCED, S6 §5]** The topology is an *input*, held fixed, not a runtime discovery.

**(2) A barrier on the material gap, so two sliding contacts cannot swap order along the yarn. [SOURCED, P2, S9, S6]**
P2: "*Contact between adjacent parallel yarns can be easily modeled by adding a penalty energy if two yarn
crossings get too close*", active when `u₁ − u₀ < d` with `d` set by yarn radius. **[SOURCED, P2]**
S9 gives the explicit form: `V₀,₁ = ½ k_c L (ReLU(d − Δu))²` with `d = 4R or 2R`. **[SOURCED, S9 §3.3]**
S6 confirms Cirio "*applied a repulsive force when two contacts were in close proximity*". **[SOURCED, S6 §3.2]**

**(3) Continuous-time pull-through detection (the stitch-mesh answer, and the most directly relevant one to a
"certified topology" regime). [SOURCED, S3]**
Yuksel et al. 2012 call this out as their most important improvement over prior yarn simulators:

> "*Perhaps the most important improvement over prior yarn-level simulators, though, is a method to guarantee
> that the knit topology remains consistent through the entire process by detecting when a piece of yarn could
> pass through another, an event we call yarn pull-through, and preventing pull-through from occurring.*" **[SOURCED, S3 §6.3]**

The algorithm, in full, because it is cheap and you can implement it:
- Impose a **rate limit τ** on the maximum movement of any point on the yarn per step, τ a fraction of the yarn
  radius. This reduces per-step pull-through detection to **only the pairs already in contact at the start of the
  step**. **[SOURCED, S3]**
- Place bounding spheres at regular parameter intervals on each of the two Catmull-Rom segments; test
  sphere-sphere intersection over the timestep (a quadratic). Refine recursively into smaller spheres. If an
  intersection persists at the finest level, **reduce the step size** until it does not. **[SOURCED, S3]**
- Accelerate by computing safe per-control-point bounds at the end of a step and reusing them to skip the test
  next step. **[SOURCED, S3]**

**(4) Guaranteed intersection-free trajectories by construction (IPC family). [SOURCED, S14]**
C-IPC produces "*intersection-free trajectories*" as a guarantee of the barrier formulation, for codimensional
geometry with finite thickness. **[SOURCED, S14 abstract]** This is the strongest available guarantee and is the
one most compatible with a "certified topology" invariant. **[INFERRED]**

**(5) Node removal rules — when sliding legitimately ends a contact. [SOURCED, S6]**
S6 supports removal of contact nodes for two reasons: "*the Eulerian coordinate of a node indicates that it has
exit the length of the rod*"; and "*the normal force between two constrained EoL nodes pulls them together
instead of pushing*" (a tensile normal force means the contact has separated). They did **not** support dynamic
*addition* of EoL contact nodes. **[SOURCED, S6 §5]**

### NOT FOUND

- **[UNKNOWN]** No method I found *certifies* topology the way you do (verified linkage per stitch). The
  literature either (a) fixes topology by fiat and never checks, or (b) prevents crossing geometrically. Nobody
  reported a post-hoc topological invariant check. Your certification is, as far as I can tell, stricter than
  published practice — which is an advantage, but means there is no published precedent for "sliding while a
  linkage certificate holds".

---

## 8. Q7 — Inextensibility when material coordinates move

### FOUND

**(a) In EoL, inextensibility becomes a statement about the ratio ‖Δx‖/Δu, and both are variables. [SOURCED, S6]**
`V_s = ½ k_s Δu (‖Δx‖/Δu − 1)²`. **[SOURCED, S6 Eq. 2]** There is no separate length constraint — length is
defined relative to a material length that is itself a DOF.

**(b) This creates a real, quantified stiffness blow-up. [SOURCED, S6 §3.2]** — read this one carefully, it is
the single most important warning in the whole literature for what you are about to build:

> "*Elastic forces become infinitely stiff when two sliding rod nodes get arbitrarily close to each other… In the
> undeformed case, i.e. ‖Δx‖ = Δu, the effective stiffness of the stretch energy with respect to either the
> Lagrangian or Eulerian length is ∂²V_s/∂‖Δx‖² = ∂²V_s/∂Δu² = k_s/Δu. It is evident that as the nodes slide and
> get closer in the material domain, the stiffness tends to infinity, making simulations unstable.*" **[SOURCED, S6]**

So sliding is not free: **the conditioning of your system degrades as `1/Δu`**, and `Δu` is now a DOF that can go
to zero. Any sliding implementation needs either the barrier of Q6(2), or S6's EIL nodes, or both.

**(c) Kaldor's alternative: hard per-segment length constraint + soft anti-drift energy. [SOURCED, S1 §4.1]**
One hard constraint per spline segment plus `E_len` with a *deliberately low* stiffness `k_len`, because "*it only
needs to resist the stretching or compression of mass in a local area*" — whereas without the hard constraint
`k_len` would have to hold up the whole hanging yarn. **[SOURCED, S1]**

**(d) The stitch-mesh relaxation deliberately RELAXES inextensibility. [SOURCED, S3 §6.3]** — directly relevant to
your rest-state bracketing result:

> "*Length constraints are replaced with stiff springs with a user-defined rest length per yarn loop, the rod is
> treated as isotropic with a straight rest configuration, and bending plasticity is disabled. In addition,
> gravity is set to zero and large amounts of mass-proportional damping are used to stably relax the cloth.*" **[SOURCED, S3]**

And Kaldor 2008's own relaxation stage does the same trick plus a **yarn shrink factor**:

> relax "*without the hard constraint on length and with a high length energy coefficient and high viscous
> damping… the yarn is shrunk by setting the desired arclength ℓ_i of each spline segment to c·ℓ⁰_i… c = 0.935.
> This causes the entire cloth to compress and settle into a general rest state*" **[SOURCED, S1 §6]**

with **bending stiffness 1000× lower during relaxation than during simulation** (`k_bend = 0.005` relax vs
`5` sim, in g·cm²/s²; `k_len = 10000` relax vs `2000` sim). **[SOURCED, S1 Table 1]**

**(e) The rest state in the published state of the art is NEITHER straight NOR the relaxed shape — it is a
plastically-migrated rest state. [SOURCED, S2 §3.1]** This directly addresses your bracketing measurement:

> "*Yarns are represented as inextensible rods with an isotropic bending response but a non-straight rest
> configuration.*"
> "*Yarns tend to display significant plastic behavior under deformation. To approximate this, we use a simple
> plasticity model on the rest state of the rod in angular space. If the rest state (represented as a 2D point)
> at a segment/bending element pair lies outside the circle of radius p_plastic centered at the current state of
> that pair, the rest state is projected onto the boundary of the circle. Similarly, if the rest state falls
> outside the circle of radius p_max_plastic centered at the origin, it is projected onto the boundary.*" **[SOURCED, S2]**

Their reported parameters: `yarn plasticity 0.01 ; 2.5`. **[SOURCED, S2 Table]**
**[INFERRED]** This is exactly the interpolation between your two brackets: the rest curvature is dragged toward
the current curvature but is bounded both relative to the current state (`p_plastic`) and in absolute magnitude
(`p_max_plastic`). It would let you keep a physically meaningful bending stiffness without 200–32,000× prestress,
*without* freezing the rest state at the relaxed shape.

### NOT FOUND

- **[UNKNOWN]** A published analysis of how much of a knit's apparent compliance is bending versus sliding versus
  articulation. Nobody has done the ablation you would want.

---

## 9. Q8 — Where is remeshing / reparameterisation required, and how is it done safely?

### FOUND

**Required in 2-D EoL (cloth over sharp features). [SOURCED, S5]**
Weidner et al. build a "*contact-conforming remesher*" by extending ARCSim's remesher to allow conformal
remeshing, because EOL vertices must be inserted exactly at contact boundaries and removed when contact ends.
They explicitly note that **remeshing only between time steps causes jitter** during sliding — the EOL DOFs are
what remove it. **[SOURCED, S5 §1, §3]**

**Deliberately avoided in 1-D EoL rods — and the reason is important. [SOURCED, S6 §3.2–3.3]**

> "*The classic approach to avoid degenerate discretizations is to remesh the geometry… In the case of rods, the
> trivial approach to remeshing is to collapse both adjacent nodes into one. However, this approach is not viable
> when the nodes represent two sliding contacts. It is paramount to retain the Eulerian coordinates of both nodes
> in order to determine how the contacts continue sliding.*" **[SOURCED, S6]**

Their solution instead of remeshing is the **EIL node** (Eulerian with Interpolated Lagrangian):

> "*This node has only a free Eulerian coordinate… Its Lagrangian coordinates, on the other hand, are
> interpolated between adjacent nodes.*" and "*The material distance of the degenerate segment does not
> participate in the discrete elastic energy of the rod, which results in robust equations.*" **[SOURCED, S6 §3.3, Fig. 2d]**

The strategy: "*replace offending EoL nodes with EIL nodes, and skip EIL nodes in the definition of internal
forces*", producing a mixed statics–dynamics system solved with standard solvers. **[SOURCED, S6 §1, §4]**
Scale achieved: 645K nodes (jeans pocket), up to 79,019 simultaneous EIL nodes (tablecloth), 1 ms steps. **[SOURCED, S6 Table 1]**

**Resampling is triggered by extreme events only. [SOURCED, P2]**
"*Node resampling is frequently triggered during fracture and highly plastic behaviors due to yarn pullouts and
sliding past the end of a yarn.*" **[SOURCED, P2]**

### NOT FOUND

- **[UNKNOWN]** I found no published safe recipe for reparameterising a yarn while a *topological certificate*
  is in force. The nearest available guarantees are: S3's rate-limited pull-through test (Q6.3), and S14's
  intersection-free barrier (Q6.4).

---

## 10. Q9 — Static vs kinetic friction, stick/slip, hysteresis

### FOUND — and the sources genuinely disagree, which is itself the finding

**(a) Stick/slip with an anchored spring and a hard Coulomb limit. [SOURCED, P2, P1]** — see Q4(a). Binary
stick/slip mode switch.

**(b) Continuous (Stribeck) stick→slip with NO discontinuity, argued to be more accurate at yarn speeds. [SOURCED, S9 §3.3]**
S9 argues the Coulomb model is wrong for yarns because (i) static friction matters for stick-slip and (ii) the
model is non-differentiable at the transition, and that "*the low relative speed between yarns is a special
situation where the static-to-kinetic transition could actually be continuous (as opposed to the Coulomb model),
experimentally shown by Stribeck*". Their model:

> `F_Slide = −( (k_f δu − K(δu) μF_n)/2 · K(μF_n − F_u) + (k_f δu + K(δu) μF_n)/2 ) − d_f u̇₀`
> with `δu = u₀ − ū₀` (anchor offset), `K(x) = tanh(px)`. **[SOURCED, S9 Eq. 4]**

Three regimes: `F_u = 0` → zero force; `0 ≤ F_u ≤ μF_n` → spring-like static friction with small self-excited
vibration; `F_u > μF_n` → `F_Slide = −μF_n − d_f u̇₀`. **[SOURCED, S9]**

**(c) The opposite conclusion, from measurement, at the FABRIC level. [SOURCED, S12]**
Miguel et al. model cloth hysteresis with "*an augmented reparameterization of Dahl's model*" and report:

> "*Others have already identified Dahl's model as a good match to hysteresis behavior in cloth, including the
> lack of significant static friction*" and "*We have not observed significant static (internal) friction
> either… in their data they found only very subtle Stribeck effects, without which a first-order Bliman-Sorine
> model, equivalent to a simple Dahl model, is sufficient.*" **[SOURCED, S12 §2, §3]**

They also document two features you should expect to see and should probably test for:
- **Pre-sliding**: "*the opposing friction grows smoothly, not sharply*" **[SOURCED, S12]**
- **Persistent deformation**: on unloading, "*the displacement stops when the total internal stress is canceled,
  producing a persistent deformation ε_per*", observed experimentally in both stretch and bending. **[SOURCED, S12]**

**(d) Direct quantitative measurement of hysteresis in a real knit. [SOURCED, S10]**
Poincloux et al. measure a stockinette tricot in load–unload cycles and report:
- two regimes: an almost-zero-stiffness regime below `L⁰_w = 125 mm`, then stiffening with "*a large
  hysteresis between loading and unloading phases*"; **[SOURCED, S10 §I]**
- **"*the work performed to return to the initial state is nearly half that needed to stretch the fabric, yet
  the response is consistently elastic and repeatable over the cycles, as the fabric always retrieves its initial
  shape*"**; **[SOURCED, S10 §I]**
- attributed cause: "*This dissipative behavior results from self-friction of the yarn which contributes
  oppositely in the loading and unloading phases*". **[SOURCED, S10 §I]**

**A ~50% energy-return ratio with full shape recovery is a concrete, cheap, falsifiable target for your solver.** **[INFERRED from SOURCED S10]**

**(e) Stick/slip is not smooth — it is avalanching, with power-law statistics. [SOURCED, S11]**

> "*A knit consists of a regular network of frictional contacts, linked by the elasticity of the yarn. When
> deformed, the fabric displays spatially extended avalanche-like yielding events resulting from collective
> inter-yarn contact slips.*" **[SOURCED, S11 abstract]**
> "*stitches deform elastically through bending of the yarn, but friction at the crossing points adds an
> uncertainty to the contact forces, inducing irreversible stick-slip activity. Those events propagate in the
> stitch network, generating avalanches*" **[SOURCED, S11 §1]**

Measured power-law exponents for avalanche size: −1.50±0.03 (force drops `Δf`), −1.61±0.03 (deviatoric strain
`S_d`), −1.51±0.05 (vorticity `S_ω`). **[SOURCED, S11]**

**(f) The graphics state of the art simply omits friction and says so. [SOURCED, S7, S8]**
HYLC "*omit[s] inter-yarn friction in the micro-scale quasistatic*" homogenisation and lists "*yarn-level friction
and hysteresis*" as future work. **[SOURCED, S7 §3, §9]** S8 likewise: "*In this project, we have not addressed
the hysteresis of force-deformation tests…*" **[SOURCED, S8 §4.3]** S17 notes yarn-level models are "*often
highly dampened… because the friction and contacts among yarn threads dissipate inertia energy quickly*". **[SOURCED, S17]**

**(g) The review-level summary. [SOURCED, S16]**
"*Friction dissipates energy when the contact is sliding, but can also statically trap tension within the yarn…
Signatures of solid friction are found, for instance, in the hysteretic response upon cycling quasi-static
tensile tests, stick-slip instabilities emerging from sliding contacts, or the existence of multiple rest
states.*" **[SOURCED, S16 §2]**

**"Multiple rest states" is worth dwelling on: a frictional knit does not have one relaxed shape. Your rest-state
bracketing problem may be a symptom of a frictionless model being asked to pick a unique rest state that the
real object does not have.** **[INFERRED from SOURCED S16]**

### NOT FOUND

- **[UNKNOWN]** Any friction/hysteresis measurement on crochet fabric. All the quantitative hysteresis data I
  found is knit or woven.

---

## 11. Q10 — What the named works actually do (the direct answer)

| Work | Does it allow yarn to move relative to loops? | How is conformability obtained? | Topology protection |
|---|---|---|---|
| **Kaldor et al. 2008** (S1) | **Yes, implicitly.** Material coords fixed to control points, but contacts are runtime-detected with *"no assumptions about cloth topology"*; nothing binds a material point to a stitch. **[SOURCED + INFERRED]** | Free loop kinematics + inextensible rods + penalty contact; friction only approximated by contact damping and a non-rigid-motion velocity filter. **[SOURCED]** | None explicit. Relies on stiff penalty + small steps. **[SOURCED]** |
| **Kaldor et al. 2010** (S2) | Same as 2008. | Same, accelerated by adaptive contact linearization; DER with **non-straight rest config + bending plasticity on the rest state**. **[SOURCED]** | None explicit. **[SOURCED]** |
| **Yuksel et al. 2012 Stitch Meshes** (S3) | Yes (same Kaldor engine). | Mesh-level relaxation that slides stitch-mesh vertices over a subdivision surface; then yarn-level relaxation with **length constraints replaced by stiff springs with a per-loop rest length**, straight isotropic rest, zero gravity, heavy damping. **[SOURCED]** | **Explicit continuous-time yarn pull-through detection with step-size reduction.** **[SOURCED]** |
| **Wu et al. 2019 Knittable Stitch Meshes** | **[UNKNOWN]** — not read. Cited by S7 as ensuring stitch meshes are fabricable. **[SOURCED, S7 §2]** | [UNKNOWN] | [UNKNOWN] |
| **Guo, Lin, Narayanan, McCann 2020, Representing Crochet with Stitch Meshes** | **[UNKNOWN — could not obtain full text.]** From the abstract it is a **representation** contribution: a tile library where "*each tile contains yarn geometry, and tiles connect along their edges*", plus a new edge type for the *current loop* (the loop on the hook). The abstract says this is "*amenable to yarn-level visualization and simulation*" — **it does not claim to simulate.** **[SOURCED — abstract only, https://doi.org/10.1145/3424630.3425409]** My reading is that this is a geometry/topology paper and carries no mechanics. **[INFERRED — please do not treat as established.]** |
| **Cirio et al. 2014 / 2015 / 2017** (P1, P2, corroborated by S6, S7, S8, S9) | **Yes, explicitly.** 5-DOF nodes `(x,u,v)`; `u,v` are arc-length **sliding coordinates**; "*yarns are allowed to slide at contact nodes*". **[SOURCED, P1]** | Loop-scale DOFs: sliding + a **wrapping angle energy** `½k_w L(ψ−ψ₀)²` + bending + stretch, with persistent contacts replacing collision detection. **[SOURCED, P1]** | Topology fixed by fiat (persistent contacts) + penalty barrier when two contacts approach in material space. **[SOURCED, P1, P2, S6]** |
| **Sánchez-Banderas et al. 2020 Robust EoL Rods** (S6) | **Yes** — and this is the paper that makes sliding *robust*. | EoL sliding + new EIL nodes so that sliding contacts can cross each other in material space without blowing up; enables slip-stitch knits, which "*could not be handled by previous EoL yarn-level methods*". **[SOURCED]** | Initial pattern topology fixed; node **removal** on yarn-exit or tensile normal force; no dynamic addition. **[SOURCED]** |
| **Sperl et al. 2020 HYLC** (S7) | Uses yarn-level sims (DER + Kaldor contact forces) only to *train* a thin-shell energy density; the shipped simulator has no yarns at all. **[SOURCED]** | Homogenisation — the yarn-scale conformability is baked into an anisotropic nonlinear shell energy. Friction and hysteresis explicitly omitted. **[SOURCED]** | N/A (no yarns at runtime). |
| **Sperl et al. 2022** (S8) | Periodic RVE constraints require the yarn displacement field to be "*absent of yarn sliding, yarn twist, and net rigid motion*". **[SOURCED]** | Fitting measured fabrics; nonlinear stretch + DER bending. Hysteresis/friction left as future work. **[SOURCED]** | N/A |
| **Sueda et al. 2011** (S4) | **Yes** — the origin of the E-node. "*The material of the strand flows freely through all these E-nodes.*" **[SOURCED]** | Not a cloth paper; the contribution is the representation. | N/A |
| **Weidner et al. 2018 EOL Cloth** (S5) | Yes, in 2-D, at sharp features. Motivation is precisely to avoid "*catastrophic locking*". **[SOURCED]** | EOL vertices at contact + contact-conforming remeshing. **[SOURCED]** | Inequality contact constraints allowing separation. **[SOURCED]** |
| **Bergou et al. DER 2008/2010** | Underlying rod model for S2, S7, S8, S17. Purely Lagrangian; no sliding. **[SOURCED via S2 §3.1, S7, S8]** | N/A — rods only. | N/A |

### Direct answer to your last question

**Established yarn-level methods DO get conformability with the yarn moving relative to the loops.** They differ
only in whether that motion is *implicit* (Kaldor: free contacts, fixed material coordinates, yarn can translate
through a loop) or *explicit* (Cirio/Sueda/Otaduy: an Eulerian arc-length DOF per persistent contact).

**No method in the surveyed literature welds a material point to a stitch and then relies on bending for
conformability.** The one place the literature explicitly forbids sliding — Sperl 2022's periodic RVE — does so
because periodicity requires it, not because it is physical, and that model is used only for homogenisation,
never for drape. **[SOURCED, S8 §7]**

---

## 12. Representation changes that sliding would require, per the literature

Each item below is what the literature says you must add. I have marked what it costs you against your existing
invariants.

1. **A material (arc-length) coordinate as a solver DOF at each certified linkage.** `q = (x, u, v)` where `u, v`
   are undeformed arc lengths of the two yarn passes meeting at that linkage; the two share `x`. 5 DOF per
   linkage node. **[SOURCED, P1, S6 §3.1, S9 §3.1]**
2. **Segment material length becomes `Δu = u₁ − u₀`, a variable.** Stretch energy is
   `½ k_s Δu (‖Δx‖/Δu − 1)²`. **Total yarn length is then conserved by telescoping identity, exactly** — your
   0.0000% invariant survives by construction, not by enforcement. **[SOURCED, S6 Eq. 2; P2]**
3. **A mass matrix that depends on `u` and convective `Ṁ q̇` terms in the equations of motion.** Mass must be
   *integrated* along the yarn, not lumped at nodes, or bending at the node is wrong. **[SOURCED, S9 Eq. 1/9;
   S4 Fig. 3]** — *This is the largest single implementation cost.* **[INFERRED]**
4. **A barrier on the material gap** to stop two linkages swapping order along the yarn:
   `V = ½ k_c L (ReLU(d − Δu))²`, `d ≈ 2R–4R`. **[SOURCED, S9 §3.3; P2]**
5. **A degeneracy remedy, because conditioning goes as `k_s/Δu`.** Either S6's EIL nodes (free Eulerian,
   interpolated Lagrangian, excluded from internal force stencils) or a hard floor on `Δu`. Naive node collapse
   is documented as *wrong* because it destroys the Eulerian coordinate you need. **[SOURCED, S6 §3.2–3.3]**
6. **A friction law on the sliding coordinate** — anchored zero-rest-length spring with a Coulomb limit and
   stick/slip anchor update **[SOURCED, P2]**, or S9's smooth Stribeck variant **[SOURCED, S9 Eq. 4]**, or a
   Dahl-type internal-friction model if you prefer a measured fabric-level fit with no static friction
   **[SOURCED, S12]**. You need a normal force; for knits the published shortcut is to infer it from static
   equilibrium of stretch, bending and wrapping forces. **[SOURCED, P1]**
7. **Node removal rules**: remove when `u` exits the yarn, or when the contact normal force turns tensile.
   Dynamic *addition* was not supported by S6. **[SOURCED, S6 §5]**
8. **Optional but strongly indicated: a loop wrapping-angle energy** `½ k_w L (ψ − ψ₀)²` so articulation is a
   modelled mode rather than an emergent one. **[SOURCED, P1]**
9. **Keep your pull-through certificate, and add S3's rate limit `τ` (a fraction of yarn radius per step) so the
   per-step certification only has to consider pairs already in contact.** **[SOURCED, S3 §6.3]**

---

## 13. Ranked candidate mechanisms

Ranked by (evidence strength) × (fit to your constraints) ÷ (implementation cost).

**Rank 1 — Global yarn-length conservation with per-stitch allotment (Poincloux redistribution).**
*Mechanism:* replace N per-stitch length constraints with one global constraint `Σ ℓ_k = L`, letting each stitch's
yarn allotment `ℓ_k = c_k + δ w_k` vary, resisted by a friction-like threshold.
*Evidence:* Derived from first principles and **quantitatively validated against optical stitch-level measurement
on a real knit**, including δ = 0.86 and a predicted geometric Poisson ratio ν = 0.46. **[SOURCED, S10]**
*Why rank 1:* it is the smallest possible representation change that is nonetheless the physically correct one;
it preserves total yarn length exactly; it does not require new node types, a new mass matrix, or contact
restructuring. *Caveat:* δ for HDC is **[UNKNOWN]** and must be measured.

**Rank 2 — Full EoL sliding coordinates at each certified linkage (Cirio/Sueda).**
*Evidence:* the strongest and most replicated — three papers, two granted patents, an independent open-access
re-derivation (S9), and a follow-up that hardens it (S6). Demonstrated on 645K nodes at 1 ms steps. **[SOURCED,
P1, P2, S4, S6, S9]**
*Why not rank 1:* item 3 above (mass matrix + convective terms) is a substantial rewrite of your solver core, and
S6 documents a real `1/Δu` conditioning hazard that then needs EIL nodes on top.

**Rank 3 — Frictional stick/slip with hysteresis, layered on either of the above.**
*Evidence:* anchored-spring Coulomb **[SOURCED, P2]**; Stribeck-smooth variant **[SOURCED, S9]**; Dahl fabric-level
fit **[SOURCED, S12]**; measured ~50% energy return with full shape recovery **[SOURCED, S10]**; power-law slip
avalanches **[SOURCED, S11]**.
*Note:* without a sliding coordinate there is nothing for this friction to act on, so this is strictly a
follow-on, not an alternative. **[INFERRED]**

**Rank 4 — Plastic rest-curvature migration (Kaldor 2010) as an interim fix for the rest-state bracket.**
*Mechanism:* rest curvature is dragged toward current curvature, bounded by `p_plastic` (relative) and
`p_max_plastic` (absolute). **[SOURCED, S2 §3.1]**
*Why here:* it does **not** give you a mechanism — it is still an elastic plate — but it is a ~50-line change that
sits between your two brackets and removes the 200–32,000× prestress without freezing the rest state. It is the
cheapest thing on this list and the published state of the art actually uses it. **[SOURCED + INFERRED]**

**Rank 5 — Loop wrapping-angle DOF (articulation without sliding).**
*Evidence:* one source (P1). Plausible that some of the missing compliance is loop wrap rather than yarn travel,
which would be cheaper to add. But I found **no** evidence isolating wrapping from sliding. **[SOURCED, P1;
the isolation claim is UNKNOWN.]**

**Rank 6 — Two-stage relaxation with 1000× reduced bending stiffness and a yarn shrink factor.**
*Evidence:* **[SOURCED, S1 §6 and Table 1; S3 §6.3]** — both the Kaldor and stitch-mesh pipelines do this. This is
not a conformability mechanism; it is how the published methods *obtain a rest configuration at all*. If your
"rest = relaxed shape" bracket was produced differently, this is worth comparing against.

**Rank 7 — Abandon yarn-level for drape and homogenise (HYLC).**
*Evidence:* **[SOURCED, S7]** — works, ships, is fast, and reproduces knit anisotropy. But it discards your yarn
representation and your topology certificate, and it explicitly drops friction and hysteresis. Listed for
completeness; it is not what you want for a pattern-publishing product that must certify stitch topology.
**[INFERRED]**

---

## 14. The smallest bounded experiment

**Question to answer:** *Does physically justified yarn redistribution/sliding materially improve HDC fabric
conformability/drape while preserving certified topology, yarn length, gauge and stitch morphology?*

I recommend a **two-stage** experiment where Stage 0 can kill the whole idea for a few hours' work, and Stage 1 is
the smallest simulation change that could possibly answer the question.

---

### Stage 0 — Physical measurement (half a day, cost: one ball of yarn, one hook, a phone camera, a ruler)

This is Poincloux's δ test, transposed to HDC. It is the cheapest way to find out whether yarn redistribution
even happens in HDC before you write any solver code.

**Build:** Crochet two HDC swatches in a plain yarn, ~20 stitches × 30 rows. Mark every stitch with a dot of
fabric marker (S10 tracked stitches optically; **[SOURCED, S10 §I]**).

**Measure:**
1. **Redistribution test.** Clamp the swatch and apply uniaxial tension in the row direction in ~8 steps.
   Photograph each step. Extract per-stitch course width `c` and row height `w`. Fit the single scalar `δ`
   such that `⟨c⟩ + δ⟨w⟩` is constant across all load steps. Report (a) whether such a δ exists (S10 found it
   does for knit), (b) its value, (c) the **spatial variance** of `ℓ_k = c_k + δ w_k` across the swatch at each
   load. *Variance in `ℓ_k` is direct evidence of yarn migrating between stitches.*
2. **Hysteresis.** One load–unload cycle. Compute unload work / load work. S10 measured ≈0.5 for stockinette with
   full shape recovery. **[SOURCED, S10 §I]**
3. **Reference drape + cantilever.** Peirce cantilever bending length on a strip, and a drape coefficient
   (projected area of a circular swatch draped over a smaller disc ÷ flat area). These are your simulation targets.

**Success:** a consistent δ exists, `ℓ_k` variance is measurably non-zero and grows with load, and hysteresis
ratio is meaningfully below 1.
**Failure:** `ℓ_k` variance is at noise level and `c`, `w` move rigidly → **yarn redistribution is not the
mechanism in HDC**, and you should reallocate to loop articulation (Rank 5) or rest-curvature plasticity (Rank 4).
This outcome is a genuine result and should be reported as such.

---

### Stage 1 — Minimal simulation ablation (target: 2–3 days of implementation, minutes per run)

**Do NOT implement full EoL.** Implement the Rank-1 mechanism only, which needs no new mass matrix.

**Build:**
- Keep the existing solver, geometry, certified topology and out-of-plane relaxation **unchanged**.
- Add **one scalar DOF per certified linkage**: `s_i`, the material arc-length coordinate of the yarn point that
  sits at linkage *i*. Initialise `s_i` to its present (welded) value.
- Between consecutive linkages, **resample the existing vertices** so the yarn length in that interval is
  `s_{i+1} − s_i`. Total yarn length is then `s_N − s_0`, **conserved by telescoping** — no new length
  machinery needed. **[SOURCED design rationale: S6 Eq. 2, P2.]**
- Add three terms on the `s` variables and nothing else:
  1. **Material-gap barrier**: `½ k_c L (ReLU(d − (s_{i+1} − s_i)))²` with `d` a fixed multiple of yarn radius.
     Prevents a stitch being starved of yarn and prevents linkages swapping order. **[SOURCED, S9 §3.3; P2]**
  2. **Friction on slip**: anchored zero-rest-length spring `k_f (s_i − s̄_i)` with anchor `s̄_i` updated on the
     Coulomb limit. Use a **fixed nominal normal force** for v1 (do not implement P1's equilibrium estimate yet);
     sweep it. **[SOURCED, P2]**
  3. Nothing else. No wrapping energy, no mass on `s`: run `s` **quasi-statically** (solve for `s` at fixed `x`,
     then `x` at fixed `s`, alternating). This sidesteps the convective mass terms entirely. **[INFERRED — this
     is a simplification the literature does not use; it is legitimate for a quasi-static drape test and must be
     flagged as such in the write-up.]**
- Add S3's **rate limit τ** = 0.25 × yarn radius on per-step motion, so your existing pull-through certification
  only has to consider already-contacting pairs. **[SOURCED, S3 §6.3]**

**Configurations to run (small swatch: 16 wales × 20 rows, HDC):**
- **A. Baseline** — current solver, `s` frozen (this is exactly your present model).
- **B. Sliding, frictionless** — `k_f = 0`. Upper bound on how much sliding can possibly buy.
- **C. Sliding, frictional** — sweep μ over ~5 values spanning the measured hysteresis ratio from Stage 0.
- **D. Null control** — `s_i` perturbed by random offsets of the same RMS magnitude as B produced, *without*
  energy minimisation. This separates "mechanics did something" from "stitch sizes just got noisier".

**Load cases (2):** (i) cantilever off a table edge (you already have the beam-theory harness);
(ii) square swatch draped over a sphere of radius ≈ ⅓ the swatch width — the standard double-curvature test.
Double curvature is the discriminating case: an elastic plate cannot conform to a sphere without either
stretching or buckling into a few large lobes. **[INFERRED]**

**Measure (pre-register these before running):**
| Metric | Why | Pass condition |
|---|---|---|
| Topology certificate | Non-negotiable invariant | 100% of linkages verified, every step, all configs |
| Pull-through events | Non-negotiable invariant | 0 |
| Total yarn length drift | Non-negotiable invariant | \|ΔL\|/L < 1e-6 (telescoping should give ~machine epsilon) |
| Gauge at rest (stitches/10 cm, rows/10 cm) | Must not silently change the product | within ±2% of A |
| Stitch morphology validator | Non-negotiable invariant | passes, all configs |
| **RMS Gaussian curvature of the mid-surface, sphere-drape case** | The plate/mechanism discriminator | **≥ 3× config A** |
| Number of independent fold lobes, sphere drape | Human-visible drape character | ≥ 3 where A gives ≤ 1 |
| Cantilever bending length | Absolute physical accuracy | within ±10% of the Stage-0 measurement |
| Hysteresis ratio (load/unload work), config C | Friction is doing physical work | within ±0.15 of Stage-0 measurement |
| Spatial variance of `s_{i+1} − s_i` under load | Is sliding actually active? | non-zero and structured (edge vs interior), not white noise |
| Sensitivity of drape to bending stiffness | Your existing diagnostic | monotone and non-saturating, as in your "rest = relaxed" bracket |

**Definition of success:** all five invariants hold; Gaussian-curvature RMS ≥ 3× baseline; fold-lobe count
increases; cantilever within ±10% of measurement; and config D (null control) shows **none** of these effects.

**Definition of failure (and it must be reported, not rescued):** sliding activates (variance of `Δs` is
non-trivial) but the curvature and lobe metrics move < 5% versus baseline. That means **redistribution is not the
missing compliance for HDC**, and the next candidates are Rank 5 (wrapping-angle articulation) and Rank 4
(plastic rest curvature). Equally, if sliding cannot be made to hold the topology certificate at any `k_c`, the
experiment has told you that a full EoL treatment with EIL nodes (Rank 2) is required rather than the cheap
version, and you will have learnt that for 3 days instead of 3 weeks.

**Cost estimate:** Stage 0 — half a day plus materials. Stage 1 — 2–3 days implementation, ~40 solver runs on
16×20 swatches (small enough for minutes each on one machine), 1 day analysis. **No external spend beyond yarn
and a hook.** **[INFERRED — this is my estimate, not a sourced figure.]**

**What would make me wrong:** I could not read the Cirio TVCG paper or the crochet stitch-mesh paper in full.
If the TVCG paper contains a knit-specific sliding constraint that my patent reading mischaracterises, item 2 and
Rank 2 would need revision. Get institutional access to DOI 10.1109/TVCG.2016.2592908 and DOI 10.1145/3424630.3425409
before committing to a full EoL rewrite. **[Stated explicitly as a known gap.]**

---

## 15. Label index — every substantive claim

**SOURCED** (full text read): Kaldor's fixed material coordinates and anti-drift energy (S1 §4.1); Kaldor's
topology-free runtime contact detection (S1 §2, §7); Kaldor's damping-as-friction and non-rigid velocity filter
(S1 §4.3); Kaldor's relaxation-by-shrinking and the 1000× bending-stiffness reduction (S1 §6, Table 1);
Kaldor 2010's non-straight rest configuration and bounded rest-state plasticity (S2 §3.1); stitch-mesh
replacement of length constraints by per-loop springs with straight rest and zero gravity (S3 §6.3); stitch-mesh
pull-through detection algorithm with rate limit and step-size reduction (S3 §6.3); Sueda's Eulerian node and
free material flow through it (S4 §2.2, Fig. 2c); Sueda's warning against mass lumping (S4 Fig. 3); EOL cloth's
contact-conforming remesher and catastrophic-locking motivation (S5 §1); EoL 5-DOF rod–rod formulation and shared
Lagrangian coordinates (S6 §3.1); the `k_s/Δu` stiffness divergence (S6 §3.2); why naive node collapse is wrong
(S6 §3.2); EIL nodes (S6 §3.3); anchored-spring friction as the cause of sliding, and the inclined-plane
validation (S6 §4.3); topology fixed from pattern, node removal rules, no dynamic addition (S6 §5); scale figures
(S6 Table 1); HYLC's omission of inter-yarn friction and hysteresis (S7 §3, §9); Sperl 2022's "absent of yarn
sliding" RVE constraint and unaddressed hysteresis (S8 §4.3, §7); the EoL DOF definition, mass-matrix dependence
on Eulerian coordinates, material-gap ReLU barrier, and Stribeck friction model (S9 §3.1–3.3, App. B);
Poincloux's sliding-between-stitches statement, global length conservation `⟨c⟩+δ⟨w⟩`, δ=0.86, ν=0.46, the
two-regime response and ~50% energy return with full recovery (S10); avalanche stick-slip and its exponents
(S11); Dahl model, absence of significant static friction, pre-sliding and persistent deformation (S12);
Daviet's scale and unbiased Coulomb (S13 abstract); C-IPC's intersection-free guarantee and smoothed lagged
friction (S14 abstract, §6, §7); CT2Yarn's statement that crochet computational work is almost entirely on
synthetic structures (S15 §1); the review's solid-vs-viscous friction distinction and "multiple rest states"
(S16 §2); yarn-level models being heavily damped by contact friction (S17).

**SOURCED (patent text, not peer-reviewed paper):** knit stitch = 4 contact nodes; 5-DOF `(x,u,v)` with arc-length
sliding coordinates; material conservation penalty `½k_l L(l/L−1)²`; wrapping energy `½k_w L(ψ−ψ₀)²`; bending
`k_b θ²/Δu` with `k_b = Bπ R²`; Coulomb friction via anchored springs; normal compression inferred from static
equilibrium of stretch/bending/wrapping; persistent-contact topology assumption (P1). Warp/weft crossing DOFs;
`Δu` as rest length; velocity coupling to sliding; stick/slip anchor update; parallel-yarn penalty when
`u₁−u₀ < d`; node resampling during fracture/pullout (P2).

**SOURCED (abstract only):** Guo/Lin/Narayanan/McCann 2020 — tile library with yarn geometry, "current loop" edge
type, claim of being *amenable to* simulation.

**INFERRED (my reasoning, not established):** that Kaldor's representation permits yarn to translate through a
loop and hence redistributes length between stitches; that your welded-material-coordinate configuration is a
third option the literature does not use; that four sliding nodes per loop confer articulation independent of
bending; that Kaldor 2010's bounded rest-state plasticity sits between your two brackets; that "multiple rest
states" may explain your rest-state bracketing difficulty; that the crochet stitch-mesh paper carries no
mechanics; that quasi-static alternation on `s` legitimately sidesteps convective mass terms; the cost estimates;
the double-curvature test as the plate/mechanism discriminator; that C-IPC's guarantee is the strongest available
match to a topology certificate.

**UNKNOWN (looked, did not find — do not fill these in):** any crochet-specific yarn-level simulator; δ or any
yarn-consumption parameter for HDC; friction coefficient or hysteresis data for crochet fabric; any published
ablation isolating the contribution of sliding to drape; any EoL formulation treating a loop as a curve rather
than as ~4 point contacts; any published method that certifies topology post hoc during sliding; any safe
reparameterisation recipe under a topology certificate; whether Wu et al. 2019 or Guo et al. 2020 perform
physical relaxation; whether r-adaptive Cosserat rods have been applied to knits.
