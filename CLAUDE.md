# 3D Printing Projects

Parametric, code-generated 3D models for FDM printing. Each subdirectory is one
model or generator. **"Code, not pixels":** geometry is defined in scripts with
key dimensions as named parameters — never hand-modeled in a GUI.

## Workflow skills
- **printable-model** — scaffold a new model end to end (stack choice, print-
  oriented modeling, verify, preview, slicing notes). Invoke when starting a new part.
- **verify-print-mesh** — check any STL is printable (watertight / single-body /
  manifold / bed-fit) and render a preview. Invoke after generating a model.

## Stack
- **Language:** Python — **always run it through `uv`**, never a bare `python`/`pip`
  or a hand-managed venv. Each model is a `uv` inline script: a PEP 723 `# /// script`
  header with pinned deps at the top, run with `uv run model.py`. The script self-
  installs its deps, so there's nothing to set up and runs are reproducible.
- **CAD kernel (engineered parts):** CadQuery (OpenCascade) for parametric solids —
  discs, handles, sockets, brackets, enclosures, anything dimensioned and mechanical.
- **Mesh (organic parts):** trimesh + numpy for sculptural/organic forms — lofts
  along spines, faceted shapes, clusters.
- **Robust booleans:** manifold3d via `trimesh.boolean.union(..., engine="manifold")`.
  Reach for it whenever an OCC boolean misbehaves (see the cookbook in the skill).
- **Preview:** matplotlib `Poly3DCollection` with a simple Lambert shade. Always
  render a PNG and show the user — a model you can't see isn't reviewed.

## Deliverables
- Ship **STL** by default — one file per printable body/part/variant.
- Use **3MF** when a single file must carry more than geometry: multiple objects,
  per-object slicer settings, or a preset build-plate layout (see Color strategy).
- **Never** ship STEP or other CAD-interchange formats as the deliverable — they're
  not print-ready and we don't hand them off.

## Color strategy (clarify per project — it drives modeling, not just export)
Ask which approach the user wants before modeling; it changes the geometry:
- **Single color** — one body, one STL. Default.
- **Split into separate parts that assemble** — model each color as its own body
  with real mating features: snap-fit joints (with clearance), alignment pins/lips,
  and flat glue faces where the joint is permanent. Deliver one STL per part (or a
  3MF with all parts laid out). See the multi-part rules in
  `references/fdm-design-rules.md`.
- **By-layer AMS color change** — one body, one STL; color switches at Z heights in
  the slicer. Design so each color boundary lands on a clean, flat Z transition, and
  report the suggested change height(s) in mm alongside the deliverable.

Which one fits "depends on the ask" — so ask. Don't assume single-color, and don't
assume a split when a by-layer change would do.

## Quality gate (do not skip)
A model is NOT done until, for every exported STL/3MF:
1. `mesh.is_watertight` is True,
2. `mesh.body_count == 1` (unless the design is intentionally multi-part),
3. the bounding box is checked against both the intended size and the bed, and
4. a shaded preview PNG has been rendered and shown to the user.

Assert 1–3 inside the export function so a bad mesh fails loudly at build time.
The `verify-print-mesh` skill runs all four on demand.

## Modeling rules
- **Model in print orientation** — the part sitting on the bed as it will print,
  origin at the bed, +Z up. Decide orientation before modeling, not after.
- **Bias to support-free:** keep overhangs ≤45° from vertical, put a flat face on
  the bed, round/chamfer where a sharp overhang would otherwise need support. A
  hemisphere prints clean pointing up, needs support pointing down.
- **FDM tolerances:** holes print ~0.2–0.3mm undersize — oversize them and add a
  slight taper for press-fits. Min wall ~1mm (≥3 perimeters at a 0.4mm nozzle).
  Full details in the printable-model skill's `references/fdm-design-rules.md`.

## Printer / slicer (this user)
- **Printer:** Bambu Lab X2D — **dual-nozzle**, with an **AMS** (multi-color /
  multi-material capable). **Slicer:** Bambu Studio.
- **Nozzles owned:** 0.4mm (default) and 0.2mm (fine detail). Minimum wall and
  feature sizes scale with the mounted nozzle — see `references/fdm-design-rules.md`.
- **Build volume:** 256 × 256 × 260 mm on the main nozzle; dual-nozzle mode narrows
  X to 235.5mm (usable 235.5 × 256 × 256 mm). Bed-fit checks default to 256×256×260;
  design for the smaller envelope if a part will print in dual-nozzle/multi-color mode.
- **Material:** PLA, usually single color.
- Tall thin parts are **cooling-gated** (minimum-layer-time forces per-layer waits):
  the real time levers are **fewer layers** (larger layer height) and **batching
  copies** — not lower infill or fewer walls. See `references/bambu-slicing.md`.
- Defaults: no brim/supports for parts with a flat bed face; Monotonic top/bottom.
- Because the X2D has a second nozzle, **soluble/second-material supports are
  possible** — but still design support-free first; treat dual-material as a
  deliberate choice, not a crutch.

## Gotchas (learned the hard way — see the cookbook for fixes)
- OCC `fillet` throws "BRep_API: command not done" on a union's split circular seam
  edge at r≳3. Fix: revolve the fillet as part of an axisymmetric body profile.
- OCC `fuse` silently **no-ops** where a swept solid grazes a faceted surface
  tangentially (fused volume unchanged, no error). Fix: union at the mesh level
  with manifold3d.
- Revolving a **spline** whose start tangent isn't exactly vertical self-intersects
  into an invalid solid. Fix: sample a dense **polyline** instead.
- CadQuery tessellates faces independently, so an exported STL can have unstitched
  seams. Fix: `merge_vertices()` + `fill_holes()` after export (needs `networkx`).
