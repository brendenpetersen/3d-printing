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
"""Shared outline extraction + mesh helpers for the egg-coin generators.

Parses ``coin.svg`` into the four closed curves that define the coin,
in model coordinates (mm, page center at origin, +Y up = egg point up):

- ``O``  — egg outer boundary (the coin silhouette)
- ``I``  — egg rim inner boundary (where the outer lip meets the face)
- ``Do`` — diamond rim outer boundary (where the inner lip meets the face)
- ``H``  — the through-hole boundary (curved-diamond / astroid shape)

The original TinkerCAD extrusion is: face slab between I and Do at
|z| <= face_t/2, both rims (O..I and Do..H) at |z| <= face_t/2 + lip_h.

All loops are returned CCW, resampled ~evenly by arclength but keeping
every SVG segment endpoint exact (preserves the hole's needle cusps).

Run directly to validate against the reference measurements:
    uv run coin_outlines.py
"""

from __future__ import annotations

import numpy as np
import trimesh

SVG_FILE = "coin.svg"
PAGE_CENTER = 128.0  # coin.svg is a 256x256 mm page

# Reference metrics of the current coin.svg outlines (regression check on
# parsing/scaling). The egg height is pinned to the 223.52 mm design height;
# the outer loop traces the app's symmetrized egg_outline.json.
REF_RIM_TOP_AREA = 9361.0  # mm^2, flat area at z = +-8 (both rim tops)
REF_FACE_AREA = 17878.0  # mm^2, flat area at z = +-4 (face annulus)
REF_BBOX = (167.552, 223.520)  # mm, coin footprint


# --- SVG parsing --------------------------------------------------------------


def _sample_subpath(sub, spacing: float) -> np.ndarray:
    """Sample one closed subpath ~every `spacing` mm, keeping segment endpoints
    exact so tangent-discontinuous corners (the hole cusps) are preserved."""
    pts = []
    for seg in sub:
        n = max(int(np.ceil(seg.length() / spacing)), 2)
        ts = np.linspace(0.0, 1.0, n, endpoint=False)  # endpoint = next seg's start
        pts.extend(seg.point(t) for t in ts)
    arr = np.array([[p.real, p.imag] for p in pts])
    # drop consecutive duplicates (zero-length artifacts)
    keep = np.ones(len(arr), dtype=bool)
    keep[1:] = np.linalg.norm(np.diff(arr, axis=0), axis=1) > 1e-9
    return arr[keep]


