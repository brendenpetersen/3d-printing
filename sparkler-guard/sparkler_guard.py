# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["cadquery==2.5.2", "trimesh", "numpy", "scipy", "networkx", "manifold3d"]
# ///
"""Parametric sparkler guard for kids — FDM-printable, single piece.

Modeled in print orientation: guard disc flat on the build plate (Z=0),
handle rising up from its center. In use it's flipped: handle down,
disc shielding the hand, sparkler sticking up out of the disc face.

Grip textures (each behind its own flag):
  - Hourglass waist: the shaft necks down smoothly mid-grip.
  - Helical (spiral) ribs: rounded ribs spiraling up the shaft, following
    the waist if enabled, fading into the surface at the ends.

Usage:
  uv run sparkler_guard.py            # one model per the flags below
  uv run sparkler_guard.py --combos   # all waist/helix combinations
"""

import math
import os
import sys
import tempfile

import cadquery as cq
import trimesh

# ---------------------------------------------------------------------------
# Parameters (mm)
# ---------------------------------------------------------------------------
DISC_DIAMETER = 90.0      # guard disc diameter
DISC_THICKNESS = 2.2      # guard disc thickness

HANDLE_DIAMETER = 15.0    # handle diameter
HANDLE_HEIGHT = 80.0      # total handle height INCLUDING the domed end
FILLET_RADIUS = 6.0       # strength fillet where handle meets disc (load spreader)

# Sparkler socket: tapered blind hole "drilled" from the disc face into
# the handle. Wide at the opening, narrow at the bottom, so any stick in
# the 2.8-3.2mm range wedges tight somewhere along the depth.
SPARKLER_DIAMETER = 3.0   # nominal stick diameter (reference only)
HOLE_ENTRY_DIAMETER = 3.6  # at the disc face (FDM holes shrink ~0.2-0.3mm)
HOLE_TIP_DIAMETER = 2.8    # at the bottom of the hole
HOLE_DEPTH = 30.0          # penetration from the disc face

# Countersink lead-in at the opening: easy to aim, kills elephant's foot.
COUNTERSINK_DIAMETER = 6.0
COUNTERSINK_DEPTH = 1.5

# --- Grip texture: hourglass waist -----------------------------------------
WAIST_ENABLED = True
WAIST_MIN_DIAMETER = 13.0  # shaft diameter at the narrowest point mid-grip

# --- Grip texture: helical (spiral) ribs ------------------------------------
HELIX_ENABLED = True
HELIX_RIB_COUNT = 2        # ribs equally spaced around the shaft
HELIX_TURNS = 2.0          # full revolutions over the rib length
HELIX_RIB_DIAMETER = 2.5   # rib cross-section (round)
HELIX_RIB_SINK = 0.4       # rib center embedded this far below the surface
                           # (protrusion = rib radius - sink)
HELIX_END_MARGIN = 2.0     # rib keep-out from fillet top / dome base
HELIX_FADE_LENGTH = 5.0    # ribs submerge into the shaft over this length

# ---------------------------------------------------------------------------
# Derived
# ---------------------------------------------------------------------------
SHAFT_RADIUS = HANDLE_DIAMETER / 2.0
DOME_RADIUS = SHAFT_RADIUS
CYLINDER_HEIGHT = HANDLE_HEIGHT - DOME_RADIUS  # dome counts toward total height
DOME_BASE_Z = DISC_THICKNESS + CYLINDER_HEIGHT
GRIP_START_Z = DISC_THICKNESS + FILLET_RADIUS  # waist window: above the fillet
GRIP_END_Z = DOME_BASE_Z                       # ... up to the dome base

assert CYLINDER_HEIGHT > 0, "Handle too short for its diameter's dome"
assert HOLE_DEPTH < DOME_BASE_Z, "Hole would reach the dome"
assert WAIST_MIN_DIAMETER > HOLE_ENTRY_DIAMETER + 4, "Waist too thin around socket"


