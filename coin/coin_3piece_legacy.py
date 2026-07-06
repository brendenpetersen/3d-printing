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
"""LEGACY (3-piece, solid one-piece face) — superseded by coin_snap.py (snap,
split textured face) and coin_textured.py (glue, capped star). Kept for the
smallest piece count; the solid face means neither of its sides is bed-
textured on top AND bottom, and the gluefit mode leaves back-side seam rings.

Egg coin, two-color, 3 pieces, groove fit — sized for a 55 mm coin.

Three physical pieces, no fasteners, no visible mechanism:
  1. face      (face color) — the egg plate; its edges carry a hidden tongue
  2. egg rim   (lip color)  — full-thickness outer hoop, internal groove
  3. star rim  (lip color)  — full-thickness star, external groove

Mechanism (per the user's sketch): each rim has a groove at mid-thickness;
the face plate's edge tongue snaps into it.
  - The egg hoop mounts like a tire: hook one end of the plate into the
    groove, then work the hoop around — the hoop ovalizes elastically
    (~0.5-1% strain in PLA at this size).
  - The star engages at its 4 KNOBS ONLY. A closed star loop cannot shrink:
    pressing knobs inward bulges the concave flanks outward, so any flank
    interference makes assembly impossible (print #1 proved it). The plate's
    hole is therefore relieved to a kiss fit along the flanks and tucks into
    the groove only at the knobs — insertion is four small cam-overs (tilt a
    knob in first, the plate bows slightly for the rest).
  - Assemble the STAR FIRST, then the egg hoop: the plate must be unclamped
    at its rim so it can bow out of plane while the knobs pass.
  - The plate's tongue edges are beveled top and bottom (hidden inside the
    grooves) as the lead-in that converts push into flex.

Because every piece prints FLAT, the lips keep the original crisp right
angles — no chamfer compromise needed on this version. The assembled coin
reproduces the TinkerCAD original exactly (plus fit clearances).

Print orientation (as exported): all three parts flat on the bed. The grooves
are small internal side-wall slots (0.6-0.8 mm bridges) — no supports.

Glue mode (--joint glue): same three pieces, but each closed groove becomes an
open rabbet (ledge) — the face drops in from the back with ZERO force and is
glued on the ledge (CA, ~0.1 mm glue gap built in). Foolproof assembly; the
front face is identical to the original design; the back shows a hairline
flush seam ring at each lip base. Exported with the visible (front) face on
the bed. Use this if the snap fit prints too tight.

Run:  uv run coin_3piece_legacy.py                  # snap fit, 3 STLs + preview
      uv run coin_3piece_legacy.py --joint glue     # drop-in glue version
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
    snap_to_distance,
    strip,
)

# --- Parameters -----------------------------------------------------------------
HEIGHT_MM = 55.0       # mm printed coin height; everything else scales from the
DESIGN_HEIGHT = 223.52 # mm SVG design height (do not change)
FACE_T_BASE = 8.0      # mm at design size -> ~1.97 at 55 mm
LIP_H_BASE = 4.0       # mm at design size -> ~0.98 at 55 mm (per side)

ENGAGE_EGG = 0.60      # mm tongue overlap into the egg rim's groove (drawn;
                       # prints ~0.1 tighter — raise/lower to firm/ease the snap)
ENGAGE_STAR = 0.20     # mm tongue overlap into the star rim's groove — applied
                       # ONLY at the 4 knobs (see below); the star is a closed
                       # loop, so its concave flanks cannot deflect: engaging
                       # them makes assembly impossible (learned from print #1)
STAR_KNOBS = 2         # how many knobs engage (2 = N/S only: hook one tilted,
                       # cam the other over — no simultaneous E/W squeeze)
STAR_KNOB_ARC = 1.8    # mm of arc each side of a knob apex at full engagement
STAR_BLEND_ARC = 4.0   # mm of arc where engagement has faded to flank relief
STAR_FLANK_CLR = 0.05  # mm clearance between plate hole and star wall on the
                       # flanks (kiss fit: invisible, but no interference)
ROOT_CLR = 0.20        # mm extra groove depth past the tongue tip
CLR_R = ROOT_CLR       # kept for the glue mode's tongue sizing
CLR_Z = 0.15           # mm axial clearance, plate <-> groove height (FDM slots
                       # print ~a layer short; 0.10 measured too tight)
GROOVE_LAND = 0.25     # mm flat groove mouth before the internal 45-deg
                       # chamfers begin — the chamfers make the groove ceiling
                       # self-supporting (a flat ceiling ring drapes loops into
                       # the slot; measured on the first print)
BEV = 0.5              # mm tongue lead-in bevel on the plate edges (per face)
MIN_WALL = 0.9         # mm minimum wall left behind any groove
SPACING = 0.4          # mm in SVG units, outline sampling step

BED = (256.0, 256.0, 260.0)
ENGINE = "manifold"


# --- Helpers ----------------------------------------------------------------------
def extrude_ring(outer, inners, z0, z1, name):
    patches = [cap(outer, inners, z0, z0 > z1), cap(outer, inners, z1, z1 > z0)]
    patches.append(strip(lift(outer, z0), lift(outer, z1)))
    for inn in inners:
        patches.append(strip(lift(inn, z0), lift(inn, z1)))
    return assemble(patches, name)


def difference(a, b):
    out = trimesh.boolean.difference([a, b], engine=ENGINE)
    out.merge_vertices(digits_vertex=6)
    return out


# --- Build ---------------------------------------------------------------------------
def build(height: float, joint: str = "snap"):
    scale = height / DESIGN_HEIGHT
    L = load_outlines(spacing=SPACING)
    from coin_outlines import symmetrize_loop
    O, I, Do, H = (symmetrize_loop(L[k] * scale) for k in ("O", "I", "Do", "H"))

    T = (FACE_T_BASE + 2 * LIP_H_BASE) * scale   # full coin thickness
    P = FACE_T_BASE * scale                      # plate thickness
    gh = P + CLR_Z                               # groove height
    gz0, gz1 = (T - gh) / 2, (T + gh) / 2
    lip_land = gz0                               # rim material above/below groove
    assert lip_land >= 0.7, f"groove lips only {lip_land:.2f} mm tall — coin too thin"
    assert P - 2 * BEV >= 0.7, "tongue tip too thin — reduce BEV or raise height"

    # groove root curves and the plate's tongue boundaries
    G_e = buffer_loop(I, +(ENGAGE_EGG + ROOT_CLR), SPACING)   # into the egg rim
    G_s = buffer_loop(Do, -(ENGAGE_STAR + ROOT_CLR), SPACING)  # into the star rim
    B_o = buffer_loop(I, +ENGAGE_EGG, SPACING)    # plate outer edge
    if joint == "snap":
        # knob-only star tongue: full engagement over +-STAR_KNOB_ARC of each
        # knob apex, fading to a kiss fit (-STAR_FLANK_CLR) along the concave
        # flanks, which cannot deflect and must never interfere
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
        # engage only the chosen knobs, N/S first (largest |y|)
        apex = sorted(apex, key=lambda i: -abs(Do[i, 1]))[:STAR_KNOBS]
        arc = np.full(len(Do), np.inf)
        total = s[-1] + seg[-1]
        for j in apex:
            d = np.abs(s - s[j])
            arc = np.minimum(arc, np.minimum(d, total - d))
        t = np.clip((arc - STAR_KNOB_ARC) / (STAR_BLEND_ARC - STAR_KNOB_ARC), 0, 1)
        t = t * t * (3 - 2 * t)  # smoothstep
        # blend between two clean buffer outlines (engaged / relieved) instead
        # of a raw variable offset — dense miter offsets wrinkle at knob tips
        from scipy.spatial import cKDTree
        from shapely.geometry import Polygon

        eng = buffer_loop(Do, -ENGAGE_STAR, 0.1)
        rel = buffer_loop(Do, +STAR_FLANK_CLR, 0.1)
        p_eng = eng[cKDTree(eng).query(Do)[1]]
        p_rel = rel[cKDTree(rel).query(Do)[1]]
        B_h = p_eng * (1 - t)[:, None] + p_rel * t[:, None]
        # nearest-vertex snapping leaves duplicate/jittery points that crash
        # the triangulators — clean up with an even-arclength resample
        from coin_outlines import resample_loop

        B_h = resample_loop(B_h, len(Do))
        assert Polygon(B_h).is_valid, "blended star tongue outline self-intersects"
    else:
        B_h = buffer_loop(Do, -ENGAGE_STAR, SPACING)  # glue: uniform, drop-in
    # the tongue's full-thickness zone must sit within the groove's flat mouth
    assert GROOVE_LAND >= max(ENGAGE_EGG, ENGAGE_STAR) - BEV + 0.05

    # walls left behind the grooves must stay printable
    egg_wall = loop_width_to(G_e, O).min()
    star_wall = loop_width_to(G_s, H).min()
    assert egg_wall >= MIN_WALL, f"egg rim outer wall {egg_wall:.2f} mm < {MIN_WALL}"
    assert star_wall >= MIN_WALL, f"star rim inner wall {star_wall:.2f} mm < {MIN_WALL}"

    # ---- rims: full-thickness extrusions, mating wall cut per joint style:
    # snap -> closed groove at mid-thickness; glue -> open rabbet (drop-in)
    def teardrop_groove(root, wall_sign, wall, over, engage, name):
        """Groove cutter with 45-deg internal chamfers on ceiling AND floor.

        A flat groove ceiling is a closed-loop bridge ring — FDM drapes loops
        into the slot (they peel out, and block the tongue). Chamfering from
        GROOVE_LAND past the mouth makes every layer of the ceiling a <= one
        line-width overhang on the loop below, so the slot prints clean.
        wall_sign: +1 groove opens inward (egg rim), -1 opens outward (star).
        """
        cd = engage + ROOT_CLR - GROOVE_LAND  # chamfer run == rise (45 deg)
        land = buffer_loop(wall, wall_sign * GROOVE_LAND, SPACING)
        outer, inner = (root, land) if wall_sign > 0 else (land, root)
        patches = [
            cap(land, [over], gz1, True) if wall_sign > 0 else cap(over, [land], gz1, True),
            band(outer, inner, land, gz1, gz1 - cd, cd, True),
            strip(lift(root, gz0 + cd), lift(root, gz1 - cd)),
            band(outer, inner, land, gz0, gz0 + cd, cd, False),
            cap(land, [over], gz0, False) if wall_sign > 0 else cap(over, [land], gz0, False),
            strip(lift(over, gz0), lift(over, gz1)),
        ]
        return assemble(patches, name)

    M_e = buffer_loop(I, -0.4, SPACING)   # overshoot past the egg rim's wall
    M_s = buffer_loop(Do, +0.4, SPACING)  # overshoot past the star rim's wall
    if joint == "snap":
        egg_tool = teardrop_groove(G_e, +1, I, M_e, ENGAGE_EGG, "egg_tool")
        star_tool = teardrop_groove(G_s, -1, Do, M_s, ENGAGE_STAR, "star_tool")
    else:
        # glue rabbets are open to the back and print front-face-down, so the
        # ledge is a plain top surface — no bridge problem, keep them square
        egg_tool = extrude_ring(G_e, [M_e], -0.5, gz1, "egg_tool")
        star_tool = extrude_ring(M_s, [G_s], -0.5, gz1, "star_tool")

    egg_rim = difference(extrude_ring(O, [I], 0.0, T, "egg_rim_raw"), egg_tool)
    star_rim = difference(extrude_ring(Do, [H], 0.0, T, "star_rim_raw"), star_tool)

    if joint == "snap":
        # ---- face plate: flat field, beveled tongue edges (centered, then lifted)
        B_oi = snap_to_distance(buffer_loop(B_o, -BEV, SPACING), B_o, BEV)
        B_hi = snap_to_distance(buffer_loop(B_h, +BEV, SPACING), B_h, BEV)
        patches = []
        for s in (+1.0, -1.0):
            up = s > 0
            zf, zt = s * P / 2, s * (P / 2 - BEV)
            patches += [
                cap(B_oi, [B_hi], zf, up),
                band(B_o, B_oi, B_oi, zf, zt, BEV, up),   # outer tongue bevel
                band(B_hi, B_h, B_hi, zf, zt, BEV, up),   # hole tongue bevel
            ]
        patches += [
            strip(lift(B_o, -(P / 2 - BEV)), lift(B_o, P / 2 - BEV)),
            strip(lift(B_h, -(P / 2 - BEV)), lift(B_h, P / 2 - BEV)),
        ]
        face = assemble(patches, "face")
        face.apply_translation([0, 0, T / 2])  # assembly position: centered in grooves
    else:
        # ---- face plate, drop-in: flat front seats against the ledge (glue gap
        # CLR_Z); the tongue rings extend to the back plane, flush with the rims
        S_o = buffer_loop(I, +CLR_R, SPACING)    # step, clears the egg rim wall
        S_h = buffer_loop(Do, +CLR_R, SPACING)   # step, clears the star rim wall
        z_front = gz1 - CLR_Z
        z_field = z_front - P
        patches = [
            cap(B_o, [B_h], z_front, True),      # the visible face (front)
            cap(B_o, [S_o], 0.0, False),         # outer tongue, flush with back
            cap(S_o, [S_h], z_field, False),     # recessed field back
            cap(S_h, [B_h], 0.0, False),         # hole tongue, flush with back
            strip(lift(B_o, 0.0), lift(B_o, z_front)),
            strip(lift(S_o, 0.0), lift(S_o, z_field)),
            strip(lift(S_h, 0.0), lift(S_h, z_field)),
            strip(lift(B_h, 0.0), lift(B_h, z_front)),
        ]
        face = assemble(patches, "face")  # already in assembly position

    parts = {"face": face, "egg_rim": egg_rim, "star_rim": star_rim}

    # ---- seated assembly must not interfere
    for a, b in [("face", "egg_rim"), ("face", "star_rim")]:
        inter = trimesh.boolean.intersection([parts[a], parts[b]], engine=ENGINE)
        vol = 0.0 if inter.is_empty else abs(inter.volume)
        assert vol < 1e-3, f"{a} x {b} interfere: {vol:.3f} mm^3"

    kind = "groove" if joint == "snap" else "rabbet ledge"
    star_note = (
        f"star {ENGAGE_STAR:.2f} mm at {STAR_KNOBS} knobs only (flanks relieved {STAR_FLANK_CLR:.2f})"
        if joint == "snap" else f"star {ENGAGE_STAR:.2f} mm"
    )
    print(
        f"[{joint}] coin {41.48 * height / 55:.1f} x {height:.1f} x {T:.2f} mm, plate {P:.2f} mm; "
        f"tongue engagement egg {ENGAGE_EGG:.2f} mm / {star_note} on the {kind}, "
        f"axial clearance {CLR_Z:.2f} mm, groove mouth land {GROOVE_LAND:.2f} mm, "
        f"walls behind cuts egg {egg_wall:.2f} / star {star_wall:.2f} mm"
    )
    return parts, dict(T=T, P=P, gz0=gz0, gz1=gz1, scale=scale, I=I, Do=Do, O=O, H=H)


# --- Export + verify --------------------------------------------------------------
def export(parts: dict, prefix: str, flip: bool) -> None:
    for name, mesh in parts.items():
        m = mesh.copy()
        if flip:  # glue mode: visible front face goes down on the bed
            m.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
        m.apply_translation([0, 0, -m.bounds[0][2]])
        assert m.is_watertight, f"{name}: not watertight"
        assert m.body_count == 1, f"{name}: {m.body_count} bodies"
        e = m.extents
        assert all(e[i] <= BED[i] for i in range(3)), f"{name}: exceeds bed"
        fn = f"{prefix}_{name}.stl"
        m.export(fn)
        print(f"wrote {fn}  bbox {e[0]:.2f} x {e[1]:.2f} x {e[2]:.2f} mm  {m.volume/1000:.2f} cm^3")


# --- Previews -----------------------------------------------------------------------
LIP_RGB = (0.83, 0.62, 0.20)
FACE_RGB = (0.93, 0.89, 0.80)


def preview(parts, geo, png):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    light = np.array([0.35, -0.5, 0.75])
    light = light / np.linalg.norm(light)

    def collection(m, base, dz=0.0):
        mm = trimesh.Trimesh(*trimesh.remesh.subdivide_to_size(m.vertices, m.faces, 2.0))
        lam = np.clip(mm.face_normals @ light, 0, 1) * 0.7 + 0.3
        cols = np.column_stack([np.outer(lam, base), np.ones(len(lam))])
        return Poly3DCollection(mm.vertices[mm.faces] + [0, 0, dz], facecolors=cols, edgecolor="none")

    fig = plt.figure(figsize=(16, 9))
    ax = fig.add_subplot(2, 2, 1, projection="3d")
    for name, dz in [("egg_rim", 0), ("face", 12), ("star_rim", 24)]:
        base = FACE_RGB if name == "face" else LIP_RGB
        ax.add_collection3d(collection(parts[name], base, dz))
    r = 32 * geo["scale"] / 0.246
    ax.set_xlim(-r, r); ax.set_ylim(-r, r); ax.set_zlim(-r * 0.7, r * 1.3)
    ax.view_init(elev=25, azim=-65); ax.set_axis_off()
    ax.set_title("exploded — rim / face / star", fontsize=10)

    ax = fig.add_subplot(2, 2, 2, projection="3d")
    for name in parts:
        ax.add_collection3d(collection(parts[name], FACE_RGB if name == "face" else LIP_RGB))
    ax.set_xlim(-r, r); ax.set_ylim(-r, r); ax.set_zlim(-r, r)
    ax.view_init(elev=32, azim=-75); ax.set_axis_off()
    ax.set_title("assembled", fontsize=10)

    # joint sections: cut vertically through the egg's long axis (x = 0)
    colors = {"face": "#8a8265", "egg_rim": "#b8860b", "star_rim": "#b8860b"}
    for slot, (title, xw) in enumerate([
        ("egg rim groove + tongue (top of coin)", None),
        ("star rim groove + tongue", None),
    ]):
        ax = fig.add_subplot(2, 2, 3 + slot)
        for name, m in parts.items():
            sec = m.section(plane_origin=[0, 0, 0], plane_normal=[1, 0, 0])
            if sec is None:
                continue
            for ent in sec.entities:
                pts = sec.vertices[ent.points]
                ax.plot(pts[:, 1], pts[:, 2], "-", color=colors[name], lw=1.3)
        ax.set_aspect("equal")
        if slot == 0:  # top of the egg: rim zone
            y_top = geo["O"][:, 1].max()
            ax.set_xlim(y_top - 8, y_top + 1)
        else:  # star zone: around the top edge of the star
            y_do = geo["Do"][:, 1].max()
            ax.set_xlim(y_do - 6, y_do + 3)
        ax.set_ylim(-0.5, geo["T"] + 0.5)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("along the coin (mm)"); ax.set_ylabel("z (mm)")
        ax.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(png, dpi=130)
    print(f"wrote {png}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--height", type=float, default=HEIGHT_MM, help="printed coin height, mm")
    ap.add_argument("--joint", choices=["snap", "glue"], default="snap",
                    help="snap: closed grooves, tool-free; glue: drop-in rabbets + CA")
    args = ap.parse_args()

    import os

    out_dir = "legacy_snapring" if args.joint == "snap" else "legacy_gluefit"
    name = "coin_snapring" if args.joint == "snap" else "coin_gluefit"
    os.makedirs(out_dir, exist_ok=True)
    prefix = f"{out_dir}/{name}"
    parts, geo = build(args.height, args.joint)
    preview(parts, geo, f"{prefix}_design.png")
    export(parts, prefix, flip=args.joint == "glue")