def signed_area(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def load_outlines(svg_file: str = SVG_FILE, spacing: float = 0.4) -> dict[str, np.ndarray]:
    """Return the four unique closed loops as CCW (N,2) arrays in model mm."""
    from svgpathtools import svg2paths

    paths, _ = svg2paths(svg_file)
    loops = []
    for path in paths:
        for sub in path.continuous_subpaths():
            if not sub.isclosed():
                continue
            pts = _sample_subpath(sub, spacing)
            # SVG y-down -> model y-up, centered on the page
            pts = np.column_stack([pts[:, 0] - PAGE_CENTER, PAGE_CENTER - pts[:, 1]])
            if signed_area(pts) < 0:
                pts = pts[::-1]
            loops.append(pts)

    # dedupe repeated boundaries (each shared curve is drawn in two SVG paths)
    unique: list[np.ndarray] = []
    for lp in loops:
        a, c = abs(signed_area(lp)), lp.mean(axis=0)
        dup = any(
            abs(abs(signed_area(u)) - a) < 0.01 * a and np.linalg.norm(u.mean(axis=0) - c) < 0.5
            for u in unique
        )
        if not dup:
            unique.append(lp)
    if len(unique) != 4:
        raise ValueError(f"expected 4 unique loops in {svg_file}, found {len(unique)}")

    unique.sort(key=lambda p: -abs(signed_area(p)))
    return dict(zip(["O", "I", "Do", "H"], unique))


# --- 2D helpers ---------------------------------------------------------------


def buffer_loop(pts: np.ndarray, dist: float, spacing: float = 0.4) -> np.ndarray:
    """Offset a closed loop with round joins (shapely buffer) and resample.

    dist > 0 dilates (offsets away from the interior), dist < 0 erodes.
    Correct across necks/cusps where a naive per-vertex offset self-intersects:
    the buffered outline merges/rounds there. No vertex correspondence with the
    input is kept. Returns a CCW loop resampled ~every `spacing` mm.
    """
    from shapely.geometry import Polygon

    buf = Polygon(pts).buffer(dist, quad_segs=64)
    if buf.geom_type != "Polygon" or buf.interiors:
        raise ValueError(f"buffer by {dist} changed topology ({buf.geom_type})")
    out = np.array(buf.exterior.coords[:-1])
    if signed_area(out) < 0:
        out = out[::-1]
    n = max(int(np.ceil(buf.exterior.length / spacing)), 32)
    return resample_loop(out, n)


def loop_width_to(loop_a: np.ndarray, loop_b: np.ndarray) -> np.ndarray:
    """For each vertex of loop_a, distance to the nearest vertex of loop_b."""
    from scipy.spatial import cKDTree

    return cKDTree(loop_b).query(loop_a)[0]


def offset_variable(pts: np.ndarray, d: np.ndarray, miter_limit: float = 1.5) -> np.ndarray:
    """Offset a dense CCW loop by a PER-VERTEX distance (positive = inward).

    Miter (angle-bisector) offset with capped spikes. Safe only for |d| small
    relative to local curvature radii and smoothly-varying d — validity is
    checked. Keeps 1:1 vertex correspondence with the input.
    """
    e = np.roll(pts, -1, axis=0) - pts
    e /= np.linalg.norm(e, axis=1, keepdims=True)
    n_edge = np.column_stack([-e[:, 1], e[:, 0]])  # left of travel = inward (CCW)
    m = np.roll(n_edge, 1, axis=0) + n_edge
    mlen = np.linalg.norm(m, axis=1, keepdims=True)
    m = np.divide(m, mlen, out=np.zeros_like(m), where=mlen > 1e-12)
    cos_half = np.clip(np.einsum("ij,ij->i", m, n_edge), 1.0 / miter_limit, 1.0)
    out = pts + np.asarray(d)[:, None] * m / cos_half[:, None]

    from shapely.geometry import Polygon

    if not Polygon(out).is_valid:
        raise ValueError("variable offset produced a self-intersecting loop")
    return out


def dist_to_polyline(points: np.ndarray, loop: np.ndarray) -> np.ndarray:
    """Exact distance from each 2D point to a closed polyline.

    KD-tree narrows to the nearest loop vertex, then the point is projected
    onto that vertex's neighboring segments. Exactness matters: sampled-vertex
    distances carry O(spacing) error, which shows up as phantom steep facets
    when used as a height field on sliver triangles.
    """
    from scipy.spatial import cKDTree

    n = len(loop)
    _, nearest = cKDTree(loop).query(points)
    best = np.full(len(points), np.inf)
    for k in range(-2, 2):  # segments (i+k, i+k+1) around the nearest vertex
        i0 = (nearest + k) % n
        a = loop[i0]
        b = loop[(i0 + 1) % n]
        ab = b - a
        denom = np.einsum("ij,ij->i", ab, ab)
        t = np.clip(np.einsum("ij,ij->i", points - a, ab) / np.maximum(denom, 1e-18), 0, 1)
        foot = a + t[:, None] * ab
        best = np.minimum(best, np.linalg.norm(points - foot, axis=1))
    return best


def snap_to_distance(loop: np.ndarray, crease: np.ndarray, w: float) -> np.ndarray:
    """Radially adjust `loop` so every vertex sits exactly `w` from `crease`.

    A buffered+resampled offset curve sits within ~chord-sag of the true
    offset; snapping removes that epsilon so a distance-field ramp built
    between crease and loop is exactly planar at the toe."""
    from scipy.spatial import cKDTree

    d = dist_to_polyline(loop, crease)
    _, nearest = cKDTree(crease).query(loop)
    # direction away from the crease, approximated via the nearest vertex —
    # good to first order since |d - w| is tiny
    v = loop - crease[nearest]
    vn = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)
    return loop + vn * (w - d)[:, None]


def midcurve(outer: np.ndarray, inner: np.ndarray, n: int = 800) -> np.ndarray:
    """Approximate centerline of the ring between two loops (resampled to n)."""
    from scipy.spatial import cKDTree

    _, idx = cKDTree(inner).query(outer)
    mid = 0.5 * (outer + inner[idx])
    return resample_loop(mid, n)


