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
"""Egg coin, two-color, SANDWICH version — no glue anywhere, fully reversible.

The user's trapped-flange design, v2 (v1 had a lip that overlapped the face
and was geometrically unassemblable — the flange could never reach the far
side of its hole without snapping through):

The face hole is slightly LARGER than the star lip, so each star half drops
lip-first through it with zero force; a thin base flange (wider than the
hole) catches in a recess on the face half's interior side. The two pairs
close back-to-back and the egg rim's groove clamps the whole stack.

The one visible artifact this buys: a tight HAIRLINE CLEARANCE RING around
each star lip on the faces (the lip passes through the hole instead of
overlapping it). At LIP_CLR 0.02 mm it's a snug shove fit with no rattle.

Pieces (3 STLs; face_half and star_half print x2 = 5 printed pieces):
  - egg rim   (lip color, x1): monolithic teardrop-groove hoop — identical
    geometry to coin_snap.py's (reuse a printed one).
  - face half (face color, x2): textured slab, half the plate thickness;
    45-deg lead-in bevel on the outer bed edge; hole sized just over the
    star lip; flange recess around the hole on the interior face; SELF-
    MATING registration — integrated pegs at x>0, mirrored sockets at x<0,
    so a flipped copy of the same model plugs into itself (eight engagement
    points per joint, no loose pegs).
  - star half (lip color, x2): the star lip body (full lip footprint,
    passes through the face hole) with a thin base flange at its mid-plane
    end. Exported BRIM-UP: the visible lip face prints on the bed (bed
    texture, matching the coin faces); the flange is a small ~0.6 mm
    overhang ring that prints clean and hides inside the recess.

Assembly: face half textured-side down (recess up); drop a star half in
lip-first — the flange lands in the recess; same for the second pair; press
the pairs together (pegs seat in the mirrored sockets); tire-mount the egg
rim. Disassembles in reverse; every piece reusable; no glue, no snap forces.

Run:  uv run coin_sandwich.py        # 3 STLs + preview
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
    lift,
    load_outlines,
    loop_width_to,
    mating_features,
    snap_to_distance,
    strip,
    symmetrize_loop,
)

# --- Parameters -----------------------------------------------------------------
HEIGHT_MM = 55.0       # mm printed coin height
DESIGN_HEIGHT = 223.52 # mm SVG design height (do not change)
FACE_T_BASE = 8.0      # mm at design size -> plate pair ~1.97 (halves 0.98)
LIP_H_BASE = 4.0       # mm at design size -> lips ~0.98 proud per side

# egg rim groove — identical to coin_snap.py (a printed snap egg rim fits)
ENGAGE_EGG = 0.60
ROOT_CLR = 0.20
CLR_Z = 0.15
GROOVE_LAND = 0.25
BEV = 0.5              # mm lead-in bevel on each face half's outer bed edge

# star lip-through fit + trapped flange
LIP_CLR = 0.02         # mm radial gap, star lip <-> face hole. On this
                       # printer 0.08 fell in freely (low shrink), so 0.02
                       # drawn is ~zero effective clearance = snug shove fit,
                       # no rattle. This is the floor before crack risk: the
                       # lip passes THROUGH the hole and the face's 4 star
                       # points are the thinnest feature. 0.00 = light press
                       # (watch those points for whitening); avoid negative.
CATCH = 0.60           # mm the flange overlaps the recess ledge past the hole
BRIM_T = 0.40          # mm flange thickness (prints crisp: it's on the bed)
RECESS_CLR_Z = 0.05    # mm axial play, flange in recess
RECESS_CLR_R = 0.15    # mm radial clearance, flange edge <-> recess wall

# self-mating face-half registration (integrated pegs + mirrored sockets)
PEG_D = 2.5
PEG_CLR = 0.10         # mm diametral socket clearance; 0.15 was a loose slip,
                       # 0.10 is snug (drop to 0.05 for a press fit)
HOLE_COMP = 0.2
SOCKET_FLOOR = 0.4

SPACING = 0.4
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


# --- Build (print coords per piece: z = 0 on the bed) -------------------------------
def build(height: float):
    scale = height / DESIGN_HEIGHT
    L = load_outlines(spacing=SPACING)
    O, I, Do, H = (symmetrize_loop(L[k] * scale) for k in ("O", "I", "Do", "H"))

    T = (FACE_T_BASE + 2 * LIP_H_BASE) * scale
    P = FACE_T_BASE * scale
    half_t = P / 2                    # one face half
    lip = (T - P) / 2                 # lip protrusion above the face
    half_h = T / 2                    # star half total height
    gh = P + CLR_Z
    gz0, gz1 = (T - gh) / 2, (T + gh) / 2

    # ---- egg rim: identical construction to coin_snap.py
    G = buffer_loop(I, +(ENGAGE_EGG + ROOT_CLR), SPACING)
    C = buffer_loop(I, +GROOVE_LAND, SPACING)
    M = buffer_loop(I, -0.4, SPACING)
    cd = ENGAGE_EGG + ROOT_CLR - GROOVE_LAND
    assert loop_width_to(G, O).min() >= MIN_WALL
    groove_tool = assemble([
        cap(C, [M], gz1, True),
        band(G, C, C, gz1, gz1 - cd, cd, True),
        strip(lift(G, gz0 + cd), lift(G, gz1 - cd)),
        band(G, C, C, gz0, gz0 + cd, cd, False),
        cap(C, [M], gz0, False),
        strip(lift(M, gz0), lift(M, gz1)),
    ], "egg_groove_tool")
    egg_rim = difference(extrude_ring(O, [I], 0.0, T, "egg_raw"), [groove_tool])

    # ---- star half: lip body + base flange (built flange-at-z0; export()
    # flips it brim-up so the lip face lands on the textured bed)
    B_h = buffer_loop(Do, +LIP_CLR, SPACING)                 # face hole (> lip)
    Br = buffer_loop(Do, +(LIP_CLR + CATCH), SPACING)        # flange edge
    R_out = buffer_loop(Do, +(LIP_CLR + CATCH + RECESS_CLR_R), SPACING)  # recess wall
    star_half = assemble([
        cap(Br, [H], 0.0, False),                    # flange face (bed; mid-plane)
        strip(lift(Br, 0.0), lift(Br, BRIM_T)),      # flange edge
        cap(Br, [Do], BRIM_T, True),                 # catch face (bears on recess)
        strip(lift(Do, BRIM_T), lift(Do, half_h)),   # lip wall (through the hole)
        cap(Do, [H], half_h, True),                  # visible lip face (bed after flip)
        strip(lift(H, 0.0), lift(H, half_h)),        # bore
    ], "star_half")

    # ---- face half: textured slab + beveled outer tongue + flange recess + sockets
    F = buffer_loop(I, +ENGAGE_EGG, SPACING)
    F_in = snap_to_distance(buffer_loop(F, -BEV, SPACING), F, BEV)
    face_solid = assemble([
        cap(F_in, [B_h], 0.0, False),                # textured face (bed)
        band(F, F_in, F_in, 0.0, BEV, BEV, False),   # outer tongue lead-in
        strip(lift(F, BEV), lift(F, half_t)),
        cap(F, [B_h], half_t, True),                 # interior face
        strip(lift(B_h, 0.0), lift(B_h, half_t)),    # hole wall (the hairline ring)
    ], "face_half_raw")

    recess_d = BRIM_T + RECESS_CLR_Z
    assert half_t - recess_d >= 0.5, "recess floor too thin over the textured face"
    recess_tool = extrude_ring(
        R_out, [buffer_loop(Do, -0.3, SPACING)],
        half_t - recess_d, half_t + 0.5, "recess_tool",
    )

    # self-mating registration: integrated pegs (x>0) + mirrored sockets (x<0)
    pegs, socket_cuts = mating_features(
        F, R_out, I, Do, half_t,
        peg_d=PEG_D, peg_clr=PEG_CLR, hole_comp=HOLE_COMP, floor=SOCKET_FLOOR)
    face_half = difference(union([face_solid] + pegs), [recess_tool] + socket_cuts)

    parts = {"egg_rim": egg_rim, "face_half": face_half, "star_half": star_half}

    # ---- seated-assembly interference checks (assembly reachability is by
    # construction this time: lip < hole < flange, nothing ever interferes)
    flip_y = trimesh.transformations.rotation_matrix(np.pi, [0, 1, 0])

    def seat(m, flip, dz):
        c = m.copy()
        if flip:
            c.apply_transform(flip_y)
        c.apply_translation([0, 0, dz - c.bounds[0][2]])
        return c

    # faces are positioned by their textured plane, NOT by bounds — the pegs
    # protrude past the body, so a bounds-drop would seat them 0.48 too high
    face_bot = face_half.copy()
    face_bot.apply_translation([0, 0, lip])
    face_top = face_half.copy()
    face_top.apply_transform(flip_y)
    face_top.apply_translation([0, 0, lip + P])
    seated = {
        "egg_rim": seat(egg_rim, False, 0.0),
        "star_bot": seat(star_half, True, 0.0),        # lip down at the coin face
        "star_top": seat(star_half, False, half_h),    # lip up
        "face_bot": face_bot,                          # textured down, recess up
        "face_top": face_top,                          # textured up, pegs down
    }
    for a, b in [("face_bot", "egg_rim"), ("face_top", "egg_rim"),
                 ("face_bot", "star_bot"), ("face_top", "star_top"),
                 ("face_bot", "star_top"), ("face_top", "star_bot"),
                 ("star_bot", "star_top"), ("face_bot", "face_top"),
                 ("star_bot", "egg_rim"), ("star_top", "egg_rim")]:
        inter = trimesh.boolean.intersection([seated[a], seated[b]], engine=ENGINE)
        vol = 0.0 if inter.is_empty else abs(inter.volume)
        assert vol < 1e-3, f"{a} x {b} interfere: {vol:.3f} mm^3"

    print(
        f"coin {41.48 * height / 55:.1f} x {height:.1f} x {T:.2f} mm; "
        f"egg rim identical to coin_snap.py's; star lip drops through the hole "
        f"(hairline ring {LIP_CLR} mm), flange {CATCH} mm past the hole x {BRIM_T} mm "
        f"in a {recess_d:.2f} mm recess (floor {half_t - recess_d:.2f} mm); "
        f"self-mating faces: 4 pegs Ø{PEG_D} + 4 mirrored sockets each (8 joints); "
        f"no glue: clamp = egg groove on the {P:.2f} mm pair"
    )
    return parts, dict(T=T, seated=seated)


# --- Export + verify ---------------------------------------------------------------
def export(parts: dict) -> None:
    import os

    os.makedirs("sandwich", exist_ok=True)
    counts = {"face_half": "x2", "star_half": "x2"}
    for name, mesh in parts.items():
        m = mesh.copy()
        if name == "star_half":
            # export BRIM-UP: puts the visible lip face on the bed (bed texture,
            # matching the coin faces); the flange becomes a small ~0.6 mm
            # overhang ring that prints clean and hides inside the recess.
            m.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
        m.apply_translation([0, 0, -m.bounds[0][2]])
        assert m.is_watertight, f"{name}: not watertight"
        assert m.body_count == 1, f"{name}: {m.body_count} bodies"
        e = m.extents
        assert all(e[i] <= BED[i] for i in range(3)), f"{name}: exceeds bed"
        fn = f"sandwich/coin_sandwich_{name}.stl"
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
    # true assembly order, bottom to top, in assembly orientations:
    # egg rim / bottom face (textured down, recess+pegs up) / bottom star
    # (lip down, dropping through) / top star (lip up) / top face (flipped:
    # textured up, pegs DOWN)
    stack = [
        ("egg_rim", LIP_RGB, False, 0),
        ("face_half", FACE_RGB, False, 9),
        ("star_half", LIP_RGB, True, 17),
        ("star_half", LIP_RGB, False, 27),
        ("face_half", FACE_RGB, True, 37),
    ]
    from coin_outlines import merged_shaded

    ax.add_collection3d(merged_shaded(
        [(positioned(parts[name], flip, dz), base) for name, base, flip, dz in stack]
    ))
    ax.set_xlim(-30, 30); ax.set_ylim(-30, 30); ax.set_zlim(-4, 52)
    ax.view_init(elev=18, azim=-65); ax.set_axis_off()
    ax.set_title("assembly order, correct orientations: egg rim / face (recess up) / "
                 "star (lip down) / star (lip up) / face (pegs down)")

    ax = fig.add_subplot(1, 2, 2)
    colors = {"egg_rim": "#b8860b", "star_bot": "#b8860b", "star_top": "#7a5c0a",
              "face_bot": "#8a8265", "face_top": "#8a8265"}
    for name, m in geo["seated"].items():
        sec = m.section(plane_origin=[0, 0, 0], plane_normal=[1, 0, 0])
        if sec is None:
            continue
        for ent in sec.entities:
            p = sec.vertices[ent.points]
            ax.plot(p[:, 1], p[:, 2], "-", color=colors[name], lw=1.1)
    ax.set_aspect("equal"); ax.grid(alpha=0.25)
    ax.set_title("assembled section (x=0): lips through the holes, flanges in recesses")
    ax.set_xlabel("along the coin (mm)"); ax.set_ylabel("z (mm)")
    plt.tight_layout()
    plt.savefig(png, dpi=130)
    print(f"wrote {png}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--height", type=float, default=HEIGHT_MM)
    args = ap.parse_args()

    import os

    os.makedirs("sandwich", exist_ok=True)
    parts, geo = build(args.height)
    preview(parts, geo, "sandwich/coin_sandwich_design.png")
    export(parts)
