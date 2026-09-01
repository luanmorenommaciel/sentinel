# Design system — flow UI

> Recorded from the built world, not from intentions. Every value here is in
> `src/flow_ui/static/app.css`; if the two disagree, the CSS is right and this file is stale.

## The world

**A flight-control console, etched onto a circuit board.**

The ground is a mission-control readout: phosphor on near-black, scanlines, everything in one
monospace, every figure a channel. Onto it is grafted the discipline of a printed board —
traces routed at 45°, a via at every junction, and a bloom on whatever carries current.

The bloom is not borrowed. **A real phosphor glows**; it is the one thing the board world
lends that already lived in this one. Nothing else came across — not the cyan, not the
magenta. Taking those would have made this the board world with a different name.

**What it deliberately is not**: a dashboard of equal cards. Six tiles of the same weight say
nothing about what to look at, which is what the first version did and why it was replaced.

## Two palettes, one world

Every rule reads a **role**, never a colour. `[data-world]` on the root swaps six values.
This is the whole reason the switch costs one attribute instead of a second stylesheet.

| Role | Command | Substrate | Job |
|---|---|---|---|
| `--bg` | `#080A07` | `#04060B` | the ground |
| `--pri` | `#7FE04A` | `#22D3EE` | flow, alive, stored |
| `--sec` | `#FFB000` | `#FFC53D` | attention, batch, selection |
| `--ter` | `#CFE8C0` | `#F0ABFC` | the second lane |
| `--alarm` | `#FF4A3D` | `#FF5C7A` | loss, and only loss |
| `--txt` | `#CFE8C0` | `#C3D6E6` | reading |

**The alarm is the one that does not port.** `#FF4A3D` interrupts against phosphor and amber;
against cyan and magenta a pure red *competes* instead — magenta is already warm. Substrate
shifts it toward pink. Same role, tuned value. A naive hue swap would have degraded one of the
two palettes and nobody would have been able to say why.

**Colour never carries a state alone.** Every status also has a word: the mode chip prints
`stream`/`batch`/`idle`, the health boxes are labelled `STORED`/`REJECTED`/`DROPPED`, and the
legend names every particle it colours.

## The switch has no words

Green to the left, blue to the right; the knob is `--knob`, which is `--pri`. **The colour is
the label.** Naming the palettes in the control would have put two proper nouns in a header
that is otherwise all data. The choice persists in `localStorage`, wrapped in try/catch — a
private window that throws must not take the page down with it.

## Type

**IBM Plex Mono, one family, everywhere.** A console has one voice. Uppercase with
`letter-spacing: .12–.15em` for labels; `font-variant-numeric: tabular-nums` on every figure
that sits in a column, so a changing digit never reflows its neighbours.

IBM Plex Sans appears only in prose that is not part of the instrument.

## The bloom is exclusive to what is alive

`filter: url(#bloom)` is applied to **one group**: the particles and the batch blocks. Nodes
stay matte.

If everything glows, the glow stops meaning anything. The eye goes to what moves because
nothing else asks for it. With no traffic there are no haloes and the board reads as at rest —
a state that needs no label.

## Semantic zoom, and its one obligation

Level 0 is three boxes. Opening one changes what a particle **means**: at the overview a dot
is `QUANTUM = 100` signals; inside, it is one trace.

That is a legitimate move, and it is only legitimate **because the legend is rebuilt on every
level change**. The strip along the bottom is not decoration — it is the contract between the
picture and the reader. Without it, someone counts dots at one level and quotes a figure from
another.

The overview caps at `MAX_DOTS = 14` per lane. Beyond that the eye reads a line, not a count,
so more dots would be a lie dressed as detail.

## Nodes

- **`.hit`** — a clickable node. `pointer-events` is `all` on the group and on the rect,
  and **`none` on every child**, so a click on a label can never land on a different target
  than a click on the box. Hover brightens the border and the fill; `:active` sinks it.
  **Hover styling uses `>`, and an open container is exempt from it.** As a descendant
  selector it matched every `.nd` inside a container, so pointing at one table lit that
  table, its neighbours and the box around them at once. Worse, `.hit:hover .nd` sets
  `fill: var(--panel)` and outranks `.nd.open{fill:none}` on specificity — so hovering
  anywhere inside an open container re-filled it opaque and it painted over the pipes
  running behind it, which is the exact thing `fill:none` is there to prevent.