def symmetrize_loop(pts: np.ndarray) -> np.ndarray:
    """Exactly mirror-symmetrize a CCW loop about x=0 (the egg's long axis).

    Printed face halves mate with flipped copies of themselves, so their
    silhouettes must be invariant under reflection about x=0. The loop is
    resampled to an even count starting at its top axis crossing; sample i
    and sample N-i are then mirror conjugates, and each pair is rewritten to
    exactly opposite x and equal y (float negation is exact), with on-axis
    samples pinned to x=0. The result is reflection-invariant by
    construction; the shape shift is bounded by the input's own asymmetry
    (coin.svg is drawn exactly symmetric, so in practice this only cancels
    float noise from parsing and page centering)."""
    n_in = len(pts)
    x = pts[:, 0]

    # Locate the x=0 crossings (exact vertex hits or sign-change edges).
    crossings = []  # (insert_after_index_or_vertex, point)
    for i in range(n_in):
        j = (i + 1) % n_in
        if x[i] == 0.0:
            crossings.append((i, pts[i], True))
        elif (x[i] < 0.0) != (x[j] < 0.0):
            t = x[i] / (x[i] - x[j])
            crossings.append((i, pts[i] + t * (pts[j] - pts[i]), False))
    if len(crossings) < 2:
        raise ValueError("loop does not cross the x=0 axis twice")
    top = max(crossings, key=lambda c: c[1][1])

    i0, p0, at_vertex = top
    ring = np.roll(pts, -i0, axis=0) if at_vertex else np.vstack(
        [p0[None, :], np.roll(pts, -(i0 + 1), axis=0)]
    )

    n = n_in + (n_in % 2)  # even count for i <-> N-i pairing
    res = resample_loop(ring, n)
    half = n // 2
    out = res.copy()
    out[0] = [0.0, res[0, 1]]
    out[half] = [0.0, res[half, 1]]
    idx = np.arange(1, half)
    jdx = n - idx
    xa = 0.5 * (res[idx, 0] - res[jdx, 0])
    ya = 0.5 * (res[idx, 1] + res[jdx, 1])
    out[idx, 0], out[idx, 1] = xa, ya
    out[jdx, 0], out[jdx, 1] = -xa, ya

    shift = np.abs(out - res).max()
    if shift > 1.0:
        raise ValueError(f"symmetrization moved the loop {shift:.2f} mm")
    return out


def resample_loop(pts: np.ndarray, n: int) -> np.ndarray:
    """Resample a closed loop to n points, evenly by arclength."""
    seg = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    si = np.linspace(0.0, s[-1], n, endpoint=False)
    closed = np.vstack([pts, pts[:1]])
    x = np.interp(si, s, closed[:, 0])
    y = np.interp(si, s, closed[:, 1])
    return np.column_stack([x, y])


# --- Mesh patch builders -------------------------------------------------------


def mating_features(outer_loop, inner_loop, I, Do, half_t,
                    peg_d=2.5, peg_dx=3.0, peg_clr=0.15, hole_comp=0.2,
                    floor=0.4):
    """Integrated male/female registration for a SELF-MATING face half.

    Pegs at x>0 with sockets mirrored at x<0: flipping the part about the
    y (long) axis maps every peg onto the partner's socket, so one model
    mates with a flipped copy of itself — no loose pegs. Four mirrored
    pairs (N, S, and the two diagonals, where the annulus is widest — the
    star's flanks recede between its knobs) give eight engagement points
    per joint. In the assembled joint polarity alternates automatically:
    +x positions carry the bottom half's pegs, -x the top's. Features must
    stay OFF the x=0 axis (a feature there would meet itself).
    Returns (peg_solids, socket_cut_tools).
    """
    socket_depth = half_t - floor
    assert socket_depth >= 0.45, "face half too thin for peg sockets"
    socket_r = (peg_d + peg_clr + hole_comp) / 2
    peg_h = socket_depth - 0.10

    def extreme(loop, axis, sign):
        m = np.abs(loop[:, 1 - axis]) < 1.0
        vals = loop[m, axis]
        return vals.max() if sign > 0 else vals.min()

    def x_mid_at(y):
        """Annulus midline x (on the +x side) at height y."""
        def ext(loop):
            m = np.abs(loop[:, 1] - y) < 1.0
            assert m.any(), f"no boundary points near y={y:.1f}"
            return loop[m, 0].max()
        return 0.5 * (ext(inner_loop) + ext(outer_loop))

    y_n = 0.5 * (extreme(I, 1, +1) + extreme(Do, 1, +1))
    y_s = 0.5 * (extreme(I, 1, -1) + extreme(Do, 1, -1))
    y_dn, y_ds = 0.5 * y_n, 0.5 * y_s
    spots = [(peg_dx, y_n), (peg_dx, y_s),
             (x_mid_at(y_dn), y_dn), (x_mid_at(y_ds), y_ds)]

    pegs, cuts = [], []
    for sx, sy in spots:
        for cx, male in ((sx, True), (-sx, False)):
            c = np.array([cx, sy])
            for lp in (outer_loop, inner_loop):
                d = dist_to_polyline(c[None, :], lp)[0]
                assert d >= socket_r + 0.8, (
                    f"mating feature at ({cx:.1f},{sy:.1f}) too close to an edge"
                )
            cyl_kw = dict(sections=48)
            if male:
                p = trimesh.creation.cylinder(radius=peg_d / 2, height=peg_h, **cyl_kw)
                p.apply_translation([cx, sy, half_t + peg_h / 2])
                pegs.append(p)
            else:
                s = trimesh.creation.cylinder(
                    radius=socket_r, height=socket_depth + 0.5, **cyl_kw)
                s.apply_translation(
                    [cx, sy, half_t - socket_depth + (socket_depth + 0.5) / 2])
                cuts.append(s)
    return pegs, cuts


