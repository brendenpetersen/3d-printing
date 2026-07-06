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
"""LEGACY (snap-peg clamshell) — only viable at large scale (~190 mm+ coins).

Superseded at 55 mm by coin_snap.py / coin_textured.py; kept because it is the
only design with hidden click-together fasteners, which need this much room.

Egg coin, two-color snap-fit — 5 flat-printing parts, no supports, no glue.

Parts (assembly, bottom to top; plate spans z = 0..FACE_T):
  1 x plate           (face color)  — the egg face with the star hole
  2 x egg rim ring    (lip color)   — outer lip, one per side
  2 x diamond rim ring(lip color)   — star lip around the hole, one per side

Snap mechanism: the BOTTOM rings carry round posts that pass through clearance
holes in the plate and click into capped sockets in the TOP rings. Post tips
are split (slotted) arrowheads: the slot gives PLA a long, thin flexing beam
(~1.7% strain at engagement, safely under PLA's limit), the nose cone is the
lead-in, and the barb seats behind the socket's internal ledge. Sockets are
blind — the visible faces stay untouched. The two rings clamp the plate;
every joint is serviceable (parts pry apart without breaking).

Edge skirts: each ring carries a thin skirt wall that wraps the plate's edge
(egg rings) or the hole bore (diamond rings), so the assembled coin's
silhouette and hole read entirely in lip color, like the original extrusion.
Skirts from both sides meet at a small parting gap at mid-thickness.

Print orientation (as exported): every part lies flat, visible face DOWN on
the bed (best finish), posts/sockets pointing up. No overhangs anywhere
except the sockets' tiny internal annular bridge (~0.5 mm, prints fine).

Run:  uv run coin_snappeg.py          # writes 5 STLs + preview PNGs
"""

from __future__ import annotations

import numpy as np
import trimesh

from coin_outlines import (
    assemble,
    buffer_loop,
    cap,
    dist_to_polyline,
    lift,
    load_outlines,
    midcurve,
    strip,
)

# --- Parameters -----------------------------------------------------------------
SCALE = 1.0          # global outline scale (1.0 = original 168.6 x 223.5 mm)
FACE_T = 8.0         # mm plate thickness (original face: 8)
LIP_H = 4.0          # mm ring thickness = lip height per side (original: 4)
SPACING = 0.4        # mm outline sampling step

SKIRT = True         # rings wrap the plate edge / hole bore in lip color
SKIRT_T = 1.2        # mm skirt wall thickness (3 perimeters at 0.4 nozzle)
SKIRT_GAP = 0.3      # mm total parting gap where the two skirts meet
CLR = 0.15           # mm radial clearance, skirt wall <-> plate wall

N_POSTS_EGG = 8      # snap posts around the egg rim
N_POSTS_DIA = 4      # snap posts in the star rim (auto-placed at wide spots)
POST_D_EGG = 4.0     # mm post shaft diameter, egg rim (ring ~12 mm wide)
POST_D_DIA = 3.2     # mm post shaft diameter, star rim (ring only ~8-10 mm wide)
BARB_LIP = 0.4       # mm barb radial protrusion per side (retention depth)
ENTRY_CLR = 0.15     # mm radial clearance, shaft <-> socket entry bore
ENTRY_DEPTH = 1.2    # mm socket entry bore length (the ledge the barb catches)
SEAT_SLACK = 0.1     # mm axial slack between barb shoulder and ledge
FLARE_H = 0.45       # mm barb flare cone height
NOSE_H = 1.3         # mm lead-in nose cone height
TIP_R = 1.2          # mm nose tip radius
CAVITY_CLR = 0.25    # mm radial clearance, barb <-> socket cavity
SLOT_W = 1.1         # mm split-slot width
SLOT_DEPTH = 6.0     # mm split-slot depth from the tip (the flexing length)
PLATE_HOLE_CLR = 0.5 # mm radial clearance, shaft <-> plate through-hole
HOLE_COMP = 0.2      # mm diametral FDM compensation added to every bore
MIN_WALL = 0.8       # mm minimum material around any bore

TEST_COUPON = True   # also export a tiny 3-piece snap-fit test print

BED = (256.0, 256.0, 260.0)
ENGINE = "manifold"


