# Egg coin

Parametric generators for an egg-shaped coin with a curved-diamond (star) hole,
built from `coin.svg` (the single geometry source; drawn symmetric about the
egg's long axis). Default print size: **55 mm tall** (41.2 × 55 × 3.94 mm).
`single/coin_reference.stl` is the faithful right-angle-lip extrusion of the
current SVG (the up-to-date replacement for the stale original `coin.glb`).

`coin_outlines.py` is the shared library: SVG outline extraction, offsets,
and watertight mesh-patch helpers. Each generator is a `uv` inline script;
fit-critical clearances are parameters at the top — tune and rerun, never
edit STLs.

## Current versions

| Version | Dir | Pieces | Regenerate | Notes |
|---|---|---|---|---|
| Single | `single/` | 1 | `uv run coin_single.py` | One color, prints upright. Lip chamfer angle is the main knob (45 = support-free, 90 = original extrusion; default 60). `--flat-base` for bed adhesion. |
| Reference | `single/coin_reference.stl` | 1 | `uv run coin_single.py --chamfer-angle 90 --out coin_reference` | Faithful right-angle-lip extrusion (replaces `coin.glb`). Reference/display model — as-is it has 90° overhang ceilings and needs supports; for an actual single-color print use `coin_single.stl`. |
| Snap | `snap/` | 4 STLs (face_half ×2) | `uv run coin_snap.py` | Two color. Monolithic teardrop-groove rims (seamless edge + bore); two peg-registered textured face halves tire-mount into the egg groove; star snaps on at its N/S knobs. Only glue: between the face halves. |
| Glue | `glue/` | 5 STLs (face_half ×2) | `uv run coin_glue.py` | Two color, full glue-up. Same as Snap except the star: a bottom-lip + hole-tube base with a rebated top-lip cap — seamless bore and *both* star lips textured. Most seamless version. |
| Sandwich | `sandwich/` | 3 STLs (face_half, star_half ×2) | `uv run coin_sandwich.py` | Two color, **no glue, zero-force, fully reversible**. Star halves drop lip-first through oversized face holes; base flanges are trapped in face recesses; the egg rim (identical to Snap's) clamps the stack. Trades: a hairline ring (0.02 mm drawn, snug) around each star lip, bore mid-seam. All flat faces (coin faces + both star lips) are bed-textured. |

**Snap vs Glue — the only difference is the star.** Snap's star is one piece
and serviceable but its two lips are print-top/bed finish (one each); Glue's
star is two glued pieces with both lips bed-textured and a hairline seam high
inside the bore. Face halves are **self-mating** (integrated pegs + mirrored sockets: one model, flipped, plugs into itself — no loose pegs). Both versions also ship a **`face_solid`** STL — a
full-thickness one-piece face (no pegs, no face glue) for lazy builds and fit
testing; its downside is one non-textured side.

## Legacy (kept for reference, superseded at 55 mm)

| Version | Dir | Regenerate | Why superseded |
|---|---|---|---|
| Snap-peg (clamshell) | `snappeg/` | `uv run coin_snappeg.py` | Hidden snap posts + sockets; physically needs a ~190 mm+ coin. Built at 223.5 mm. Still the only fastener-based design. |
| 3-piece (solid face) | `legacy_snapring/`, `legacy_gluefit/` | `uv run coin_3piece_legacy.py [--joint glue]` | Fewest pieces, but the one-piece face can't be bed-textured on both sides; gluefit's open rabbets leave back-side seam rings. |