def merged_shaded(entries, light=(0.35, -0.5, 0.75), max_edge=2.0):
    """One Poly3DCollection from positioned (mesh, rgb) pairs, Lambert-shaded.

    matplotlib only depth-sorts faces WITHIN a collection; separate collections
    paint in add-order, so multi-part previews interpenetrate visually. Merging
    every part's triangles into a single collection fixes the occlusion.
    """
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    lt = np.asarray(light, dtype=float)
    lt = lt / np.linalg.norm(lt)
    tris, cols = [], []
    for m, base in entries:
        mm = trimesh.Trimesh(*trimesh.remesh.subdivide_to_size(m.vertices, m.faces, max_edge))
        lam = np.clip(mm.face_normals @ lt, 0, 1) * 0.7 + 0.3
        tris.append(mm.vertices[mm.faces])
        cols.append(np.column_stack([np.outer(lam, np.asarray(base)), np.ones(len(lam))]))
    return Poly3DCollection(np.concatenate(tris), facecolors=np.concatenate(cols), edgecolor="none")


def cap(outer: np.ndarray, inners: list[np.ndarray], z: float, up: bool) -> trimesh.Trimesh:
    """Flat triangulated ring/disc at height z. Boundary vertices are kept
    exactly, so adjacent wall strips stitch by merge_vertices."""
    from shapely.geometry import Polygon
    from trimesh.creation import triangulate_polygon

    poly = Polygon(outer, [inn[::-1] for inn in inners])
    v2, f = triangulate_polygon(poly, engine="earcut")
    v3 = np.column_stack([v2, np.full(len(v2), z)])
    if not up:
        f = f[:, ::-1]
    return trimesh.Trimesh(vertices=v3, faces=f, process=False)


def band(
    outer: np.ndarray,
    inner: np.ndarray,
    crease: np.ndarray,
    z_crease: float,
    z_toe: float,
    run: float,
    up: bool,
    max_area: float = 1.0,
) -> trimesh.Trimesh:
    """Chamfer-ramp surface over the annular band between `outer` and `inner`.

    One of the two boundary loops is the `crease` (the lip's top edge, at
    z_crease); the other is the ramp toe (at z_toe). Interior vertex heights
    follow the distance field to the crease: z = z_crease -> z_toe linearly
    over `run` mm. Where two branches of the crease face each other across a
    neck, the distance field forms the correct merged-ramp ridge, so the
    surface slope never exceeds atan(|z_crease - z_toe| / run) anywhere.

    Triangulated with Shewchuk's `triangle` (constrained, boundary vertices
    kept exactly, interior Steiner points allowed) so the ridge is resolved.
    """
    import triangle as tr

    def segs(n0, count):
        i = np.arange(count)
        return np.column_stack([n0 + i, n0 + (i + 1) % count])

    pslg = {
        "vertices": np.vstack([outer, inner]),
        "segments": np.vstack([segs(0, len(outer)), segs(len(outer), len(inner))]),
        "holes": [inner.mean(axis=0)],
    }
    # p: PSLG, Y: never split my boundary segments, q: quality, a: max area
    out = tr.triangulate(pslg, f"pYq30a{max_area}")
    v2, f = out["vertices"], out["triangles"]
    nb = len(outer) + len(inner)
    assert np.allclose(v2[:nb], pslg["vertices"]), "boundary moved"

    # interior Steiner points follow the exact distance field to the crease...
    d = dist_to_polyline(v2, crease)
    t = np.clip(d / run, 0.0, 1.0)
    z = z_crease + (z_toe - z_crease) * t
    # ...but boundary vertices are pinned to their exact design heights so
    # adjacent caps/strips stitch watertight
    outer_is_crease = len(crease) == len(outer) and np.allclose(crease, outer)
    z[: len(outer)] = z_crease if outer_is_crease else z_toe
    z[len(outer) : nb] = z_toe if outer_is_crease else z_crease
    v3 = np.column_stack([v2, z])
    if not up:
        f = f[:, ::-1]
    return trimesh.Trimesh(vertices=v3, faces=f, process=False)


