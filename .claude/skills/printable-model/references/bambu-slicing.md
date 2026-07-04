# Bambu Studio slicing notes (X2D, PLA)

## Orientation & adhesion
- Print with the flat bed face down (usually as-modeled in this repo). No supports
  for parts designed to be support-free.
- Skip the brim when the bed face is large; add one only for tall/tippy parts or
  small footprints.

## Time levers — know what actually helps
Tall thin parts are **cooling-gated**: each small layer is held to a minimum layer
time so the plastic can set before the next layer lands. So the printer often
*waits* per layer rather than being speed-limited. The real levers:
1. **Fewer layers** — increase layer height (e.g. 0.24 → 0.28mm). Biggest win, and
   for a functional part the coarser finish is usually irrelevant.
2. **Batch copies** — printing N on one plate barely raises total time, because
   layers cool while the head works on the others. Per-part time drops sharply.
   Ideal when you need several of the same thing.
3. Trimming minimum-layer-time / raising fan — modest, with minor quality risk on
   small tips and steep overhangs.

**Lowering infill or wall count does NOT speed up a cooling-gated part** — the
layer-time floor stays put. Lower infill for material savings, not for time.

## Quality
- Top/bottom surface pattern: **Monotonic** — uniform and well-sealed. Use
  Concentric only for a round *decorative* top (it risks a center pinhole).
- Ironing gives a glassy top but adds a slow extra pass — skip unless finish
  matters more than time.
- Strength comes from perimeters and fillets, not infill percentage.

## Quick confirm
Slice, open the preview, and look at per-layer time up a tall feature. If those
layers are all pinned at the same few-second value, it's cooling-gated — reach for
levers 1 and 2 above.