# --- Derived snap geometry (assembly z; plate bottom = 0) -------------------------
def snap_dims(post_d: float) -> dict:
    d = {"post_d": post_d}
    d["shaft_r"] = post_d / 2
    d["barb_r"] = post_d / 2 + BARB_LIP
    d["entry_r"] = (post_d + 2 * ENTRY_CLR + HOLE_COMP) / 2
    d["cavity_r"] = d["barb_r"] + CAVITY_CLR + HOLE_COMP / 2
    d["plate_hole_r"] = (post_d + 2 * PLATE_HOLE_CLR + HOLE_COMP) / 2
    d["z_shoulder"] = FACE_T + ENTRY_DEPTH + SEAT_SLACK
    d["z_barb"] = d["z_shoulder"] + FLARE_H
    d["z_tip"] = d["z_barb"] + NOSE_H
    d["cavity_top"] = d["z_tip"] + 0.15
    d["cap_t"] = LIP_H - (d["cavity_top"] - FACE_T)
    assert d["cap_t"] >= 0.6, f"socket cap only {d['cap_t']:.2f} mm — shorten the barb"
    # sanity: barb must clear the cavity, and flexing strain must be PLA-safe
    assert d["barb_r"] < d["cavity_r"], "barb larger than cavity"
    beam_t = (post_d - SLOT_W) / 2
    printed_entry_r = d["entry_r"] - 0.125  # holes print ~0.25 mm under
    strain = 1.5 * beam_t * (d["barb_r"] - printed_entry_r) / SLOT_DEPTH**2
    assert strain < 0.025, f"snap strain {strain:.1%} too high for PLA"
    d["strain"] = strain
    return d


# --- Station placement ------------------------------------------------------------
def stations(outer, inner, n, margin_out, margin_in):
    """Choose n post centers on the ring's centerline, preferring even spacing,
    falling back to the locally-widest spots (the star ring's knobs)."""
    mid = midcurve(outer, inner, 1500)
    clear = np.minimum(
        dist_to_polyline(mid, outer) - margin_out,
        dist_to_polyline(mid, inner) - margin_in,
    )
    best_idx, best_score = None, -np.inf
    for ph in np.linspace(0, 1.0 / n, 48, endpoint=False):
        idx = (((np.arange(n) / n + ph) * len(mid)).astype(int)) % len(mid)
        s = clear[idx].min()
        if s > best_score:
            best_score, best_idx = s, idx
    if best_score >= 0:
        return mid[best_idx]
    # greedy: clearance maxima with minimum arc separation
    order, chosen = np.argsort(-clear), []
    min_sep = len(mid) / (2.5 * n)
    for i in order:
        if clear[i] < 0:
            break
        if all(min((i - j) % len(mid), (j - i) % len(mid)) >= min_sep for j in chosen):
            chosen.append(i)
        if len(chosen) == n:
            break
    assert len(chosen) == n, (
        f"only {len(chosen)}/{n} posts fit — reduce POST_D or post count"
    )
    return mid[np.sort(np.array(chosen))]


# --- Solid builders ----------------------------------------------------------------
def extrude_ring(outer, inners, z0, z1):
    """Straight extrusion of a ring/disc between two heights (watertight)."""
    patches = [cap(outer, inners, z0, False), cap(outer, inners, z1, True)]
    patches.append(strip(lift(outer, z0), lift(outer, z1)))
    for inn in inners:
        patches.append(strip(lift(inn, z0), lift(inn, z1)))
    return patches


def ring_with_skirt(outer, inner, z_body, skirt_loops, z_skirt, name):
    """A rim ring slab plus (optionally) its skirt step, as one watertight solid.

    outer/inner: the ring's boundaries. skirt_loops: (skirt_outer, skirt_inner)
    or None. The skirt zone spans z_skirt, the body spans z_body; the two share
    the boundary loop that the skirt grows from.
    """
    zb0, zb1 = z_body
    if not skirt_loops:
        return assemble(extrude_ring(outer, [inner], zb0, zb1), name)
    (sk_out, sk_in), (zs0, zs1) = skirt_loops, z_skirt
    # which side does the skirt sit on? egg ring: skirt at the outer edge
    # (sk_out is `outer`); star ring: skirt at the hole (sk_in is `inner`).
    at_outer = sk_out is outer
    patches = [cap(outer, [inner], zb0, zb0 > zb1)]  # ring's visible face
    if at_outer:
        patches += [
            cap(sk_in, [inner], zb1, zb1 > zb0),   # flat face the plate touches
            cap(sk_out, [sk_in], zs1, zs1 > zs0),  # skirt end face
            strip(lift(outer, zb0), lift(outer, zs1)),   # outside wall (full)
            strip(lift(sk_in, zb1), lift(sk_in, zs1)),   # skirt inner wall
            strip(lift(inner, zb0), lift(inner, zb1)),   # ring inner wall
        ]
    else:
        patches += [
            cap(outer, [sk_out], zb1, zb1 > zb0),
            cap(sk_out, [sk_in], zs1, zs1 > zs0),
            strip(lift(inner, zb0), lift(inner, zs1)),   # hole wall (full)
            strip(lift(sk_out, zb1), lift(sk_out, zs1)),  # skirt outer wall
            strip(lift(outer, zb0), lift(outer, zb1)),   # ring outer wall
        ]
    return assemble(patches, name)


