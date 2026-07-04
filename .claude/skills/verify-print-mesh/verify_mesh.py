# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["trimesh", "numpy", "scipy", "networkx", "matplotlib"]
# ///
"""Printability checker: watertight / single-body / manifold / bed-fit + preview.

Usage:
  uv run verify_mesh.py <file.stl> [more.stl ...] [--bed 256x256x256] [--no-preview]

Exits non-zero if any file fails the hard checks (watertight AND single-body).
"""

import argparse
import sys

import numpy as np
import trimesh


def parse_bed(s: str):
    try:
        x, y, z = (float(v) for v in s.lower().split("x"))
        return (x, y, z)
    except Exception:
        raise argparse.ArgumentTypeError("bed must look like 256x256x256")


def render(mesh: trimesh.Trimesh, path: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    light = np.array([0.4, -0.5, 0.77])
    light /= np.linalg.norm(light)
    base = np.array([0.82, 0.66, 0.30])
    shade = np.clip(mesh.face_normals @ light, 0.15, 1.0)
    colors = np.hstack([shade[:, None] * base, np.ones((len(shade), 1))])

    fig = plt.figure(figsize=(6, 6))
    ax = fig.add_subplot(111, projection="3d")
    ax.add_collection3d(
        Poly3DCollection(mesh.vertices[mesh.faces], facecolors=colors, edgecolors="none")
    )
    lo, hi = mesh.bounds
    ctr = (lo + hi) / 2.0
    span = float((hi - lo).max()) * 0.6 + 1e-6
    ax.set_xlim(ctr[0] - span, ctr[0] + span)
    ax.set_ylim(ctr[1] - span, ctr[1] + span)
    ax.set_zlim(lo[2], lo[2] + 2 * span)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=20, azim=40)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def check(path: str, bed, do_preview: bool) -> bool:
    mesh = trimesh.load(path, force="mesh")
    watertight = bool(mesh.is_watertight)
    bodies = int(mesh.body_count)
    manifold = bool(mesh.is_winding_consistent)
    ext = mesh.extents
    fits = all(e <= b for e, b in zip(sorted(ext), sorted(bed)))

    print(f"\n=== {path} ===")
    print(f"  watertight:                   {watertight}")
    print(f"  bodies:                       {bodies}")
    print(f"  winding-consistent (manifold):{manifold}")
    print(f"  volume:                       {mesh.volume / 1000:.2f} cm^3")
    print(f"  bbox (mm):                    {ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f}")
    print(f"  fits bed {bed[0]:.0f}x{bed[1]:.0f}x{bed[2]:.0f}:          {fits}")

    if not watertight:
        r = mesh.copy()
        r.update_faces(r.nondegenerate_faces())
        r.merge_vertices()
        trimesh.repair.fill_holes(r)
        trimesh.repair.fix_normals(r)
        verdict = (
            "re-export from source with the repair pass"
            if r.is_watertight
            else "source solid likely invalid (self-intersection / bad boolean)"
        )
        print(f"  -> after repair watertight:   {r.is_watertight}  ({verdict})")

    if do_preview:
        out = path.rsplit(".", 1)[0] + "_preview.png"
        render(mesh, out)
        print(f"  preview:                      {out}")

    return watertight and bodies == 1


def main() -> None:
    ap = argparse.ArgumentParser(description="FDM printability checker")
    ap.add_argument("files", nargs="+", help="mesh files (.stl/.obj/...)")
    ap.add_argument(
        "--bed",
        type=parse_bed,
        default=(256.0, 256.0, 260.0),  # Bambu X2D main nozzle; dual-nozzle: 235.5x256x256
        help="WxDxH in mm (default X2D main-nozzle 256x256x260)",
    )
    ap.add_argument("--no-preview", action="store_true", help="skip preview PNGs")
    args = ap.parse_args()

    ok = True
    for f in args.files:
        ok &= check(f, args.bed, not args.no_preview)

    print(
        f"\n{'PASS' if ok else 'FAIL'}: "
        f"{'all files printable' if ok else 'one or more files failed the hard checks'}"
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
