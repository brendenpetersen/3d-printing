# FDM design rules (Bambu X2D, PLA)

Rules of thumb for designing parts that print cleanly, ideally without supports.
Numbers below assume the **0.4mm nozzle** (default). With the **0.2mm nozzle**,
minimum walls/features roughly halve (min wall ~0.5mm) at the cost of print time —
use it only when a design genuinely needs fine detail.

## Tolerances & fit
- Holes print **0.2–0.3mm undersized** (inward shrink + elephant's foot). Oversize
  holes by that much for a clearance fit.
- **Press-fit a round stick/pin:** taper the socket — wider at the mouth, ~0.5–0.8mm
  narrower over the depth — so a range of real diameters wedges somewhere along it.
  Add a short countersink lead-in so it starts easily and elephant's-foot can't
  pinch the mouth.
- Clearance for mating/moving parts: ~0.2mm gap; snug slip fit ~0.1mm.

## Walls & features
- Min wall ~1.0mm (≥3 perimeters). For load-bearing parts, more perimeters beats
  more infill.
- Min embossed/engraved feature ~0.4mm wide and ≥0.3mm deep to survive.
- Fillet or chamfer stressed junctions to spread load — sharp inside corners are
  crack starters. A generous fillet where a handle/post meets a plate is worth more
  than added thickness.

## Overhangs & orientation
- Overhangs up to **~45°** from vertical print unsupported; steeper needs support
  or a chamfer.
- Bridges up to ~5–10mm span print OK; longer sags.
- Put the largest flat face on the bed. Orient so load crosses layer lines rather
  than running along them — layer adhesion is the weak axis.
- A dome/hemisphere prints support-free pointing **up**; pointing **down** it needs
  support — flip the part or split it.
- First-layer "elephant's foot": chamfer the bottom edge ~0.4–0.6mm if a crisp base
  matters for fit.

## Multi-part assembly (snap-fits, alignment, glue)
When a model is split into parts that combine (often to give each color its own
body and clean print orientation):
- **Split at flat interfaces along color/feature boundaries** — never through a
  curved or load-bearing region. Each part should get its own critical face flat
  on the bed.
- **Snap-fit clearance:** ~0.1–0.2mm gap on mating snap surfaces. PLA is stiff and
  brittle, so a cantilever snap wants a *longer, thinner* beam, a lead-in chamfer on
  the hook, and modest engagement (~0.5–1mm hook depth) so it flexes instead of
  snapping. Test-print the joint before committing to the full part.
- **Alignment:** add registration pins/holes or a lip so parts self-locate. Pin
  ~0.2mm under the hole for a slip fit; less for a press fit.
- **Glue joints:** give mating faces flat, generous contact area — a shallow
  tongue-and-groove or recessed lip aligns the parts and hides the seam. PLA bonds
  well with cyanoacrylate (CA); leave ~0.1mm gap for the glue film.

## By-layer color changes (AMS)
- One body; color switches at a Z height in the slicer. Put each color boundary on
  a **flat, horizontal transition** so the change reads as a clean line.
- Report the suggested change height(s) in mm — the user sets them in Bambu Studio.

## Sanity checks before slicing
- Watertight, single body, manifold — run the **verify-print-mesh** skill.
- Bounding box within the bed.
- Thinnest wall ≥ the minimum above; smallest hole ≥ nozzle width after shrink.
