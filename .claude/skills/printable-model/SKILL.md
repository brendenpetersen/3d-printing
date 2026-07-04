---
name: printable-model
description: Scaffold and build a new FDM-printable 3D model from parametric code in this repo. Use when the user wants to create a new printable part, model, generator, or object — a bracket, holder, guard, enclosure, knob, organic/sculptural piece, etc. Guides stack choice (CadQuery for engineered/parametric, trimesh for organic), print-orientation modeling, the watertight/manifold verify gate, preview rendering, and Bambu slicing notes. Bundles starter templates and FDM/CadQuery/Bambu reference sheets.
---

# printable-model

Build a new printable model the way this repo does it: parametric code, print-
oriented, verified, previewed. Follow the repo `CLAUDE.md`; this skill adds the
step-by-step and the reference material next to it.

## Steps
1. **Clarify the essentials** — ask only what you can't infer:
   - Key dimensions, and which ones must be parameters.
   - Function / fit constraints (does something insert, mate, hang, snap?).
   - **Color strategy:** single, split-into-parts (snap/glue), or by-layer AMS
     change? It decides how you split bodies and what you deliver — see the repo
     CLAUDE.md "Color strategy" section. Don't assume; ask.
   - Printer/material if not the default (Bambu X2D, PLA) — it sets tolerances.
   Recommend sensible defaults rather than asking about everything.
2. **Pick the stack:**
   - *Engineered / dimensioned* (holes, sockets, flat faces, brackets, threads):
     **CadQuery** → start from `templates/cadquery_starter.py`.
   - *Organic / sculptural* (blades, clusters, terrain, lofts, blobs):
     **trimesh + numpy** → start from `templates/trimesh_starter.py`.
3. **Model in print orientation** — origin on the bed, +Z up. Read
   `references/fdm-design-rules.md` before dimensioning holes, walls, or overhangs.
4. **Export + verify in the script:** assert watertight + single-body + a
   dimension check inside the export function (both templates already do this).
5. **Render a preview PNG and show the user** (templates do this), or run the
   `verify-print-mesh` skill which also renders one.
6. **Report slicing notes** relevant to this part from
   `references/bambu-slicing.md` (orientation, supports, infill, time levers).
7. **When an OCC/CadQuery op fails or misbehaves,** check
   `references/cadquery-cookbook.md` first — most failures we've hit are solved there.

## Conventions
- One `uv` inline script per model; parameters in a labeled block at the top with
  `mm` comments. Emit multiple named variants from a `--combos` flag when useful.
- Document the coordinate system and print orientation in the module docstring.
- Prefer revolving a whole axisymmetric profile over unioning primitives — it
  sidesteps most boolean pitfalls and is watertight by construction.

## Bundled files
- `templates/cadquery_starter.py` — parametric solid, verify + report baked in.
- `templates/trimesh_starter.py` — organic mesh, multi-size variants, flat bed face.
- `references/fdm-design-rules.md` — tolerances, walls, overhangs, orientation.
- `references/cadquery-cookbook.md` — OCC patterns and fixes from real failures.
- `references/bambu-slicing.md` — Bambu Studio settings and time levers for X2D/PLA.
