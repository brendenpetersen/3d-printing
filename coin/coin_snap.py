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
"""Egg coin, two-color, SNAP version — textured split face, no glue required.

Identical to coin_textured.py except for the star: here it is a one-piece
C-groove ring that SNAPS onto the face pair, instead of a glued base + cap.

Pieces (4 STLs; print face_half x2 = 5 printed pieces):
  - egg rim   (lip color, x1): monolithic teardrop-groove hoop — the coin's
    edge and both egg lips are seamless. The face pair tire-mounts into it.
  - star rim  (lip color, x1): monolithic teardrop-groove star — seamless
    hole bore and both star lips. Engages the face pair at its N/S knobs
    ONLY (0.3 mm), flanks relieved to a kiss fit: hook one knob tilted,
    cam the other over. (A closed star loop cannot shrink, so flank
    engagement would make assembly impossible — learned from prints 1-3.)
  - face half (face color, x2): textured slab, half the plate thickness;
    45-deg lead-in bevels on BOTH bed edges (outer tongue + hole tongue);
    SELF-MATING registration: integrated pegs at x>0, mirrored sockets at
    x<0, so a flipped copy of the same model plugs into itself (eight
    engagement points per joint, no loose pegs). Both faces bed-textured.
  - face_solid (x1, ALTERNATIVE): full-thickness one-piece face, no pegs, no
    glue — for lazy builds and fit testing. One of its sides is a print-top
    surface instead of bed texture; otherwise interchangeable with the pair.

The only glue is between the two face halves (their seam daylights nowhere —
it hides inside the grooves). Rim joints are dry snaps and stay serviceable.
Non-textured visible surfaces: one egg lip and one star lip (each rim is
symmetric — whichever lip faced up in printing; use Monotonic top surfaces).

Assembly: glue the face halves back-to-back (pegs self-align); snap the star rim on
FIRST (hook the north knob into the groove tilted, press the south home —
the plate must be unclamped so it can bow); then tire-mount the egg rim
(hook the pointy end first, work around to the fat end).

Outlines are symmetrized about the egg's long axis (<= 0.08 mm) so the
flipped top face half mates the bottom one exactly.

Run:  uv run coin_snap.py          # 4 STLs + preview
"""

from __future__ import annotations

import argparse

import numpy as np
import trimesh

from coin_outlines import (
    assemble,
    band,
    buffer_loop,
    cap,
    dist_to_polyline,
    lift,
    load_outlines,
    loop_width_to,
    mating_features,
    resample_loop,
    snap_to_distance,
    strip,
    symmetrize_loop,
)

# --- Parameters -----------------------------------------------------------------
HEIGHT_MM = 55.0       # mm printed coin height
DESIGN_HEIGHT = 223.52 # mm SVG design height (do not change)
FACE_T_BASE = 8.0      # mm at design size -> plate pair ~1.97 (halves 0.98)
LIP_H_BASE = 4.0       # mm at design size -> lips ~0.98 proud per side

# grooves (proven numbers)
ENGAGE_EGG = 0.60      # mm face-pair tongue overlap into the egg groove
ENGAGE_STAR = 0.30     # mm tongue overlap at the star's engaged knobs
                       # (0.20 seated but rattled and popped out; 2-knob
                       # insertion is one cam-over, so it tolerates more)
STAR_CLR_Z = 0.10      # mm axial groove clearance at the star (tighter than
                       # the egg's: only two knobs grip, so slack = rattle)
STAR_KNOBS = 2         # engage N/S knobs only: hook one, cam the other
STAR_KNOB_ARC = 1.8    # mm arc each side of a knob apex at full engagement
STAR_BLEND_ARC = 4.0   # mm arc where engagement fades to flank relief
STAR_FLANK_CLR = 0.05  # mm kiss-fit clearance along the star's flanks
ROOT_CLR = 0.20        # mm extra groove depth past the tongue tip
CLR_Z = 0.15           # mm axial groove clearance over the pair thickness
GROOVE_LAND = 0.25     # mm flat groove mouth before the internal 45-deg chamfers
BEV = 0.5              # mm lead-in bevel on each face half's bed edges

# self-mating face-half registration (integrated pegs + mirrored sockets)
PEG_D = 2.5            # mm peg diameter
PEG_CLR = 0.10         # mm diametral socket clearance; snug (0.05 = press fit)
HOLE_COMP = 0.2        # mm diametral FDM compensation on the sockets
SOCKET_FLOOR = 0.4     # mm left between socket bottom and the textured face