def surface_radius(z: float, waist: bool) -> float:
    """Shaft outer radius at height z (the waist is a smooth sin^2 dip)."""
    if not waist or not (GRIP_START_Z < z < GRIP_END_Z):
        return SHAFT_RADIUS
    depth = (HANDLE_DIAMETER - WAIST_MIN_DIAMETER) / 2.0
    u = (z - GRIP_START_Z) / (GRIP_END_Z - GRIP_START_Z)
    return SHAFT_RADIUS - depth * math.sin(math.pi * u) ** 2


def make_body(waist: bool) -> cq.Workplane:
    """Disc + junction fillet + shaft + dome as ONE revolved half-profile.

    The waist is axisymmetric, so it lives in this profile and the whole
    part revolves as one solid — no boolean unions (OCC's fuse is flaky
    with coplanar contact faces and revolved solids' axis vertices). Only
    the helix, which isn't axisymmetric, is unioned on.
    """
    f = FILLET_RADIUS
    top_z = DOME_BASE_Z + DOME_RADIUS
    profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(DISC_DIAMETER / 2, 0)
        .lineTo(DISC_DIAMETER / 2, DISC_THICKNESS)          # disc rim
        .lineTo(SHAFT_RADIUS + f, DISC_THICKNESS)           # disc top, to fillet
        .threePointArc(                                     # concave fillet
            (
                SHAFT_RADIUS + f - f / math.sqrt(2),
                DISC_THICKNESS + f - f / math.sqrt(2),
            ),
            (SHAFT_RADIUS, GRIP_START_Z),
        )
    )
    if waist:
        # Fine polyline (not a spline): revolving a spline whose start tangent
        # isn't exactly vertical bulges past the fillet endpoint and yields an
        # invalid, self-intersecting solid. A dense polyline stays manifold.
        n = max(120, int((GRIP_END_Z - GRIP_START_Z) / 0.25))
        for i in range(1, n + 1):
            z = GRIP_START_Z + (GRIP_END_Z - GRIP_START_Z) * i / n
            profile = profile.lineTo(surface_radius(z, True), z)
    else:
        profile = profile.lineTo(SHAFT_RADIUS, GRIP_END_Z)  # straight shaft
    profile = (
        profile.threePointArc(                              # dome
            (
                DOME_RADIUS / math.sqrt(2),
                DOME_BASE_Z + DOME_RADIUS / math.sqrt(2),
            ),
            (0, top_z),
        )
        .close()
    )
    return profile.revolve(360, (0, 0, 0), (0, 1, 0))


def make_rib(theta0: float, waist: bool) -> cq.Workplane:
    """One helical rib swept along the shaft surface, fading in/out at the ends."""
    z0 = GRIP_START_Z + HELIX_END_MARGIN
    z1 = GRIP_END_Z - HELIX_END_MARGIN
    rib_r = HELIX_RIB_DIAMETER / 2.0
    n = 100
    pts = []
    for i in range(n + 1):
        u = i / n
        z = z0 + (z1 - z0) * u
        theta = theta0 - 2 * math.pi * HELIX_TURNS * u
        # Submerge the rib center by an extra rib radius near the ends so the
        # blunt sweep caps are buried inside the shaft (smooth fade-in).
        d_end = min(u, 1 - u) * (z1 - z0)
        fade = 0.0
        if d_end < HELIX_FADE_LENGTH:
            fade = 0.5 * (1 + math.cos(math.pi * d_end / HELIX_FADE_LENGTH))
        radial = surface_radius(z, waist) - HELIX_RIB_SINK - fade * rib_r
        pts.append(cq.Vector(radial * math.cos(theta), radial * math.sin(theta), z))

    path_edge = cq.Edge.makeSpline(pts)
    path = cq.Workplane("XY").newObject([cq.Wire.assembleEdges([path_edge])])
    tangent = (pts[1] - pts[0]).normalized()
    profile_plane = cq.Plane(origin=pts[0], normal=tangent)
    return cq.Workplane(profile_plane).circle(rib_r).sweep(path, isFrenet=True)


