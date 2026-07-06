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
"""Egg coin, two-color, GLUE version — textured faces, most seamless build.

Identical to coin_snap.py except for the star: here it is a glued base + cap
(seamless bore, BOTH star lips textured) instead of a snap-on ring.

Pieces (6 STLs; print face_half x2 = 6 printed pieces):
  - egg rim   (lip color, x1): monolithic teardrop-groove hoop — the coin's
    edge and both egg lips are one piece, zero seams. The glued face pair
    tire-mounts into its groove (proven assembly).
  - face half (face color, x2): textured slab, half the plate thickness, with
    a 45-deg lead-in bevel on its outer bed edge (the pair's tongue); SELF-
    MATING registration (integrated pegs at x>0, mirrored sockets at x<0 —
    a flipped copy plugs into itself, eight engagement points, no loose pegs).
    Both coin faces show bed texture; the halves' seam daylights nowhere.
  - star base (lip color, x1): bottom star lip + full-height hole tube in one
    piece — the hole bore and bottom lip are seamless and bed-textured. The
    face pair drops over the tube and rests on the lip.
  - star cap  (lip color, x1): the top star lip, a flat textured ring with a
    shallow rebate underneath that keys over the tube tip (self-centering).
    Its seams: the lip-base corner (hidden) and a hairline ring inside the
    hole bore ~0.7 mm below the top face.
  - face_solid (x1, ALTERNATIVE): full-thickness one-piece face, no pegs, no
    face glue — for lazy builds and fit testing. One of its sides is a
    print-top surface instead of bed texture.

Remaining non-textured visible surface: the TOP egg lip only (top-of-print;
use Monotonic, or ironing if it bothers).

Assembly: glue the face halves back-to-back (pegs self-align); drop the pair over the
star base tube (rests on the bottom star lip); glue the star cap onto the
tube tip and face; tire-mount the finished plate into the egg rim's groove
(hook the pointy end first), with a thin bead of CA in the groove if you
want it permanent.

Outlines are symmetrized about the egg's long axis (<= 0.08 mm) so the
flipped top half mates the bottom one exactly.

Run:  uv run coin_glue.py        # 6 STLs + preview
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

# egg rim groove (same proven numbers as coin_snap.py)
ENGAGE_EGG = 0.60      # mm face-pair tongue overlap into the egg groove
ROOT_CLR = 0.20        # mm extra groove depth past the tongue tip
CLR_Z = 0.15           # mm axial groove clearance over the pair thickness
GROOVE_LAND = 0.25     # mm flat groove mouth before the internal 45-deg chamfers
BEV = 0.5              # mm lead-in bevel on each face half's outer bed edge

# star base + cap
TUBE_W = 1.0           # mm hole-tube wall thickness
TUBE_CLR = 0.15        # mm radial clearance, face pair hole <-> tube
REBATE_D = 0.30        # mm the tube tip keys into the cap's underside
REBATE_CLR_R = 0.10    # mm radial clearance in the cap rebate
REBATE_CLR_Z = 0.05    # mm axial glue gap at the rebate root

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

    T = (FACE_T_BASE + 2 * LIP_H_BASE) * scale  # full coin thickness
    P = FACE_T_BASE * scale                     # face pair thickness
    half_t = P / 2                              # one face half
    lip = (T - P) / 2                           # lip protrusion above the face
    gh = P + CLR_Z                              # egg groove height
    gz0, gz1 = (T - gh) / 2, (T + gh) / 2
    tube_top = T - lip + REBATE_D               # star tube tip (keys into cap)

    # ---- egg rim: one-piece teardrop-groove hoop (edge + both lips seamless)
    G = buffer_loop(I, +(ENGAGE_EGG + ROOT_CLR), SPACING)  # groove root
    C = buffer_loop(I, +GROOVE_LAND, SPACING)              # chamfer start
    M = buffer_loop(I, -0.4, SPACING)                      # overshoot past wall
    cd = ENGAGE_EGG + ROOT_CLR - GROOVE_LAND
    egg_wall = loop_width_to(G, O).min()
    assert egg_wall >= MIN_WALL, f"egg rim wall {egg_wall:.2f} mm behind groove"
    groove_tool = assemble([
        cap(C, [M], gz1, True),
        band(G, C, C, gz1, gz1 - cd, cd, True),
        strip(lift(G, gz0 + cd), lift(G, gz1 - cd)),
        band(G, C, C, gz0, gz0 + cd, cd, False),
        cap(C, [M], gz0, False),
        strip(lift(M, gz0), lift(M, gz1)),
    ], "egg_groove_tool")
    egg_rim = difference(extrude_ring(O, [I], 0.0, T, "egg_raw"), [groove_tool])

    # ---- star base: bottom lip + full-height hole tube, one watertight piece
    Tt = buffer_loop(H, +TUBE_W, SPACING)
    star_bearing = loop_width_to(Tt, Do).min()  # ring the face pair rests on
    assert star_bearing >= 0.6, f"star lip bearing only {star_bearing:.2f} mm"
    star_base = assemble([
        cap(Do, [H], 0.0, False),                 # visible bottom lip (bed)
        strip(lift(Do, 0.0), lift(Do, lip)),      # lip outer wall
        cap(Do, [Tt], lip, True),                 # face-bearing ledge
        strip(lift(Tt, lip), lift(Tt, tube_top)),  # tube outer wall
        cap(Tt, [H], tube_top, True),             # tube tip
        strip(lift(H, 0.0), lift(H, tube_top)),   # seamless hole bore
    ], "star_base")

    # ---- star cap: flat top lip ring, rebated underside keys over the tube
    reb_tool = extrude_ring(
        buffer_loop(H, +(TUBE_W + REBATE_CLR_R), SPACING),
        [buffer_loop(H, -0.4, SPACING)],
        lip - (REBATE_D + REBATE_CLR_Z), lip + 0.5, "cap_rebate_tool",
    )
    star_cap = difference(extrude_ring(Do, [H], 0.0, lip, "cap_raw"), [reb_tool])
    assert lip - (REBATE_D + REBATE_CLR_Z) >= 0.55, "cap too thin over the rebate"

    # ---- face half: textured slab, beveled outer bed edge, blind peg sockets
    F = buffer_loop(I, +ENGAGE_EGG, SPACING)          # pair tongue boundary
    F_h = buffer_loop(H, +(TUBE_W + TUBE_CLR), SPACING)  # wraps the tube
    F_in = snap_to_distance(buffer_loop(F, -BEV, SPACING), F, BEV)
    face_solid_patches = [
        cap(F_in, [F_h], 0.0, False),                 # textured face (bed)
        band(F, F_in, F_in, 0.0, BEV, BEV, False),    # 45-deg tongue lead-in
        strip(lift(F, BEV), lift(F, half_t)),
        cap(F, [F_h], half_t, True),                  # glue face
        strip(lift(F_h, 0.0), lift(F_h, half_t)),
    ]
    face_solid_half = assemble(face_solid_patches, "face_half_raw")

    # self-mating registration: integrated pegs (x>0) + mirrored sockets (x<0)
    pegs, socket_cuts = mating_features(
        F, F_h, I, Do, half_t,
        peg_d=PEG_D, peg_clr=PEG_CLR, hole_comp=HOLE_COMP, floor=SOCKET_FLOOR)
    face_half = difference(union([face_solid_half] + pegs), socket_cuts)

    # ---- solid face: full plate thickness, no pegs — the lazy/testing option
    face_solid = assemble(
        [p for sgn in (+1.0, -1.0) for p in (
            cap(F_in, [F_h], sgn * P / 2, sgn > 0),
            band(F, F_in, F_in, sgn * P / 2, sgn * (P / 2 - BEV), BEV, sgn > 0),
        )] + [
            strip(lift(F, -(P / 2 - BEV)), lift(F, P / 2 - BEV)),
            strip(lift(F_h, -P / 2), lift(F_h, P / 2)),
        ], "face_solid")

    parts = {
        "egg_rim": egg_rim, "face_half": face_half, "face_solid": face_solid,
        "star_base": star_base, "star_cap": star_cap,
    }

    # ---- seated-assembly interference checks
    flip_y = trimesh.transformations.rotation_matrix(np.pi, [0, 1, 0])
    bot = face_half.copy(); bot.apply_translation([0, 0, lip])
    top = face_half.copy(); top.apply_transform(flip_y); top.apply_translation([0, 0, lip + P])
    capm = star_cap.copy(); capm.apply_transform(flip_y); capm.apply_translation([0, 0, T])
    solid = face_solid.copy(); solid.apply_translation([0, 0, T / 2])
    seated = {"egg_rim": egg_rim, "star_base": star_base, "star_cap": capm,
              "face_bot": bot, "face_top": top, "face_solid": solid}
    for a, b in [("face_bot", "egg_rim"), ("face_top", "egg_rim"),
                 ("face_bot", "star_base"), ("face_top", "star_base"),
                 ("star_cap", "star_base"), ("star_cap", "face_top"),
                 ("face_bot", "face_top"),
                 ("face_solid", "egg_rim"), ("face_solid", "star_base"),
                 ("face_solid", "star_cap")]:
        inter = trimesh.boolean.intersection([seated[a], seated[b]], engine=ENGINE)
        vol = 0.0 if inter.is_empty else abs(inter.volume)
        assert vol < 1e-3, f"{a} x {b} interfere: {vol:.3f} mm^3"

    print(
        f"coin {41.48 * height / 55:.1f} x {height:.1f} x {T:.2f} mm; "
        f"egg rim monolithic (groove engage {ENGAGE_EGG}, teardrop); "
        f"star tube Ø-wall {TUBE_W} mm to z={tube_top:.2f}, cap rebate {REBATE_D}+{REBATE_CLR_Z} mm; "
        f"face halves {half_t:.2f} mm, self-mating (4 pegs Ø{PEG_D} + 4 sockets each, 8 joints); "
        f"hole-bore seam {lip - REBATE_D:.2f} mm below top face"
    )
    return parts, dict(T=T, P=P, lip=lip, seated=seated)


# --- Export + verify ---------------------------------------------------------------
def export(parts: dict) -> None:
    import os

    os.makedirs("glue", exist_ok=True)
    counts = {"face_half": "x2",
              "face_solid": "x1 — lazy alternative to face_half x2"}
    for name, mesh in parts.items():
        m = mesh.copy()
        m.apply_translation([0, 0, -m.bounds[0][2]])
        assert m.is_watertight, f"{name}: not watertight"
        assert m.body_count == 1, f"{name}: {m.body_count} bodies"
        e = m.extents
        assert all(e[i] <= BED[i] for i in range(3)), f"{name}: exceeds bed"
        fn = f"glue/coin_glue_{name}.stl"
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
    # assembly orientations: star base tube-up, bottom face textured-down,
    # top face flipped (sockets down), cap flipped (visible face up)
    stack = [
        ("egg_rim", LIP_RGB, False, 0),
        ("star_base", LIP_RGB, False, 8),
        ("face_half", FACE_RGB, False, 18),
        ("face_half", FACE_RGB, True, 26),
        ("star_cap", LIP_RGB, True, 35),
    ]
    from coin_outlines import merged_shaded

    ax.add_collection3d(merged_shaded(
        [(positioned(parts[name], flip, dz), base) for name, base, flip, dz in stack]
    ))
    ax.set_xlim(-30, 30); ax.set_ylim(-30, 30); ax.set_zlim(-6, 54)
    ax.view_init(elev=20, azim=-65); ax.set_axis_off()
    ax.set_title("assembly stack: egg rim / star base / 2 face halves / star cap (+pegs)")

    ax = fig.add_subplot(1, 2, 2)
    colors = {"egg_rim": "#b8860b", "star_base": "#b8860b", "star_cap": "#7a5c0a",
              "face_bot": "#8a8265", "face_top": "#8a8265"}
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
    ax.set_title("assembled section through the pegs (x=0)")
    ax.set_xlabel("along the coin (mm)"); ax.set_ylabel("z (mm)")
    plt.tight_layout()
    plt.savefig(png, dpi=130)
    print(f"wrote {png}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--height", type=float, default=HEIGHT_MM)
    args = ap.parse_args()

    import os

    os.makedirs("glue", exist_ok=True)
    parts, geo = build(args.height)
    preview(parts, geo, "glue/coin_glue_design.png")
    export(parts)
