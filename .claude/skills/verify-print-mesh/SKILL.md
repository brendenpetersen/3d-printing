---
name: verify-print-mesh
description: Verify an STL/OBJ mesh is FDM-printable — watertight, single-body, manifold, and fits the print bed — and render a shaded preview PNG. Use after generating any 3D model in this repo, before declaring it done or slicing it, and to diagnose why a mesh won't slice cleanly (holes, non-manifold edges, flipped normals, disconnected shells).
---

# verify-print-mesh

Runs the printability quality gate on one or more mesh files and renders a
preview. This is the mandatory check before any model is "done" (see the repo
`CLAUDE.md` quality gate).

## Usage
Run the bundled checker with `uv` (no install needed), from the repo root:

```
uv run .claude/skills/verify-print-mesh/verify_mesh.py <file.stl> [more.stl ...] [--bed 256x256x256] [--no-preview]
```

It prints a per-file report and exits non-zero if any file fails the hard checks
(watertight AND single-body). For each file it reports:
- watertight, body count, winding-consistent (manifold proxy), volume
- bounding box (mm) and whether it fits the bed (default 256×256×256 — pass
  `--bed` for the actual printer)
- whether a repair pass (`merge_vertices` + `fill_holes` + `fix_normals`) would
  make an unclean mesh watertight
- writes `<file>_preview.png` (three-quarter shaded view) unless `--no-preview`

## Interpreting failures
- **Not watertight / open edges:** usually unstitched tessellation seams. If the
  script says repair would fix it, re-export from source with the repair pass
  baked in (see the printable-model cookbook). If repair does NOT close it, the
  source solid is likely invalid (self-intersection from a boolean or a
  spline-revolve) — fix the geometry, not the mesh.
- **body_count > 1:** disconnected shells — either an intended multi-part model,
  or a boolean that left a floating fragment. Inspect the preview.
- **Doesn't fit bed:** scale down or split the model; confirm the target bed size.

Always interpret and relay the results to the user — don't just paste the raw
output.
