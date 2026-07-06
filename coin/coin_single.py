# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#     "numpy",
#     "trimesh",
#     "scipy",
#     "networkx",
#     "shapely",
#     "mapbox-earcut",
#     "manifold3d",
#     "svgpathtools",
#     "matplotlib",
#     "triangle",
# ]
# ///
"""Egg coin, single-color, printer-friendly lips — prints UPRIGHT, support-free lips.

The TinkerCAD original is a straight extrusion: the egg lip and the diamond lip
rise from the face at 90 deg. Printed upright (standing on the rounded egg end,
the only orientation that keeps both faces clean), those steps turn into
horizontal ceilings near the top of the print. This generator replaces each
step with a straight chamfer ramp at <= 45 deg from the face plane, so no lip
surface ever overhangs more than CHAMFER_ANGLE_DEG from vertical, anywhere
around the outline. The ramp eats into the *face* side, keeping the lip's
top silhouette (its drawn width) exactly as designed.

Coordinates / print orientation: exported standing on edge — the coin plane is
the world XZ plane, thickness along Y (centered), +Z up, egg's rounded end
tangent to the bed at z = 0. Set FLAT_BASE_MM > 0 to shave a small flat chord
at the contact point for a more reliable first layer.

Run:  uv run coin_single.py            # writes coin_single.stl + preview PNG
      uv run coin_single.py --chamfer-angle 40 --flat-base 0.6
"""

from __future__ import annotations

import argparse

import numpy as np
import trimesh

from coin_outlines import (
    REF_BBOX,
    assemble,
    band,
    buffer_loop,
    cap,
    lift,
    load_outlines,
    loop_width_to,
    signed_area,
    snap_to_distance,
    strip,
    symmetrize_loop,
)

# --- Parameters ---------------------------------------------------------------
HEIGHT_MM = 55.0           # mm, printed height of the coin (egg's long axis).
                           # Everything scales proportionally from the SVG
                           # design (223.52 mm tall, 16 mm thick), so at 55 mm
                           # the coin is ~3.94 mm thick with ~0.98 mm lips.
DESIGN_HEIGHT = 223.52     # mm, the SVG/GLB egg height (do not change)
FACE_T_BASE = 8.0          # mm at design size, face plate thickness
LIP_H_BASE = 4.0           # mm at design size, lip height per side
CHAMFER_ANGLE_DEG = 60.0   # deg, lip ramp angle from the face plane; equals the
                           # worst-case overhang-from-vertical when upright.
                           # <= 45 is guaranteed support-free (verified); 55
                           # printed clean; 60 in test; 90 = the original
                           # perfect extrusion (right-angle lips, full ceiling
                           # overhangs — the geometry this project set out to fix)
FLAT_BASE_MM = 0.0         # mm, shave this much off the egg's bottom for a flat
                           # stand (0 = faithful round bottom; ~0.3 gives an
                           # ~7 mm flat strip and a much safer first layer)
SPACING = 0.4              # mm in SVG units, outline sampling step (finer after scaling)
BED = (256.0, 256.0, 260.0)  # X2D single-nozzle envelope


# --- Build --------------------------------------------------------------------


