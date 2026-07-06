# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["trimesh", "numpy", "scipy"]
# ///
"""Convert an STL to a GLB for a web 3D viewer (e.g. model-viewer / Flutter).

The coin generators export STL in millimetres; glTF/GLB conventionally uses
metres, so the default --scale is 0.001. The coin STLs sit X=width,
Y=thickness, Z=egg-long-axis. A viewer with Y up (e.g. model-viewer) then
shows the coin lying flat (thickness vertical); pass --upright to stand the
egg's long axis up along +Y with the face toward +Z, so it renders as an
upright, edge-spinning coin. A PBR material is attached; the defaults
replicate the old dragon-eggs coin.glb (the game overrides metallic/roughness
live anyway).

    uv run stl_to_glb.py IN.stl OUT.glb [--upright] [--scale 0.001] [--color R G B]
"""

from __future__ import annotations

import argparse

import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial


def convert(in_stl, out_glb, scale, color, metallic, roughness, upright=False):
    mesh = trimesh.load(in_stl, force="mesh")
    assert mesh.is_watertight, f"{in_stl}: not watertight"
    mesh.apply_scale(scale)
    if upright:
        # STL is X=width, Y=thickness, Z=egg-long-axis. Rotate -90 deg about X
        # so the long axis stands up (+Y) and thickness faces the camera (+Z).
        mesh.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
    mesh.apply_translation(-mesh.bounds.mean(axis=0))  # center for clean framing
    mesh.visual = trimesh.visual.TextureVisuals(
        material=PBRMaterial(
            baseColorFactor=[*color, 1.0],
            metallicFactor=metallic,
            roughnessFactor=roughness,
        )
    )
    mesh.export(out_glb)
    e = mesh.extents
    print(f"wrote {out_glb}  extents {e[0]:.4f} x {e[1]:.4f} x {e[2]:.4f} (glTF units)")
    print(f"  material baseColor {color}  metallic {metallic}  roughness {roughness}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("in_stl")
    ap.add_argument("out_glb")
    ap.add_argument("--upright", action="store_true",
                    help="stand the egg long axis up (+Y), face toward +Z")
    ap.add_argument("--scale", type=float, default=0.001, help="mm -> m (default)")
    ap.add_argument("--color", type=float, nargs=3, default=[0.4, 0.4, 0.4],
                    metavar=("R", "G", "B"), help="base color 0..1 (default = old grey)")
    ap.add_argument("--metallic", type=float, default=0.5)
    ap.add_argument("--roughness", type=float, default=0.5)
    args = ap.parse_args()
    convert(args.in_stl, args.out_glb, args.scale, args.color, args.metallic,
            args.roughness, upright=args.upright)