def post_solid(xy, d):
    prof = np.array([
        [0.0, 0.0],
        [d["shaft_r"], 0.0],
        [d["shaft_r"], d["z_shoulder"]],
        [d["barb_r"], d["z_barb"]],
        [TIP_R, d["z_tip"]],
        [0.0, d["z_tip"]],
    ])
    p = trimesh.creation.revolve(prof, sections=64)
    p.apply_translation([xy[0], xy[1], 0.0])
    return p


def slot_box(xy, tangent, d):
    t = tangent / np.linalg.norm(tangent)
    box = trimesh.creation.box((d["post_d"] + 2.0, SLOT_W, SLOT_DEPTH + 0.5))
    rot = np.eye(4)
    rot[:2, 0], rot[:2, 1] = t, [-t[1], t[0]]  # slot gap opens along the rim normal
    box.apply_transform(rot)
    box.apply_translation([xy[0], xy[1], d["z_tip"] + 0.3 - (SLOT_DEPTH + 0.5) / 2])
    return box


def socket_tool(xy, d):
    z_entry0 = FACE_T - 0.5  # extend below the ring face for a clean cut
    prof = np.array([
        [0.0, z_entry0],
        [d["entry_r"], z_entry0],
        [d["entry_r"], FACE_T + ENTRY_DEPTH],
        [d["cavity_r"], FACE_T + ENTRY_DEPTH],
        [d["cavity_r"], d["cavity_top"]],
        [0.0, d["cavity_top"]],
    ])
    p = trimesh.creation.revolve(prof, sections=64)
    p.apply_translation([xy[0], xy[1], 0.0])
    return p


def boolean(kind, meshes):
    fn = trimesh.boolean.union if kind == "union" else trimesh.boolean.difference
    out = fn(meshes, engine=ENGINE)
    out.merge_vertices(digits_vertex=6)
    return out


