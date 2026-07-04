# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["trimesh", "numpy", "scipy", "networkx", "manifold3d", "shapely"]
# ///
"""<MODEL NAME> — organic/sculptural FDM-printable mesh (trimesh + numpy).

Print orientation: flat back on the bed (the z = 0 plane); the form grows +Z.
Origin at the bed. Slicing the solid with the z = 0 plane gives it a flat
bed/contact face so it prints support-free.

Run:  uv run trimesh_starter.py
Then: uv run ../../verify-print-mesh/verify_mesh.py model_small.stl model_medium.stl model_large.stl
"""

import numpy as np  # noqa: F401  (your generator will want it)
import trimesh

# --- Parameters -------------------------------------------------------------
SIZE = 40.0                 # nominal overall size (mm)
FLAT_FRACTION = 0.3         # how deep to slice the bottom flat (fraction of SIZE)


# --- Build ------------------------------------------------------------------
def build(scale: float = 1.0) -> trimesh.Trimesh:
    """Return one watertight, flat-backed mesh. Replace with your generator.

    The example is a sphere sliced flat on the bottom; swap in your real form
    (lofts along a spine, faceted clusters, etc.). Whatever you build, finish by
    slicing at z = 0 with cap=True so there's a flat bed face, then merge_vertices
    and fix_normals.
    """
    radius = SIZE * scale / 2.0
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=radius)
    mesh.apply_translation([0, 0, radius])  # sit tangent to the bed
    cut_z = SIZE * scale * FLAT_FRACTION
    mesh = mesh.slice_plane([0, 0, cut_z], [0, 0, 1], cap=True)
    mesh.merge_vertices()
    trimesh.repair.fix_normals(mesh)
    # Drop to z = 0 so the flat face is on the bed.
    mesh.apply_translation([0, 0, -mesh.bounds[0][2]])
    return mesh


# --- Export + verify (the quality gate) -------------------------------------
def export(mesh: trimesh.Trimesh, basename: str) -> None:
    assert mesh.is_watertight, f"{basename}: not watertight"
    assert mesh.body_count == 1, f"{basename}: {mesh.body_count} disconnected bodies"
    mesh.export(f"{basename}.stl")
    e = mesh.extents
    print(
        f"wrote {basename}.stl  bbox {e[0]:.1f} x {e[1]:.1f} x {e[2]:.1f} mm  "
        f"{mesh.volume / 1000:.1f} cm^3"
    )


if __name__ == "__main__":
    for name, s in {"small": 0.7, "medium": 1.0, "large": 1.4}.items():
        export(build(s), f"model_{name}")