- **One channel each.** The border is INTERACTION — hover and selection — and the mark beside
  the name is STATE. They were briefly the same channel, in the same `--sec`, and a warning
  node became indistinguishable from a pointed-at one, which is how a pointer stops meaning
  anything.
- **`.chrome`** — open, the clickable target is the header strip, not the whole interior.
  The full-size rect covers everything drawn inside the container, so leaving it
  hit-testable meant the pointer was over the container even while aiming at something
  inside it. Closed, the box is a card and the card is the button.
- **`.pw` / `.pb`** — a pipe: a casing, and inside it a bore painted darker than the stage
  so it reads as hollow. The bore also hides the grid, so the channel looks enclosed rather
  than drawn on top of the board. Signals travel the bore's centreline, which is why a dot
  reads as moving *through* a channel instead of sliding along a wire.
  **Only the flow is piped.** Every outcome tap stays a thin line, and that is the point:
  if the pipe is the flow, then failing is falling OUT of it, so the two have to be
  different objects rather than the same object at two weights.
  Two gauges, both sized by what travels them, not by taste. **13/10** for signals: the
  floor is the dot's 6.4px core, which scraped the walls at a 9px bore and reads as bursting
  out; 10px leaves 1.8px a side, and the bloom halo may spill where the core may not.
  **24/21** for the `buffer → bronze` trunk, because the thing travelling it is an 18px
  batch sphere, not a dot. Wall thickness is `(casing - bore) / 2` — 1.5px in both, so only
  the bore grows, because only the payload did. Wider than this was tried and cost two things: ORIGIN's
  eight-edge topology read as tangled plumbing, and the collector's 32px internal hops
  became plugs rather than runs.
- **`.rim`** — a pipe mouth: a short lip ACROSS the run, wider than the casing it caps, and
  rectangular. **One rule, no exceptions: a lip marks where a pipe meets a box, any box.**
  It first appeared at only four of the twenty-odd junctions — the inter-container ones —
  which read as arbitrary rather than as meaning anything. It was a circle first, which read as a bead threaded onto a wire — the one
  shape that argues against the pipe it is supposed to cap. Every mouth on this board sits
  where a horizontal run meets a box, so the lip is a tall narrow rect; it is derived from
  the casing, so the trunk's lip is the bigger one for the same reason its bore is.
  Replaces the old junction pad and keeps its job — you can see where a connection begins
  and ends.
- **45° routing** — edges turn at 45°, never on a Bézier. A diagram routed like a board reads
  as something fabricated rather than sketched. Pipes inherit it, with round joins so a
  corner does not open a seam in the casing.
  **An elbow needs room to turn.** A 45° corner consumes `rise` worth of horizontal run on
  top of its stubs; given less, it lands past the target and the last leg doubles back,
  drawing a stray that runs out from under the node it was meant to reach. `route` now
  falls through to the orthogonal `fan` shape whenever `rise > span - 48`. ORIGIN's columns
  sit 52px apart, so every edge there that changes row was overshooting — one by 84px,
  straight through `gcs-processed-bucket`. It had been invisible for as long as the edges
  were hairlines.
- **A fan's legs are one casing apart** — edges leaving a node share a port, so their
  vertical legs must not share a column too. Staggered per source; the clamp that keeps the
  last chamfer landable is also what caps a readable fan at about three legs per node.
- **`.cue`** — `▸ OPEN` in `--sec`. A node that can be opened says so in words, not by
  waiting for a hover that a touch device will never send.

## What the picture refuses to say

**Three lanes in, one lane out.** The graph narrows after the buffer because the metrics do:
from there on the collector labels everything `signal="all"`, since one mixed batch is flushed
and no per-type boundary survives. Drawing three lanes all the way to ClickHouse would be
inventing a distinction the pipeline does not have.