def build(waist: bool, helix: bool):
    """Return (body_solid, [rib_solids]).

    The body (disc, fillet, waisted shaft, dome, socket) is a clean
    axisymmetric solid built in OCC. The helix ribs are returned separately
    because OCC's boolean fuse silently no-ops where a Frenet-swept rib
    grazes the faceted waist surface — they're unioned onto the body at the
    mesh level (manifold3d) in export(), which is exact and robust.
    """
    body = make_body(waist)

    # Tapered sparkler socket, cut from the plate face (Z=0) upward
    socket = cq.Solid.makeCone(
        HOLE_ENTRY_DIAMETER / 2,  # radius at Z=0 (disc face)
        HOLE_TIP_DIAMETER / 2,    # radius at hole bottom
        HOLE_DEPTH,
    )
    body = body.cut(cq.Workplane("XY").add(socket))

    # Countersink lead-in
    countersink = cq.Solid.makeCone(
        COUNTERSINK_DIAMETER / 2,
        HOLE_ENTRY_DIAMETER / 2,
        COUNTERSINK_DEPTH,
    )
    body = body.cut(cq.Workplane("XY").add(countersink))

    ribs = (
        [make_rib(2 * math.pi * k / HELIX_RIB_COUNT, waist) for k in range(HELIX_RIB_COUNT)]
        if helix
        else []
    )
    return body, ribs


def _to_watertight_mesh(shape: cq.Workplane) -> trimesh.Trimesh:
    """Tessellate a solid and stitch its seams into a watertight mesh.

    CadQuery tessellates each B-rep face independently, which can leave
    unstitched seam edges — merging coincident vertices closes them.
    """
    fd, path = tempfile.mkstemp(suffix=".stl")
    os.close(fd)
    try:
        cq.exporters.export(shape, path, tolerance=0.01, angularTolerance=0.1)
        mesh = trimesh.load(path)
    finally:
        os.unlink(path)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.merge_vertices()
    trimesh.repair.fill_holes(mesh)
    trimesh.repair.fix_normals(mesh)
    return mesh


def export(built, basename: str) -> None:
    body, ribs = built
    mesh = _to_watertight_mesh(body)
    if ribs:
        parts = [mesh] + [_to_watertight_mesh(r) for r in ribs]
        mesh = trimesh.boolean.union(parts, engine="manifold")
    assert mesh.is_watertight, f"{basename}: mesh not watertight after union"
    assert mesh.body_count == 1, f"{basename}: {mesh.body_count} disconnected bodies"
    mesh.export(f"{basename}.stl")
    print(f"  wrote {basename}.stl  ({mesh.volume / 1000:.1f} cm3)")


# (waist, helix)
COMBOS = {
    "plain": (False, False),
    "waist": (True, False),
    "helix": (False, True),
    "waist_helix": (True, True),
}

if __name__ == "__main__":
    taper_deg = math.degrees(
        math.atan(((HOLE_ENTRY_DIAMETER - HOLE_TIP_DIAMETER) / 2) / HOLE_DEPTH)
    )
    print(f"Disc:    Ø{DISC_DIAMETER} x {DISC_THICKNESS} mm")
    print(f"Handle:  Ø{HANDLE_DIAMETER} x {HANDLE_HEIGHT} mm (dome R{DOME_RADIUS})")
    print(f"Fillet:  R{FILLET_RADIUS} mm at the junction")
    print(
        f"Socket:  Ø{HOLE_ENTRY_DIAMETER} -> Ø{HOLE_TIP_DIAMETER}, "
        f"{HOLE_DEPTH} mm deep ({taper_deg:.2f} deg/side taper)"
    )
    if "--combos" in sys.argv:
        print(f"Helix: {HELIX_TURNS} turns")
        for name, (waist, helix) in COMBOS.items():
            print(f"Building {name} (waist={waist}, helix={helix})...")
            export(build(waist, helix), f"sparkler_guard_{name}")
    else:
        print(f"Building waist={WAIST_ENABLED}, helix={HELIX_ENABLED}")
        export(build(WAIST_ENABLED, HELIX_ENABLED), "sparkler_guard")