# --- Build all five parts (assembly coordinates) -----------------------------------
def build(scale: float):
    L = load_outlines(spacing=SPACING)
    from coin_outlines import symmetrize_loop
    O, I, Do, H = (symmetrize_loop(L[k] * scale) for k in ("O", "I", "Do", "H"))
    d_egg = snap_dims(POST_D_EGG)
    d_dia = snap_dims(POST_D_DIA)

    skirt_len = FACE_T / 2 - SKIRT_GAP / 2
    if SKIRT:
        O_sk = buffer_loop(O, -SKIRT_T, SPACING)
        H_sk = buffer_loop(H, +SKIRT_T, SPACING)
        O_plate = buffer_loop(O, -(SKIRT_T + CLR), SPACING)
        H_plate = buffer_loop(H, +(SKIRT_T + CLR), SPACING)
    else:
        O_sk = H_sk = None
        O_plate, H_plate = O, H

    # post stations (shared by plate holes, posts, and sockets)
    def need(d):
        return max(d["cavity_r"], d["plate_hole_r"]) + MIN_WALL

    skirt_m = (SKIRT_T + CLR) if SKIRT else 0.0
    st_egg = stations(O, I, N_POSTS_EGG, need(d_egg) + skirt_m, need(d_egg))
    st_dia = stations(Do, H, N_POSTS_DIA, need(d_dia), need(d_dia) + skirt_m)

    # tangents at stations (for slot orientation)
    def tangents(loop, pts):
        from scipy.spatial import cKDTree

        _, idx = cKDTree(loop).query(pts)
        return loop[(idx + 2) % len(loop)] - loop[idx - 2]

    tan_egg, tan_dia = tangents(O, st_egg), tangents(H, st_dia)

    # ---- plate ----
    plate = assemble(extrude_ring(O_plate, [H_plate], 0.0, FACE_T), "plate_raw")
    holes = [
        trimesh.creation.cylinder(
            radius=d["plate_hole_r"], height=FACE_T + 2, sections=64,
            transform=trimesh.transformations.translation_matrix([x, y, FACE_T / 2]),
        )
        for sts, d in [(st_egg, d_egg), (st_dia, d_dia)]
        for x, y in sts
    ]
    plate = boolean("difference", [plate] + holes)

    # ---- rings ----
    egg_skirt = (O, O_sk) if SKIRT else None
    dia_skirt = (H_sk, H) if SKIRT else None

    egg_bot = ring_with_skirt(O, I, (-LIP_H, 0.0), egg_skirt, (0.0, skirt_len), "egg_bot")
    egg_top = ring_with_skirt(
        O, I, (FACE_T + LIP_H, FACE_T), egg_skirt, (FACE_T, FACE_T - skirt_len), "egg_top"
    )
    dia_bot = ring_with_skirt(Do, H, (-LIP_H, 0.0), dia_skirt, (0.0, skirt_len), "dia_bot")
    dia_top = ring_with_skirt(
        Do, H, (FACE_T + LIP_H, FACE_T), dia_skirt, (FACE_T, FACE_T - skirt_len), "dia_top"
    )

    def add_posts(ring, sts, tans, d):
        posts = [post_solid(p, d) for p in sts]
        slots = [slot_box(p, t, d) for p, t in zip(sts, tans)]
        return boolean("difference", [boolean("union", [ring] + posts)] + slots)

    def cut_sockets(ring, sts, d):
        return boolean("difference", [ring] + [socket_tool(p, d) for p in sts])

    egg_bot = add_posts(egg_bot, st_egg, tan_egg, d_egg)
    dia_bot = add_posts(dia_bot, st_dia, tan_dia, d_dia)
    egg_top = cut_sockets(egg_top, st_egg, d_egg)
    dia_top = cut_sockets(dia_top, st_dia, d_dia)

    parts = {
        "plate": plate,
        "egg_ring_bottom": egg_bot,
        "egg_ring_top": egg_top,
        "diamond_ring_bottom": dia_bot,
        "diamond_ring_top": dia_top,
    }

    # ---- assembly interference check (seated parts must not overlap) ----
    for a, b in [
        ("plate", "egg_ring_bottom"), ("plate", "egg_ring_top"),
        ("plate", "diamond_ring_bottom"), ("plate", "diamond_ring_top"),
        ("egg_ring_bottom", "egg_ring_top"), ("diamond_ring_bottom", "diamond_ring_top"),
    ]:
        inter = trimesh.boolean.intersection([parts[a], parts[b]], engine=ENGINE)
        vol = 0.0 if inter.is_empty else inter.volume
        assert vol < 1e-3, f"{a} x {b} interfere: {vol:.3f} mm^3"

    print(
        f"snap: {N_POSTS_EGG} egg posts (Ø{POST_D_EGG}, strain {d_egg['strain']:.1%}) "
        f"+ {N_POSTS_DIA} star posts (Ø{POST_D_DIA}, strain {d_dia['strain']:.1%}); "
        f"barb +{BARB_LIP} mm/side, socket cap {d_egg['cap_t']:.1f} mm"
    )
    return parts, d_egg, (st_egg, st_dia, tan_egg)


# --- Snap-fit test coupon (print + click before committing to the full coin) --------
def coupon_parts(d: dict) -> dict:
    """One post pad, one plate slice, one socket pad — the joint in miniature."""
    s = 9.0
    sq = np.array([[-s, -s], [s, -s], [s, s], [-s, s]])

    bot = assemble(extrude_ring(sq, [], -LIP_H, 0.0), "coupon_bot")
    bot = boolean("difference", [
        boolean("union", [bot, post_solid((0, 0), d)]),
        slot_box((0, 0), np.array([1.0, 0.0]), d),
    ])
    mid = assemble(extrude_ring(sq, [], 0.0, FACE_T), "coupon_mid")
    mid = boolean("difference", [mid, trimesh.creation.cylinder(
        radius=d["plate_hole_r"], height=FACE_T + 2, sections=64,
        transform=trimesh.transformations.translation_matrix([0, 0, FACE_T / 2]),
    )])
    top = assemble(extrude_ring(sq, [], FACE_T, FACE_T + LIP_H), "coupon_top")
    top = boolean("difference", [top, socket_tool((0, 0), d)])
    # "_top" suffix so export() flips it into print orientation like the rings
    return {"test_post": bot, "test_plate": mid, "test_socket_top": top}