SPACING = 0.4          # mm in SVG units, outline sampling step
MIN_WALL = 0.9
BED = (256.0, 256.0, 260.0)
ENGINE = "manifold"


# --- Helpers ----------------------------------------------------------------------
def extrude_ring(outer, inners, z0, z1, name):
    patches = [cap(outer, inners, z0, z0 > z1), cap(outer, inners, z1, z1 > z0)]
    patches.append(strip(lift(outer, z0), lift(outer, z1)))
    for inn in inners:
        patches.append(strip(lift(inn, z0), lift(inn, z1)))
    return assemble(patches, name)


def difference(a, b_list):
    out = trimesh.boolean.difference([a] + b_list, engine=ENGINE)
    out.merge_vertices(digits_vertex=6)
    return out


def union(meshes):
    out = trimesh.boolean.union(meshes, engine=ENGINE)
    out.merge_vertices(digits_vertex=6)
    return out


# --- Build (print coords per piece: z = 0 is the bed = the VISIBLE surface) --------
def build(height: float):
    scale = height / DESIGN_HEIGHT
    L = load_outlines(spacing=SPACING)
    O, I, Do, H = (symmetrize_loop(L[k] * scale) for k in ("O", "I", "Do", "H"))

    T = (FACE_T_BASE + 2 * LIP_H_BASE) * scale
    P = FACE_T_BASE * scale
    half_t = P / 2
    lip = (T - P) / 2

    def teardrop_rim(outer, inner, wall, wall_sign, engage, clr_z, name):
        """One-piece rim with a self-supporting internal groove.
        wall_sign: +1 groove opens inward (egg), -1 opens outward (star)."""
        gh = P + clr_z
        gz0, gz1 = (T - gh) / 2, (T + gh) / 2
        root = buffer_loop(wall, wall_sign * (engage + ROOT_CLR), SPACING)
        land = buffer_loop(wall, wall_sign * GROOVE_LAND, SPACING)
        over = buffer_loop(wall, -wall_sign * 0.4, SPACING)
        cd = engage + ROOT_CLR - GROOVE_LAND
        out_l, in_l = (root, land) if wall_sign > 0 else (land, root)
        tool = assemble([
            cap(land, [over], gz1, True) if wall_sign > 0 else cap(over, [land], gz1, True),
            band(out_l, in_l, land, gz1, gz1 - cd, cd, True),
            strip(lift(root, gz0 + cd), lift(root, gz1 - cd)),
            band(out_l, in_l, land, gz0, gz0 + cd, cd, False),
            cap(land, [over], gz0, False) if wall_sign > 0 else cap(over, [land], gz0, False),
            strip(lift(over, gz0), lift(over, gz1)),
        ], f"{name}_tool")
        return difference(extrude_ring(outer, [inner], 0.0, T, f"{name}_raw"), [tool]), root

    egg_rim, G_e = teardrop_rim(O, I, I, +1, ENGAGE_EGG, CLR_Z, "egg")
    star_rim, G_s = teardrop_rim(Do, H, Do, -1, ENGAGE_STAR, STAR_CLR_Z, "star")
    egg_wall = loop_width_to(G_e, O).min()
    star_wall = loop_width_to(G_s, H).min()
    assert egg_wall >= MIN_WALL and star_wall >= MIN_WALL, "wall behind a groove too thin"

    # ---- face-pair tongue outlines
    F = buffer_loop(I, +ENGAGE_EGG, SPACING)  # outer tongue

    # star tongue: engaged only at STAR_KNOBS knobs, kiss fit along the flanks
    seg = np.linalg.norm(np.diff(np.vstack([Do, Do[:1]]), axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])[:-1]
    r = np.linalg.norm(Do - Do.mean(axis=0), axis=1)
    apex = []
    for i in np.argsort(-r):
        if all(min(abs(s[i] - s[j]), s[-1] + seg[-1] - abs(s[i] - s[j])) > s[-1] / 8
               for j in apex):
            apex.append(i)
        if len(apex) == 4:
            break
    apex = sorted(apex, key=lambda i: -abs(Do[i, 1]))[:STAR_KNOBS]  # N/S first
    arc = np.full(len(Do), np.inf)
    total = s[-1] + seg[-1]
    for j in apex:
        d = np.abs(s - s[j])
        arc = np.minimum(arc, np.minimum(d, total - d))
    t = np.clip((arc - STAR_KNOB_ARC) / (STAR_BLEND_ARC - STAR_KNOB_ARC), 0, 1)
    t = t * t * (3 - 2 * t)
    from scipy.spatial import cKDTree
    from shapely.geometry import Polygon

    eng = buffer_loop(Do, -ENGAGE_STAR, 0.1)
    rel = buffer_loop(Do, +STAR_FLANK_CLR, 0.1)
    p_eng = eng[cKDTree(eng).query(Do)[1]]
    p_rel = rel[cKDTree(rel).query(Do)[1]]
    B_h = resample_loop(p_eng * (1 - t)[:, None] + p_rel * t[:, None], len(Do))
    assert Polygon(B_h).is_valid, "blended star tongue outline self-intersects"

    # ---- face half: textured slab, beveled tongues on BOTH bed edges, sockets
    F_in = snap_to_distance(buffer_loop(F, -BEV, SPACING), F, BEV)
    B_h_in = snap_to_distance(buffer_loop(B_h, +BEV, SPACING), B_h, BEV)
    face_solid = assemble([
        cap(F_in, [B_h_in], 0.0, False),                # textured face (bed)
        band(F, F_in, F_in, 0.0, BEV, BEV, False),      # outer tongue lead-in
        band(B_h_in, B_h, B_h_in, 0.0, BEV, BEV, False),  # hole tongue lead-in
        strip(lift(F, BEV), lift(F, half_t)),
        cap(F, [B_h], half_t, True),                    # glue face
        strip(lift(B_h, BEV), lift(B_h, half_t)),
    ], "face_half_raw")

    # self-mating registration: integrated pegs (x>0) + mirrored sockets (x<0)
    pegs, socket_cuts = mating_features(
        F, B_h, I, Do, half_t,
        peg_d=PEG_D, peg_clr=PEG_CLR, hole_comp=HOLE_COMP, floor=SOCKET_FLOOR)
    face_half = difference(union([face_solid] + pegs), socket_cuts)

    # ---- solid face: full plate thickness, no pegs — the lazy/testing option
    # (one of its sides is a print-top surface instead of bed texture)
    face_solid = assemble(
        [p for sgn in (+1.0, -1.0) for p in (
            cap(F_in, [B_h_in], sgn * P / 2, sgn > 0),
            band(F, F_in, F_in, sgn * P / 2, sgn * (P / 2 - BEV), BEV, sgn > 0),
            band(B_h_in, B_h, B_h_in, sgn * P / 2, sgn * (P / 2 - BEV), BEV, sgn > 0),
        )] + [
            strip(lift(F, -(P / 2 - BEV)), lift(F, P / 2 - BEV)),
            strip(lift(B_h, -(P / 2 - BEV)), lift(B_h, P / 2 - BEV)),
        ], "face_solid")

    parts = {"egg_rim": egg_rim, "star_rim": star_rim, "face_half": face_half,
             "face_solid": face_solid}

    # ---- seated-assembly interference checks (pair centered in the grooves)
    flip_y = trimesh.transformations.rotation_matrix(np.pi, [0, 1, 0])
    bot = face_half.copy(); bot.apply_translation([0, 0, (T - P) / 2])
    top = face_half.copy(); top.apply_transform(flip_y)
    top.apply_translation([0, 0, (T - P) / 2 + P])
    solid = face_solid.copy(); solid.apply_translation([0, 0, T / 2])
    seated = {"egg_rim": egg_rim, "star_rim": star_rim, "face_bot": bot, "face_top": top,
              "face_solid": solid}
    for a, b in [("face_bot", "egg_rim"), ("face_top", "egg_rim"),
                 ("face_bot", "star_rim"), ("face_top", "star_rim"),
                 ("face_bot", "face_top"),
                 ("face_solid", "egg_rim"), ("face_solid", "star_rim")]:
        inter = trimesh.boolean.intersection([seated[a], seated[b]], engine=ENGINE)
        vol = 0.0 if inter.is_empty else abs(inter.volume)
        assert vol < 1e-3, f"{a} x {b} interfere: {vol:.3f} mm^3"

    print(
        f"coin {41.48 * height / 55:.1f} x {height:.1f} x {T:.2f} mm; "
        f"tongue engagement egg {ENGAGE_EGG} mm / star {ENGAGE_STAR} mm at {STAR_KNOBS} knobs "
        f"(flanks relieved {STAR_FLANK_CLR}, axial egg {CLR_Z} / star {STAR_CLR_Z}); "
        f"face halves {half_t:.2f} mm, "
        f"self-mating faces: 4 pegs Ø{PEG_D} + 4 mirrored sockets each (8 joints); "
        f"walls behind grooves egg {egg_wall:.2f} / star {star_wall:.2f} mm"
    )
    return parts, dict(T=T, seated=seated)