def build(scale: float, chamfer_deg: float, flat_base: float) -> trimesh.Trimesh:
    loops = load_outlines(spacing=SPACING)
    # symmetrized so every version in this project shares one exact silhouette
    O, I, Do, H = (symmetrize_loop(loops[k] * scale) for k in ("O", "I", "Do", "H"))
    face_t, lip_h = FACE_T_BASE * scale, LIP_H_BASE * scale

    zf = face_t / 2.0          # face top
    zr = zf + lip_h            # rim top
    w = lip_h / np.tan(np.radians(chamfer_deg))  # chamfer horizontal run
    if w < 0.05:  # ~>= 89 deg: the true perfect extrusion, right-angle steps
        w = 0.0
        I_in, Do_out = I, Do
    else:
        # ramp toes, offset into the face; round joins merge the ramp correctly
        # across the star's narrow necks, then snap to exactly `w` from the
        # crease so the ramp surface is exactly planar at the requested angle
        I_in = snap_to_distance(buffer_loop(I, -w, SPACING), I, w)
        Do_out = snap_to_distance(buffer_loop(Do, +w, SPACING), Do, w)

    # the two ramp toes must not collide across the face annulus
    gap = loop_width_to(Do_out, I_in).min()
    assert gap > max(0.6, 2.0 * scale), f"chamfers overlap: face annulus min width {gap:.2f} mm"
    assert signed_area(I_in) > 0 and signed_area(Do_out) > 0

    patches = []
    ramps = []
    for s in (+1.0, -1.0):  # top face, bottom face (coin is symmetric)
        up = s > 0
        if w > 0:
            ramps += [
                band(I, I_in, I, s * zr, s * zf, w, up),        # egg lip ramp
                band(Do_out, Do, Do, s * zr, s * zf, w, up),    # diamond lip ramp
            ]
        else:  # original geometry: vertical step walls at the lip boundaries
            patches += [
                strip(lift(I, s * zf), lift(I, s * zr)),
                strip(lift(Do, s * zf), lift(Do, s * zr)),
            ]
        patches += [
            cap(O, [I], s * zr, up),          # egg rim top
            cap(Do, [H], s * zr, up),         # diamond rim top
            cap(I_in, [Do_out], s * zf, up),  # visible face
        ]
    patches += ramps

    # support-free guarantee: printed upright (design +Y becomes print +Z), a
    # ramp face's downward tilt from vertical is asin(-ny). Check every ramp
    # triangle against the requested chamfer angle.
    if ramps:
        worst = 0.0
        for r in ramps:
            ok = r.area_faces > 1e-9
            down = np.clip(-r.face_normals[ok, 1], 0.0, 1.0)
            worst = max(worst, float(np.degrees(np.arcsin(down)).max()))
        assert worst <= chamfer_deg + 2.0, f"ramp overhang {worst:.1f} deg > {chamfer_deg} deg"
        print(f"worst lip-ramp overhang when upright: {worst:.1f} deg (limit {chamfer_deg:g})")
    else:
        print("no chamfer: right-angle lips — full 90 deg ceilings when upright "
              "(the original extrusion geometry)")
    patches += [
        strip(lift(O, -zr), lift(O, +zr)),  # coin edge
        strip(lift(H, -zr), lift(H, +zr)),  # hole wall
    ]
    coin = assemble(patches, "coin_single")

    # stand it up: +90 deg about X maps design +Y (egg point) to world +Z
    coin.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])
    )
    coin.apply_translation([0, 0, -coin.bounds[0][2]])

    if flat_base > 0:
        coin = coin.slice_plane([0, 0, flat_base], [0, 0, 1], cap=True)
        coin.merge_vertices(digits_vertex=6)
        trimesh.repair.fix_normals(coin)
        coin.apply_translation([0, 0, -coin.bounds[0][2]])
    return coin


# --- Export + verify (the quality gate) ----------------------------------------


def export(mesh: trimesh.Trimesh, basename: str, scale: float) -> None:
    assert mesh.is_watertight, f"{basename}: not watertight"
    assert mesh.body_count == 1, f"{basename}: {mesh.body_count} bodies"
    e = mesh.extents
    # expected footprint from coin.svg's symmetric outline (REF_BBOX), scaled;
    # thickness = FACE_T + 2*LIP. width, thickness, egg-long-axis (upright: Z)
    exp = np.array([REF_BBOX[0], FACE_T_BASE + 2 * LIP_H_BASE, REF_BBOX[1]]) * scale
    assert np.allclose(e, exp, atol=max(1.0, FLAT_BASE_MM + 0.5)), f"{basename}: extents {e} != {exp}"
    assert all(e[i] <= BED[i] for i in range(3)), f"{basename}: exceeds bed {BED}"
    mesh.export(f"{basename}.stl")
    print(
        f"wrote {basename}.stl  bbox {e[0]:.2f} x {e[1]:.2f} x {e[2]:.2f} mm  "
        f"{mesh.volume / 1000:.1f} cm^3  watertight={mesh.is_watertight}"
    )


# --- Preview --------------------------------------------------------------------