# --- Export in print orientation + verify -------------------------------------------
def export(parts: dict, scale: float) -> dict:
    out = {}
    for name, mesh in parts.items():
        m = mesh.copy()
        if name.endswith("_top"):  # flip: visible face down, sockets up
            m.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
        m.apply_translation([0, 0, -m.bounds[0][2]])
        assert m.is_watertight, f"{name}: not watertight"
        assert m.body_count == 1, f"{name}: {m.body_count} bodies"
        e = m.extents
        assert e[0] <= BED[0] and e[1] <= BED[1] and e[2] <= BED[2], f"{name}: exceeds bed"
        fn = f"snappeg/coin_snappeg_{name}.stl"
        m.export(fn)
        out[name] = m
        print(f"wrote {fn}  bbox {e[0]:.1f} x {e[1]:.1f} x {e[2]:.1f} mm  {m.volume/1000:.1f} cm^3")
    return out


# --- Previews -------------------------------------------------------------------------
LIP_RGB = (0.83, 0.62, 0.20)
FACE_RGB = (0.93, 0.89, 0.80)


def preview_assembly(parts, st_egg, png):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    light = np.array([0.35, -0.5, 0.75])
    light = light / np.linalg.norm(light)

    def collection(m, base, dz=0.0):
        mm = trimesh.Trimesh(*trimesh.remesh.subdivide_to_size(m.vertices, m.faces, 6.0))
        lam = np.clip(mm.face_normals @ light, 0, 1) * 0.7 + 0.3
        cols = np.column_stack([np.outer(lam, base), np.ones(len(lam))])
        tris = mm.vertices[mm.faces] + [0, 0, dz]
        return Poly3DCollection(tris, facecolors=cols, edgecolor="none")

    fig = plt.figure(figsize=(16, 9))
    # exploded
    ax = fig.add_subplot(1, 2, 1, projection="3d")
    offs = {
        "egg_ring_bottom": -30, "diamond_ring_bottom": -30,
        "plate": 0, "egg_ring_top": 30, "diamond_ring_top": 30,
    }
    for name, m in parts.items():
        base = FACE_RGB if name == "plate" else LIP_RGB
        ax.add_collection3d(collection(m, base, offs[name]))
    ax.set_xlim(-120, 120); ax.set_ylim(-120, 120); ax.set_zlim(-100, 140)
    ax.view_init(elev=28, azim=-60); ax.set_axis_off()
    ax.set_title("exploded (assembly stack: ring / plate / ring)")

    # assembled, slightly tilted
    ax = fig.add_subplot(1, 2, 2, projection="3d")
    for name, m in parts.items():
        base = FACE_RGB if name == "plate" else LIP_RGB
        ax.add_collection3d(collection(m, base))
    ax.set_xlim(-115, 115); ax.set_ylim(-115, 115); ax.set_zlim(-110, 120)
    ax.view_init(elev=35, azim=-75); ax.set_axis_off()
    ax.set_title("assembled — lips + edge in lip color, face in face color")
    plt.tight_layout()
    plt.savefig(png, dpi=110)
    print(f"wrote {png}")


def preview_snap_section(parts, station, tangent, d, png):
    """Cut the seated assembly through one post and plot the snap joint."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = tangent / np.linalg.norm(tangent)
    nrm = np.array([t[0], t[1], 0.0])  # cut across the post, along the rim normal
    fig, ax = plt.subplots(figsize=(7, 9))
    colors = {
        "plate": "#8a8265", "egg_ring_bottom": "#b8860b", "egg_ring_top": "#7a5c0a",
    }
    inplane = np.array([-t[1], t[0], 0.0])
    for name in ["plate", "egg_ring_bottom", "egg_ring_top"]:
        sec = parts[name].section(plane_origin=[station[0], station[1], 0], plane_normal=nrm)
        if sec is None:
            continue
        for ent in sec.entities:
            pts = sec.vertices[ent.points] - [station[0], station[1], 0]
            u = pts @ inplane
            ax.plot(u, pts[:, 2], "-", color=colors[name], lw=1.4)
    ax.set_aspect("equal")
    ax.set_xlim(-14, 14)
    ax.set_title("snap joint section — post (bottom ring) through plate into socket (top ring)")
    ax.set_xlabel("across the rim (mm)"); ax.set_ylabel("assembly z (mm)")
    ax.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(png, dpi=130)
    print(f"wrote {png}")


if __name__ == "__main__":
    import os

    os.makedirs("snappeg", exist_ok=True)
    parts, dims, (st_egg, st_dia, tan_egg) = build(SCALE)
    preview_assembly(parts, st_egg, "snappeg/coin_snappeg_preview.png")
    preview_snap_section(parts, st_egg[0], tan_egg[0], dims, "snappeg/coin_snappeg_joint.png")
    export(parts, SCALE)
    if TEST_COUPON:
        export(coupon_parts(dims), SCALE)
