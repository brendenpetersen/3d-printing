# CadQuery / OpenCascade cookbook

Patterns and fixes from real failures in this repo. Check here first when an OCC
operation errors or silently produces wrong geometry.

## Revolve a whole axisymmetric body instead of unioning primitives
Disc + fillet + shaft + dome all share an axis → build ONE half-profile in the XZ
plane and `.revolve(360, (0,0,0), (0,1,0))`. This avoids every boolean pitfall
below and is watertight by construction. Only add separate solids (via mesh union)
for genuinely non-axisymmetric features like a helical rib.

## fillet() fails: "BRep_API: command not done"
OCC's fillet builder chokes on a union's split circular seam edge at radius ≳3mm.
Fixes, best first:
- Revolve the fillet as a concave arc segment in the body profile (no fillet op).
- If you must fillet a real edge, select it robustly and keep the radius modest.

## Boolean fuse silently no-ops (volume unchanged, no error)
`body.union(swept_solid)` can return the body unchanged where a Frenet-swept solid
grazes a faceted (polyline-revolved) surface tangentially. Fuzzy `tol` does not
help. Fix: union at the **mesh** level with manifold3d:

```python
parts = [to_watertight_mesh(body)] + [to_watertight_mesh(r) for r in ribs]
mesh = trimesh.boolean.union(parts, engine="manifold")   # needs manifold3d
```

Sanity-check the fused volume actually increased — a silent no-op looks like success.

## Revolved spline self-intersects → invalid solid
A `.spline(...)` whose start tangent isn't exactly vertical bulges past the
preceding segment, and the revolve self-intersects (invalid, not watertight). Fix:
sample a **dense polyline** instead — `.lineTo` in a loop at ~0.25mm steps.

```python
n = max(120, int((z_end - z_start) / 0.25))
for i in range(1, n + 1):
    z = z_start + (z_end - z_start) * i / n
    profile = profile.lineTo(radius_at(z), z)
```

## STL has unstitched seams (not watertight after export)
CadQuery tessellates each B-rep face independently, so the exported STL can have
open seam edges. Repair after export:

```python
m = trimesh.load(path)
m.update_faces(m.nondegenerate_faces()); m.merge_vertices()
trimesh.repair.fill_holes(m); trimesh.repair.fix_normals(m)   # fill_holes needs networkx
assert m.is_watertight
```

## Blind tapered socket (press-fit hole)
`cq.Solid.makeCone(r_entry, r_tip, depth)` positioned at the face, then
`body.cut(...)`. Add a second shallow cone for the countersink lead-in. Entry wider
than tip gives the taper that grips a range of stick diameters.

## Tessellation quality for export
`cq.exporters.export(shape, path, tolerance=0.01, angularTolerance=0.1)` is a good
default. Tighten `tolerance` only if curved surfaces look faceted in the preview.