def preview(mesh: trimesh.Trimesh, chamfer_deg: float, png: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    def shade(m, base=(1.0, 0.83, 0.45)):
        light = np.array([0.35, -0.5, 0.75])
        light = light / np.linalg.norm(light)
        lam = np.clip(m.face_normals @ light, 0, 1) * 0.7 + 0.3
        return np.column_stack([np.outer(lam, base), np.ones(len(lam))])

    # subdivide for display only: painter's-algorithm sorting needs small tris
    disp = mesh.copy()
    disp = trimesh.Trimesh(*trimesh.remesh.subdivide_to_size(disp.vertices, disp.faces, 6.0))

    fig = plt.figure(figsize=(16, 10))
    views = [(12, -90, "front (as printed, upright)"), (25, -55, "iso"), (8, -5, "edge-on")]
    for i, (elev, azim, title) in enumerate(views):
        ax = fig.add_subplot(2, 3, i + 1, projection="3d")
        ax.add_collection3d(
            Poly3DCollection(disp.vertices[disp.faces], facecolors=shade(disp), edgecolor="none")
        )
        c = disp.bounds.mean(axis=0)
        r = disp.extents.max() / 2
        ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(0, 2 * r)
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off(); ax.set_title(title, fontsize=10)

    # cross-sections: x=0 shows the whole profile + egg lip; an off-center cut
    # crosses the star's edges so the diamond lip chamfer is visible
    def section_segs(x_plane):
        sec = mesh.section(plane_origin=[x_plane, 0, 0], plane_normal=[1, 0, 0])
        return [] if sec is None else [sec.vertices[e.points][:, 1:] for e in sec.entities]

    h = mesh.extents[2]
    mid = section_segs(0.0)
    off = section_segs(-0.15 * mesh.extents[0])
    # diamond lip window: rim-height material (|thickness| ~ full) mid-print
    rim_pts = np.vstack([s for s in off]) if off else np.zeros((0, 2))
    m = (np.abs(rim_pts[:, 0]) > 0.49 * mesh.extents[1]) & (rim_pts[:, 1] > 0.15 * h) & (rim_pts[:, 1] < 0.85 * h)
    dwin = (rim_pts[m, 1].min() - 8, rim_pts[m, 1].max() + 8) if m.any() else (0.3 * h, 0.7 * h)
    panels = [
        (4, "full section (x=0)", mid, None),
        (5, "egg lip (top of print)", mid, (h - 32, h + 2)),
        (6, "diamond lip (off-center section)", off, dwin),
    ]
    for slot, title, segs, zwin in panels:
        ax = fig.add_subplot(2, 3, slot)
        for s in segs:
            ax.plot(s[:, 0], s[:, 1], "k-", lw=0.9)
        ax.set_aspect("equal")
        if zwin:
            ax.set_ylim(*zwin)
            ax.set_xlim(-1.4 * mesh.extents[1], 1.4 * mesh.extents[1])
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("thickness (mm)")
    fig.suptitle(
        f"coin_single — lips ramp at {chamfer_deg:g} deg from the face; prints upright"
        + (", support-free lips" if chamfer_deg <= 45 else " (past 45: slow overhangs)"),
        fontsize=12,
    )
    plt.tight_layout()
    plt.savefig(png, dpi=110)
    print(f"wrote {png}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--height", type=float, default=HEIGHT_MM, help="printed coin height, mm")
    ap.add_argument("--chamfer-angle", type=float, default=CHAMFER_ANGLE_DEG)
    ap.add_argument("--flat-base", type=float, default=FLAT_BASE_MM)
    ap.add_argument("--out", default="coin_single")
    args = ap.parse_args()
    assert 15.0 <= args.chamfer_angle <= 90.0, "chamfer angle must be 15..90 deg (90 = no chamfer)"
    if args.chamfer_angle > 45.0:
        print(f"note: {args.chamfer_angle:g} deg lip ramps exceed the 45 deg support-free "
              "guideline — keep overhang slowdown on (at 90 the lips are full ceilings)")

    import os

    os.makedirs("single", exist_ok=True)
    scale = args.height / DESIGN_HEIGHT
    m = build(scale, args.chamfer_angle, args.flat_base)
    export(m, f"single/{args.out}", scale)
    # "_design" suffix: verify-print-mesh writes <stl>_preview.png, keep both
    preview(m, args.chamfer_angle, f"single/{args.out}_design.png")