# --- Export + verify ---------------------------------------------------------------
def export(parts: dict) -> None:
    import os

    os.makedirs("snap", exist_ok=True)
    counts = {"face_half": "x2",
              "face_solid": "x1 — lazy alternative to face_half x2"}
    for name, mesh in parts.items():
        m = mesh.copy()
        m.apply_translation([0, 0, -m.bounds[0][2]])
        assert m.is_watertight, f"{name}: not watertight"
        assert m.body_count == 1, f"{name}: {m.body_count} bodies"
        e = m.extents
        assert all(e[i] <= BED[i] for i in range(3)), f"{name}: exceeds bed"
        fn = f"snap/coin_snap_{name}.stl"
        m.export(fn)
        print(f"wrote {fn}  bbox {e[0]:.2f} x {e[1]:.2f} x {e[2]:.2f} mm  (print {counts.get(name, 'x1')})")


# --- Preview -------------------------------------------------------------------------
LIP_RGB = (0.83, 0.62, 0.20)
FACE_RGB = (0.93, 0.89, 0.80)


def preview(parts, geo, png):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    light = np.array([0.35, -0.5, 0.75])
    light = light / np.linalg.norm(light)

    flip_y = trimesh.transformations.rotation_matrix(np.pi, [0, 1, 0])

    def positioned(m, flip, dz):
        mm = m.copy()
        if flip:
            mm.apply_transform(flip_y)
        mm.apply_translation([0, 0, dz - mm.bounds[0][2]])
        return mm

    fig = plt.figure(figsize=(16, 9))
    ax = fig.add_subplot(1, 2, 1, projection="3d")
    # assembly orientations: bottom face textured-down (sockets up), top face
    # flipped (sockets down), star rim snaps on last
    stack = [
        ("egg_rim", LIP_RGB, False, 0),
        ("face_half", FACE_RGB, False, 9),
        ("face_half", FACE_RGB, True, 17),
        ("star_rim", LIP_RGB, False, 26),
    ]
    from coin_outlines import merged_shaded

    ax.add_collection3d(merged_shaded(
        [(positioned(parts[name], flip, dz), base) for name, base, flip, dz in stack]
    ))
    ax.set_xlim(-30, 30); ax.set_ylim(-30, 30); ax.set_zlim(-6, 46)
    ax.view_init(elev=20, azim=-65); ax.set_axis_off()
    ax.set_title("snap version: egg rim / star rim / 2 self-mating face halves; no glue to rims")

    ax = fig.add_subplot(1, 2, 2)
    colors = {"egg_rim": "#b8860b", "star_rim": "#b8860b", "face_bot": "#8a8265", "face_top": "#8a8265"}
    for name, m in geo["seated"].items():
        if name not in colors:  # face_solid duplicates the pair in section
            continue
        sec = m.section(plane_origin=[0, 0, 0], plane_normal=[1, 0, 0])
        if sec is None:
            continue
        for ent in sec.entities:
            p = sec.vertices[ent.points]
            ax.plot(p[:, 1], p[:, 2], "-", color=colors[name], lw=1.1)
    ax.set_aspect("equal"); ax.grid(alpha=0.25)
    ax.set_title("assembled section (x=0, through pegs and the N/S star knobs)")
    ax.set_xlabel("along the coin (mm)"); ax.set_ylabel("z (mm)")
    plt.tight_layout()
    plt.savefig(png, dpi=130)
    print(f"wrote {png}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--height", type=float, default=HEIGHT_MM)
    args = ap.parse_args()

    import os

    os.makedirs("snap", exist_ok=True)
    parts, geo = build(args.height)
    preview(parts, geo, "snap/coin_snap_design.png")
    export(parts)