**Outcome is drawn per TYPE where the metric says so, and never per trace.** The line falls
at the buffer, not at the collector: `signals_rejected_total{signal,reason}` does know which
of the three types failed and how, so a contract rejection leaves `validate` in that type's
own colour. `storage_signals_total` does not — it is `signal="all"` — so a dropped batch falls
as the mixed sphere, ringed. Below type there is nothing: which *trace* was rejected is not
measured anywhere, and colouring one red would be fabricating a fact.

**Declared and observed sit side by side.** In the origin view the left of each node is Pod 1's
`topology.yaml`; the right is what actually landed in bronze. They are drawn together on
purpose — the two disagreeing is itself the finding.

**Three tables are named as empty.** `otel_metrics_histogram`, `_exponential_histogram` and
`_summary` are permanently zero under contract v1.0.0. Named, they read as a decision; unnamed,
as a failure.

## Figures before motion

Every number is rendered into the HTML by the server before a script runs. The canvas
illustrates figures the page already printed; a blocked or slow script costs the motion, never
the reading. A test pins this.

**Density is spread, not a prefix.** A lane allocates its dots once and afterwards only fades
them in and out, and *which* ones it fades matters twice over. Lighting the first `n` puts
every visible dot in the first `n / poolSize` of the cycle — one clump, then an empty stretch,
so a steady lane reads as a burst and a gap. Lighting every `poolSize / n`-th fixes the spread
but reshuffles the whole set whenever the rate wobbles, which it does every tick, so half the
lane fades out and back once a second. The order is built by farthest-point insertion, whose
prefixes are both evenly spread *and* nested: a rate change adds or removes dots without
disturbing the ones already in flight.

## Layout

**The drawing fits the window; the window does not fit the drawing.** The stage carried
`aspect-ratio: 1000/440` with `height: auto`, so its height came from its WIDTH and the screen
was never consulted: on a 32" monitor it asked for more height than the window had and the
whole page scrolled, while half-width left the bottom half empty. The page is now a column
filling `100dvh` and the canvas takes the remainder. Tiles fall to `minmax(112px, 1fr)`.
`prefers-reduced-motion` removes `animateMotion` entirely; the graph and every figure survive.

**`fit()` measures what is drawn, not the viewBox.** `layout()` reported a flat `height: 440`
while the closed boxes occupy about 200 of it, so the graph sat small in the middle of empty
space; and the datasheet, which is not a box, was missing from the bounds entirely and ran off
the right edge whenever bronze was open. Bounds now come from the real extent, `fit()` centres
on it, and it may scale UP to `FIT_MAX` — a graph capped at 1× leaves a large screen mostly
empty.

**It refits when the drawing changes SIZE, and only then.** On window resize, and on opening a
box or selecting a service — deliberate acts, with an expectation of seeing the result. Not on
every repaint: a mode change repaints too, and refitting there would throw away a pan the
reader had just made.

**Height a box grows into is not height its contents may use.** Selecting a service grows
ORIGIN by 138px to make room for the signal panel, and the node grid — sized as
`(height − 56) / rows` — spread itself across the taller box and put its lower rows directly
under the panel, which then covered the very nodes it describes. The grid now lays out in
`gridH`, the height the container has *without* the panel; the extra belongs to the panel
alone. Any future panel that grows a container needs the same separation.

## Assets

The stylesheet is served as `/static/app.css?v=<mtime>`, stat-ed per render — no build step, no
restart, and no way for two pages to disagree about which CSS they are wearing.

Type comes from Google Fonts. **Without a network the fallback stack is real** and the page
stays legible, but the console voice is lost. Self-host before showing this anywhere without
internet.

---

## Provenance

Direction chosen from five candidates rendered as live mockups, then narrowed through six
variants of the winner and a navigable zoom prototype. The cross with the board world was the
owner's call after seeing both. **Those mockups were deleted when V1 closed** — the decisions
they carried, with palettes and trade-offs, survive in
[`DESIGN-DIRECTIONS.md`](DESIGN-DIRECTIONS.md); the animated renderings do not.

**No `impeccable` finish-review or documenter subagent was run**; this file was written
in-thread from the built CSS.

**Not yet verified visually by anyone but the owner in a browser.** Headless capture is
unavailable here: the page holds an SSE connection open, so Chrome never reaches network-idle
and `--screenshot` hangs. Structure, JS execution and served figures are verified by test; the
*look* is not.