def strip(loop_a: np.ndarray, loop_b: np.ndarray) -> trimesh.Trimesh:
    """Closed quad strip between two same-length 3D loops (vertex i <-> i)."""
    assert loop_a.shape == loop_b.shape and loop_a.shape[1] == 3
    n = len(loop_a)
    v = np.vstack([loop_a, loop_b])
    i = np.arange(n)
    j = (i + 1) % n
    f1 = np.column_stack([i, j, n + i])
    f2 = np.column_stack([n + i, j, n + j])
    return trimesh.Trimesh(vertices=v, faces=np.vstack([f1, f2]), process=False)


def lift(loop2d: np.ndarray, z: float) -> np.ndarray:
    return np.column_stack([loop2d, np.full(len(loop2d), z)])


def assemble(patches: list[trimesh.Trimesh], name: str) -> trimesh.Trimesh:
    """Concatenate patches into one solid; stitch, orient, and gate-check."""
    mesh = trimesh.util.concatenate(patches)
    mesh.merge_vertices(digits_vertex=6)
    # NOTE: keep zero-area sliver faces (earcut emits them on collinear runs) —
    # they are topological connectors; dropping them opens the shell.
    trimesh.repair.fix_normals(mesh)
    if mesh.volume < 0:
        mesh.invert()
    assert mesh.is_watertight, f"{name}: not watertight"
    assert mesh.body_count == 1, f"{name}: {mesh.body_count} bodies"
    return mesh


# --- Validation ---------------------------------------------------------------

if __name__ == "__main__":
    L = load_outlines()
    areas = {k: signed_area(v) for k, v in L.items()}
    for k, v in L.items():
        print(f"{k}: {len(v)} pts, area {areas[k]:9.1f} mm^2, "
              f"bbox {np.ptp(v[:, 0]):.2f} x {np.ptp(v[:, 1]):.2f} mm")

    rim_tops = areas["O"] - areas["I"] + areas["Do"] - areas["H"]
    face = areas["I"] - areas["Do"]
    bbox = (np.ptp(L["O"][:, 0]), np.ptp(L["O"][:, 1]))
    print(f"\nrim-top area {rim_tops:.0f} (ref {REF_RIM_TOP_AREA:.0f})")
    print(f"face area    {face:.0f} (ref {REF_FACE_AREA:.0f})")
    print(f"footprint    {bbox[0]:.2f} x {bbox[1]:.2f} (ref {REF_BBOX[0]} x {REF_BBOX[1]})")
    assert abs(rim_tops - REF_RIM_TOP_AREA) / REF_RIM_TOP_AREA < 0.01
    assert abs(face - REF_FACE_AREA) / REF_FACE_AREA < 0.01
    assert abs(bbox[0] - REF_BBOX[0]) < 0.2 and abs(bbox[1] - REF_BBOX[1]) < 0.2

    egg_w = loop_width_to(L["I"], L["O"])
    dia_w = loop_width_to(L["H"], L["Do"])
    gap_w = loop_width_to(L["Do"], L["I"])
    print(f"\negg rim width     {egg_w.min():.2f} .. {egg_w.max():.2f} mm")
    print(f"diamond rim width {dia_w.min():.2f} .. {dia_w.max():.2f} mm")
    print(f"face gap Do->I    {gap_w.min():.2f} .. {gap_w.max():.2f} mm")

    print("\nmirror asymmetry about x=0 (raw parse / after symmetrize_loop, mm):")
    for k, v in L.items():
        raw = dist_to_polyline(v * [-1.0, 1.0], v).max()
        s = symmetrize_loop(v)
        sym = dist_to_polyline(s * [-1.0, 1.0], s).max()
        print(f"  {k}: {raw:.6f} / {sym:.6f}")
        assert raw < 0.01, f"{k}: coin.svg loop is not mirror-symmetric"

    print("\nvalidation OK")
