/* Sentinel flow — one canvas, expanded in place.
 *
 * The pipeline is a single graph that never gets replaced. Opening a box grows it and
 * reveals its internals; the boxes beside it stay where they are and the particles keep
 * flowing through. An earlier version swapped the whole stage for a detail view, which
 * threw away the context at exactly the moment it was needed.
 *
 * Two invariants hold the motion together:
 *
 *   1. Particles are allocated ONCE per structural render and afterwards only faded in
 *      and out. Throughput changes on nearly every tick — a steady 730/s samples as 171,
 *      85, 166… because the poll interval drifts against the producer's — so rebuilding on
 *      rate would restart the animation once a second.
 *   2. Pan and zoom write a transform attribute. They never re-render, so dragging the
 *      canvas cannot interrupt anything in flight.
 *
 * What the collector can and cannot tell us, and where the line falls: at the gRPC
 * boundary `signals_rejected_total` is labelled by BOTH `signal` and `reason`, so a
 * rejection knows which of the three types it was — that is why a contract failure falls
 * in its own colour. From the BUFFER onward every metric is labelled signal="all", because
 * the exporter merges the three types into one batch, so a dropped batch can only be drawn
 * as what it is: a mixed sphere, ringed to say it was lost. Colouring that one would
 * invent a fact.
 */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const VW = 1000, VH = 440;      // viewBox — the window, not the canvas
  const QUANTUM = 100;            // signals per dot at the overview
  const MAX_DOTS = 14;            // per lane; beyond this the eye reads a line, not a count
  const GAP = 110;                // between columns
  const SHEET_W = 320;            // the bronze datasheet, which layout() must make room for

  //: Collapsed and expanded footprints. Layout is computed from these, so a box growing
  //: pushes its neighbours rather than overlapping them.
  const SIZE = {
    origin:    { closed: [212, 196], open: [742, 248], openSel: [742, 386] },
    collector: { closed: [252, 152], open: [500, 344] },
    bronze:    { closed: [176, 136], open: [318, 252] },
    //: SILVER open has no fixed size — `silverSize()` measures the graph. Add a model or
    //: a view to the DDL and the box grows to hold it.
    silver:    { closed: [186, 136] },
  };

  let graph = null, snap = null, table = null, model = null;
  //: A selected service filters what the graph reports about bronze. It cannot filter the
  //: live rates: `sentinel_signals_ingested_total` carries a `signal` label and no service
  //: label, so per-service throughput simply does not exist upstream of ClickHouse. The
  //: legend says so rather than letting the lanes imply otherwise.
  let service = null;
  const open = { origin: false, collector: false, bronze: false, silver: false };
  let painted = "", pools = {};
  //: Where an open box's rows meet its edge, so the BRONZE ⇒ SILVER strands can be drawn
  //: after both bodies have run. Reset on every render; empty whenever a box is closed.
  let ports = { bronze: {}, silver: {} };
  const view = { k: 1, x: 0, y: 0 };   // viewport transform
  let root = null;                      // the <g> everything pans inside
  let vias = null;                      // the layer mouths are drawn into

  /* ── helpers ───────────────────────────────────────────────── */
  const fmt = (n) => {
    n = Number(n) || 0;
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + "k";
    return Math.abs(n) >= 10 || n === Math.trunc(n) ? String(Math.round(n)) : n.toFixed(1);
  };
  const el = (tag, attrs = {}, text) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
    if (text != null) n.textContent = text;
    return n;
  };
  /** A branch leaving a stage downward. Kept separate from `route` because a branch
   *  target often sits to the LEFT of its source, and a left-to-right router asked to go
   *  backwards folds its elbow over itself — which drew a stray triangle under the
   *  collector. This one descends first, then turns once at 45°. */
  const branch = (x1, y1, x2, y2) => {
    const dx = x2 - x1, turn = y2 - Math.abs(dx);
    if (turn <= y1) return `M${x1} ${y1} L${x2} ${y2}`;
    return `M${x1} ${y1} L${x1} ${turn} L${x2} ${y2}`;
  };
  /** Truncate to a monospace column budget, so a long name cannot run into a figure. */
  const clip = (t, n) => (t.length > n ? t.slice(0, n - 1) + "…" : t);
  /** A fan from one entry point to several rows stacked above and below it.
   *
   *  `route` cannot do this: it assumes the run is longer than the rise, and with a 20px
   *  channel and a 100px drop its elbow overshot the target and doubled back — which is
   *  what drew lines behind the table boxes. A fan needs a bus: a short stub, one vertical
   *  leg, then straight in. Corners are chamfered to keep the board language. */
  const fan = (x1, y1, x2, y2, stub = 26) => {
    const bx = x1 + stub, dy = y2 - y1;
    if (Math.abs(dy) < 2) return `M${x1} ${y1} L${x2} ${y2}`;
    const c = Math.min(9, Math.abs(dy) / 2, Math.max(0, x2 - bx));
    const dir = Math.sign(dy);
    return `M${x1} ${y1} L${bx - c} ${y1} L${bx} ${y1 + c * dir} `
         + `L${bx} ${y2 - c * dir} L${bx + c} ${y2} L${x2} ${y2}`;
  };
  /** An axis-aligned polyline with chamfered corners. `route`, `fan` and `branch` each
   *  bake in one shape; a return climbs a margin channel and turns three or four times,
   *  so it needs the legs stated outright. Corners are cut at 45° like everything else. */
  const poly = (pts, c = 8) => {
    let d = `M${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const [px, py] = pts[i - 1], [x, y] = pts[i], [nx, ny] = pts[i + 1];
      const a = Math.min(c, Math.hypot(x - px, y - py) / 2);
      const bq = Math.min(c, Math.hypot(nx - x, ny - y) / 2);
      const ax = x === px ? x : x - Math.sign(x - px) * a;
      const ay = y === py ? y : y - Math.sign(y - py) * a;
      const bx = nx === x ? x : x + Math.sign(nx - x) * bq;
      const by = ny === y ? y : y + Math.sign(ny - y) * bq;
      d += ` L${ax.toFixed(1)} ${ay.toFixed(1)} L${bx.toFixed(1)} ${by.toFixed(1)}`;
    }
    const last = pts[pts.length - 1];
    return d + ` L${last[0].toFixed(1)} ${last[1].toFixed(1)}`;
  };
  /** A run of pipe: two strokes over one geometry — a casing, and a bore inside it. The
   *  BORE carries the id, so `animateMotion` puts the dots on its centreline and they read
   *  as travelling through the channel rather than along a wire. `extra` selects the gauge
   *  ("trunk") and any marker the run needs. */
  const pipe = (parent, id, d, gauge = "", attrs = {}, w = null, tone = null) => {
    // `w` overrides the CSS gauge in user units, so an edge can be as thick as it carries.
    // The bore keeps a 1.5px wall on each side at every width, which is what makes a thin
    // pipe read as a thin pipe rather than as a line.
    //
    // As `style`, not as an attribute: `.pw{stroke-width:13}` is a stylesheet rule and a
    // presentation attribute loses to it, so the widths were computed correctly and every
    // pipe still rendered at its CSS gauge.
    const pw = w ? { style: `stroke-width:${w.toFixed(1)}` + (tone ? `;stroke:${tone}` : "") } : {};
    // The floor is on the WALL, never on the bore: `max(4, w - 3)` let the bore reach the
    // casing at w = 4, so the wall went to zero and the pipe rendered as a plain dark line.
    // Every gauge keeps the same 1.5px wall a pipe needs to read as one.
    const pb = w ? { style: `stroke-width:${Math.max(2, w - 3).toFixed(1)}` } : {};
    parent.append(el("path", { class: "pw " + gauge, d, ...pw }),
                  el("path", { class: "pb " + gauge, id, d, ...attrs, ...pb }));
  };
  /** A pipe mouth: a short lip ACROSS the run, wider than the casing it caps. Every mouth
   *  on this board sits where a horizontal run meets a box, so the lip is a tall, narrow
   *  rectangle. It used to be a circle, which read as a bead threaded on a wire — the one
   *  shape that argues against the whole pipe. Derived from the casing, so the trunk's lip
   *  is the bigger one for the same reason its bore is. */
  const mouth = (x, y, casing = 13) => {
    const h = casing + 7, w = casing >= 20 ? 8 : 6;
    vias?.append(el("rect", { class: "rim", x: x - w / 2, y: y - h / 2,
      width: w, height: h, rx: 2 }));
  };
  /** 45° routing: a board turns at an angle, never on a Bézier.
   *
   *  A 45° elbow needs `run` worth of horizontal room to make its turn, on top of the 24px
   *  stubs either side. Given less, the elbow lands PAST `x2` and the final leg doubles
   *  back — a stray line running out from under the node it was meant to reach. `fan`
   *  already documents this defect and routes around it locally; leaving `route` itself
   *  trapped meant the next caller walked into it, and ORIGIN did: its columns are 52px
   *  apart, so every edge that changes row overshot, one of them by 84px, straight through
   *  `gcs-processed-bucket`. Invisible as a hairline. Not invisible as a pipe. */
  const route = (x1, y1, x2, y2) => {
    const dy = y2 - y1, run = Math.abs(dy), span = x2 - x1;
    if (run < 1) return `M${x1} ${y1} L${x2} ${y2}`;
    if (run > span - 48) return fan(x1, y1, x2, y2, Math.max(18, span / 2));
    return `M${x1} ${y1} L${x1 + (span - run) / 2} ${y1} `
         + `L${x1 + (span + run) / 2} ${y2} L${x2} ${y2}`;
  };

  //: Where the three feeders land on whatever they enter. Spread wider than the old
  //: 0.28/0.5/0.72 because a pipe has width: on the 54px `receive` stage these sit 19px
  //: apart, which is one casing plus a hair. Tightening either number re-merges them.
  const ENTRY = [0.14, 0.5, 0.86];

  /* ── layout ────────────────────────────────────────────────── */
  function layout() {
    const CY = 220;
    const boxes = {};
    let x = 40;
    //: Silver sits close to bronze rather than a full GAP away, because nothing travels
    //: between them: the materialized views fire inside ClickHouse on the same insert that
    //: writes bronze. A long run would draw transport that does not happen.
    const DERIVE_GAP = open.bronze && open.silver ? 130 : 52;
    for (const id of ["origin", "collector", "bronze", "silver"]) {
      const key = !open[id] ? "closed"
        : (id === "origin" && service && SIZE[id].openSel) ? "openSel" : "open";
      const [w, h] = id === "silver" && open.silver ? silverSize() : SIZE[id][key];
      boxes[id] = { id, x, y: CY - h / 2, w, h };
      x += w + (id === "bronze" ? DERIVE_GAP : GAP);
    }
    // Signal lanes leave the origin container's right edge, not individual services: the
    // three types are a property of every service, not of any one of them.
    const o = boxes.origin, c = boxes.collector, b = boxes.bronze;
    o.out = [0.28, 0.5, 0.72].map((f) => [o.x + o.w, o.y + o.h * f]);
    // The node grid is laid out in the height the box has WITHOUT the signal panel. Selecting
    // a service grows the container by 138px to make room for that panel, and spreading the
    // nodes across the taller box pushed the lower rows straight underneath it — the panel
    // covered the very nodes it describes. The extra height belongs to the panel alone.
    o.gridH = SIZE.origin.open[1];

    // Stage geometry lives in the layout, not in the body renderer, so the lanes coming
    // from ORIGIN can land on `receive` and the lane leaving for BRONZE can start at
    // `buffer`. Terminating them on the container's edge was what made it look as though
    // data could enter any stage and any stage could write to bronze.
    const SW = 116, SH = 54, SGAP = 32;
    // Centred rather than left-anchored: the open box carries a return channel down each
    // margin, and a left-anchored row put 20px on one side and 68 on the other.
    const row = 3 * SW + 2 * SGAP;
    const sx = c.x + Math.max(20, (c.w - row) / 2);
    c.stages = ["receive", "validate", "buffer"].map((name, i) => ({
      name, x: sx + i * (SW + SGAP), y: c.y + 66, w: SW, h: SH,
    }));
    if (open.collector) {
      const first = c.stages[0], last = c.stages[2];
      c.in = ENTRY.map((f) => [first.x, first.y + first.h * f]);
      c.out = [last.x + last.w, last.y + last.h / 2];
    } else {
      c.in = ENTRY.map((f) => [c.x, c.y + c.h * f]);
      c.out = [c.x + c.w, c.y + c.h * 0.5];
    }
    b.in = [b.x, b.y + b.h * 0.5];
    // The real extent of what gets drawn, not the viewBox. `height: 440` was reported flat,
    // so `fit()` scaled the graph against the whole canvas while the closed boxes occupy
    // about 200 of it — on a tall window the graph sat small in the middle of empty space.
    const bs = Object.values(boxes);
    const y0 = Math.min(...bs.map((b) => b.y)), y1 = Math.max(...bs.map((b) => b.y + b.h));
    // The datasheet goes BELOW bronze, directly under the table it describes.
    //
    // To the right it landed exactly where SILVER now sits and covered it — a detail panel
    // over the nodes it is meant to explain, the third time that defect has reached the
    // reader. Past SILVER it cleared the overlap and cost more: at 320 wide it took the
    // canvas from 1080 to 1682 units, and `fit()` scales to the widest thing, so every box
    // on the board shrank to 58% to make room for a panel. Below bronze it is 320 against
    // bronze's own 318, so it adds no width at all — only height, on an arrangement that is
    // far wider than it is tall and had the room to spare.
    const sheet = open.bronze && table
      ? { x: boxes.bronze.x, y: boxes.bronze.y + boxes.bronze.h + 30, w: SHEET_W, h: 236 }
      : null;
    // SILVER's sheet sits under SILVER, on the same rule: a sheet exists only while its own
    // row is selected.
    // Height follows the content: an MV has no columns of its own, so a 236-tall panel to
    // hold three lines is mostly empty box.
    const mDoc = (graph?.silver_graph || {})[model];
    const mSheet = open.silver && model && mDoc
      ? { x: boxes.silver.x, y: boxes.silver.y + boxes.silver.h + 30, w: SHEET_W,
          h: mDoc.kind === "mv" ? 108
            : 108 + Math.ceil((mDoc.columns?.length || 0) / 2) * 13 }
      : null;
    // Not a box, so it was absent from these bounds and `fit()` scaled to an extent that
    // excluded it — the sheet ran off the canvas whenever bronze was open.
    const btm = [sheet, mSheet].filter(Boolean);
    const x1 = Math.max(x - GAP, ...btm.map((z) => z.x + z.w));
    return { boxes, sheet, mSheet, x0: 40, y0, width: x1 - 40,
             height: Math.max(y1, ...btm.map((z) => z.y + z.h)) - y0 };
  }

  /* ── particle pools ────────────────────────────────────────── */
  const flow = (parent, pathId, key, cls, dur = 2.4, r = 3.2, n = MAX_DOTS) => {
    const pool = [];
    for (let i = 0; i < n; i++) {
      const c = el("circle", { class: cls, r, opacity: 0 });
      const a = el("animateMotion", { dur: `${dur}s`, repeatCount: "indefinite",
        begin: `${((dur / n) * i).toFixed(2)}s` });
      a.append(el("mpath", { href: `#${pathId}` }));
      c.append(a); parent.append(c); pool.push(c);
    }
    pools[key] = pool;
  };
  //: The order in which a pool's dots light up, and it has to satisfy two things at once.
  //:
  //: `flow` staggers dot `i` by `(dur / poolSize) * i`, so lighting the FIRST `n` puts
  //: every visible dot in the first `n / poolSize` of the cycle: one clump, then an empty
  //: stretch. A steady 5-of-14 lane read as a burst, a gap, then the burst again — a
  //: rhythm the pipeline does not have. (Invisible while the lanes were hairlines; the
  //: bore made it plain.)
  //:
  //: But a modular stride, which does spread them, reshuffles the whole set when `n`
  //: changes — 5→6 shares only two of six indices — and the rate wobbles every tick, so
  //: half the lane faded out and back once a second.
  //:
  //: Farthest-point insertion gives both: every prefix is evenly spread around the cycle
  //: AND is a subset of the next, so a rate change adds or removes dots without
  //: disturbing the ones already in flight. Computed once per pool size.
  const ORDERS = {};
  const order = (p) => (ORDERS[p] ||= (() => {
    const out = [0];
    while (out.length < p) {
      let best = -1, bestGap = -1;
      for (let i = 1; i < p; i++) {
        if (out.includes(i)) continue;
        let d = p;
        for (const j of out) {
          const raw = Math.abs(i - j);
          d = Math.min(d, raw, p - raw);
        }
        if (d > bestGap) { bestGap = d; best = i; }
      }
      out.push(best);
    }
    return out;
  })());
  const show = (key, n) => {
    const pool = pools[key] || [], p = pool.length;
    if (!p) return;
    const on = new Set(order(p).slice(0, Math.max(0, Math.min(n, p))));
    pool.forEach((c, i) => c.setAttribute("opacity", on.has(i) ? 1 : 0));
  };

  //: The three signal types, in draw order. Every service emits all three and every
  //: internal hop carries all three, so an edge painted in one colour was saying that
  //: only logs travel it.
  const LANES = [["logs", "p1"], ["trace", "p2"], ["metrics", "p3"]];
  /** One pool per signal type on the same path, offset so the colours interleave rather
   *  than moving in lockstep. */
  const flow3 = (parent, pathId, keyBase, dur = 2.4, r = 3.2, n = 2) =>
    LANES.forEach(([name, cls], k) => {
      flow(parent, pathId, `${keyBase}-${name}`, cls, dur, r, n);
      // stagger each colour by a third of a slot so they do not overlap exactly
      (pools[`${keyBase}-${name}`] || []).forEach((c, i) => {
        const a = c.querySelector("animateMotion");
        if (a) a.setAttribute("begin", `${((dur / n) * i + (dur / n / 3) * k).toFixed(2)}s`);
      });
    });
  /** A batch, drawn as what it contains. The buffer flushes ONE mixed batch — the
   *  collector labels it `signal="all"` for exactly this reason — so an amber rectangle
   *  was naming a colour the payload does not have. Three sectors, one per signal type. */
  const batchBall = (r = 9, spin = 2.6, lost = false) => {
    // Two nested groups: `animateMotion` writes a transform on the outer one, so the spin
    // has to live on an inner group or the two would overwrite each other.
    const g = el("g", { class: "batch" });
    const inner = el("g");
    inner.append(el("animateTransform", { attributeName: "transform", type: "rotate",
      from: "0 0 0", to: "360 0 0", dur: `${spin}s`, repeatCount: "indefinite" }));
    g.append(inner);
    LANES.forEach(([, cls], i) => {
      const a1 = (i * 120 - 90) * Math.PI / 180, a2 = ((i + 1) * 120 - 90) * Math.PI / 180;
      inner.append(el("path", { class: cls,
        d: `M0 0 L${(r * Math.cos(a1)).toFixed(2)} ${(r * Math.sin(a1)).toFixed(2)} `
         + `A${r} ${r} 0 0 1 ${(r * Math.cos(a2)).toFixed(2)} ${(r * Math.sin(a2)).toFixed(2)} Z` }));
    });
    inner.append(el("circle", { r: r * .34, fill: "var(--bg)", opacity: .55 }));
    // A lost batch is still a batch. The ring says what happened to it without recolouring
    // what it contained — which is unknowable here, and the whole reason this shape exists.
    if (lost) g.append(el("circle", { class: "lost-ring", r: r + 3, fill: "none" }));
    return g;
  };
  /** A pool of mixed batches travelling a path, for the one outcome whose payload is a
   *  batch rather than a signal. Same fade-in contract as `flow`, so `show` drives it. */
  const flowBatch = (parent, pathId, key, dur = 1.8, r = 6, n = 2) => {
    const pool = [];
    for (let i = 0; i < n; i++) {
      const ball = batchBall(r, 2.2, true);
      ball.setAttribute("opacity", 0);
      const a = el("animateMotion", { dur: `${dur}s`, repeatCount: "indefinite",
        begin: `${((dur / n) * i).toFixed(2)}s` });
      a.append(el("mpath", { href: `#${pathId}` }));
      ball.append(a); parent.append(ball); pool.push(ball);
    }
    pools[key] = pool;
  };

  const dots = (rate) => rate <= 0 ? 0
    : Math.max(1, Math.min(MAX_DOTS, Math.round(Math.pow(rate / QUANTUM, .62) * 2.6)));

  /* ── per-service health, fused ─────────────────────────────
   *
   * V2.3. Contract and Watchers are separate boards, so the view people actually look at
   * knew nothing about either. This fuses every per-service source that exists into the
   * node itself.
   *
   * There are exactly two such sources and no more: `volume` (band verdict, plus the
   * buckets a producer was silent for while the estate kept receiving) and
   * `contract_violations` (rows it wrote missing a required key). Both keyed by service.
   *
   * What V2.3 also asks for and is NOT here: edge thickness by throughput and edge colour
   * by violation rate. Neither is measurable. ORIGIN's edges come from Pod 1's
   * `topology.yaml` — they are DECLARED dependencies, not measured flows — and nothing in
   * the collector or in bronze counts anything per edge. Drawing them would be inventing
   * the one thing the picture would then be asserting.
   */
  /** Producers writing into bronze that Pod 1 never declared.
   *
   *  Found while building the per-node health and it changes what that health is worth: the
   *  DAG draws the DECLARED topology, so a producer nobody declared has no node to carry a
   *  state — and here the only two producers with problems were exactly those. Undeclared is
   *  itself the finding, and it correlates: nothing declared it, so nothing told it the
   *  contract, so it is missing required keys. Reported apart from the graph because it has
   *  no position in the graph. */
  const undeclared = () => {
    const declared = new Set((graph?.topology?.nodes || []).map((n) => n.service));
    const seen = new Set([...(snap?.lineage || []).map((r) => r.service),
                          ...(snap?.volume || []).map((r) => r.service),
                          ...(snap?.contract_violations || []).map((r) => r.service)]);
    return [...seen].filter((n) => n && !declared.has(n)).sort();
  };

  //: Silence has to be MATERIAL before it counts. `absent > 0` fired on every producer:
  //: a run's first and last minute are partial, so everyone misses a bucket at the edges,
  //: and seven of seven nodes went amber over 1 of 14. A share with a floor of two buckets
  //: keeps the edges quiet and still catches a producer that stopped — measured here,
  //: `third-party-agent` at 13 of 14.
  const ABSENT_SHARE = 0.1, ABSENT_MIN = 2;

  const HRANK = { fail: 0, warn: 1, unmonitored: 2, unknown: 3, passing: 4 };
  const HTONE = { fail: "var(--alarm)", warn: "var(--sec)", unmonitored: "var(--dim2)",
                  unknown: "var(--dim)", passing: "var(--pri)" };

  function serviceHealth(name) {
    const v = (snap?.volume || []).find((r) => r.service === name);
    const c = (snap?.contract_violations || []).find((r) => r.service === name);
    let state = v ? v.state : "unknown";
    const worse = (s) => { if (HRANK[s] < HRANK[state]) state = s; };
    const why = [];
    if (v && (v.state === "warn" || v.state === "fail")) why.push(`volume ${v.z}σ off median`);
    // Silence is not a band violation — a producer sitting at its median while writing
    // nothing at all would read as passing — so it raises the state on its own axis.
    const silent = v && v.absent >= ABSENT_MIN && v.absent >= v.estate * ABSENT_SHARE;
    if (silent) { worse("warn"); why.push(`silent in ${v.absent} of ${v.estate} buckets`); }
    if (c && c.violating > 0) {
      worse("warn");
      why.push(`${fmt(c.violating)} rows missing ${Object.keys(c.missing).length} of 5 contract keys`);
    }
    if (!why.length) why.push(v ? v.why : "no volume data for this producer");
    return { state, tone: HTONE[state] || HTONE.unknown, why: why.join(" · ") };
  }

  /* ── node bodies ───────────────────────────────────────────── */
  function originBody(g, b, edges, fx) {
    const r = snap || {}, ing = r.ingest_rate || {};
    if (!open.origin) {
      const rows = [["logs", ing.logs], ["traces", ing.trace], ["metrics", ing.metrics]];
      rows.forEach(([name, v], i) => g.append(
        el("text", { class: "txt", x: b.x + 18, y: b.y + 66 + i * 26 }, name),
        el("text", { class: "val", x: b.x + b.w - 18, y: b.y + 66 + i * 26 }, fmt(v))));
      // Closed, the card still has to answer "is anything wrong" — otherwise the fused
      // state is information you can only get by opening the box that contains it.
      const names = (graph?.topology?.nodes || []).map((n) => n.service);
      const bad = names.filter((n) => ["warn", "fail"].includes(serviceHealth(n).state));
      const off = undeclared();
      g.append(el("text", { class: "sub", x: b.x + 18, y: b.y + 158 },
        `${names.length} declared · ${graph?.topology?.edges?.length || 0} edges`),
        el("text", { class: "sub", x: b.x + 18, y: b.y + 174,
            style: bad.length ? "fill:var(--sec)" : null },
          bad.length ? `${bad.length} needing attention` : "all declared producers in band"),
        el("text", { class: "sub", x: b.x + 18, y: b.y + 190,
            style: off.length ? "fill:var(--alarm)" : null },
          off.length ? `${off.length} undeclared producer${off.length > 1 ? "s" : ""} writing`
                     : "no undeclared producers"));
      return;
    }
    const t = graph?.topology;
    if (!t?.nodes?.length) return;
    const depth = {};
    t.nodes.forEach((n) => { if (n.roots) depth[n.id] = 0; });
    for (let pass = 0; pass < t.nodes.length; pass++)
      t.edges.forEach((e) => {
        if (depth[e.from] != null) depth[e.to] = Math.max(depth[e.to] ?? 0, depth[e.from] + 1);
      });
    const cols = {};
    t.nodes.forEach((n) => (cols[depth[n.id] ?? 0] ||= []).push(n));
    const NW = 196, NH = 42, pos = {};
    Object.entries(cols).forEach(([d, list]) => list.forEach((n, i) => {
      const step = ((b.gridH || b.h) - 56) / list.length;
      pos[n.id] = { x: b.x + 20 + (+d) * (NW + 52), y: b.y + 44 + step * i + (step - NH) / 2 };
    }));
    // Internal edges first, so nodes paint over them.
    //
    // Routed by `fan` rather than `route`: with 52px between columns there is no room for
    // a 45° elbow, and every edge that changes row would overshoot. The stub is staggered
    // per source, because edges leaving one node share a PORT and would otherwise share a
    // vertical column too — three 13px casings on one x is a blob, not a fan.
    // Declared edges, drawn at what they were actually measured carrying.
    //
    // `topology.yaml` says which component depends on which; the traced call graph says
    // how much went and how much failed. They are different claims and the picture shows
    // both: a declared edge nothing was ever traced on is drawn as declared-only, which is
    // the finding — here `spark_streaming -> processed_bucket` and
    // `spark_streaming -> k8s-api-gateway` never carry a span, because the generator's
    // engine parents every child to `depends_on[0]` and never to the second dependency.
    const svc = Object.fromEntries((t.nodes || []).map((n) => [n.id, n.service]));
    const measured = {};
    (snap?.call_edges || []).forEach((e) => (measured[`${e.src}\u0000${e.dst}`] = e));
    const peak = Math.max(1, ...(snap?.call_edges || []).map((e) => e.spans));
    const legs = {};
    t.edges.forEach((e, i) => {
      const a = pos[e.from], z = pos[e.to];
      if (!a || !z) return;
      const m = measured[`${svc[e.from]}\u0000${svc[e.to]}`];
      // Width from the share of the busiest edge, on a root so a 100x range stays legible.
      // The range tops out AT the standard 13px gauge and never above it: what these edges
      // carry is relative — which one moves more than which — and letting the busiest reach
      // 20 made ORIGIN's internal dependencies fatter than the feeders and the bronze fan,
      // so the board read as though a service call outweighed the pipeline it feeds. Only
      // the trunk is allowed to be the widest thing on the canvas, because only it carries
      // whole batches.
      // Bottom of the range is 8, not 6: at 6 the wall is all there is left and the thinnest
      // measured edge stopped looking like a pipe. Declared-but-never-traced sits below it at
      // 7 — still a pipe, visibly the slightest one, and dashed.
      const w = m ? 8 + Math.sqrt(m.spans / peak) * 5 : 7;
      const err = m && m.spans ? m.errors / m.spans : 0;
      const tone = !m ? "var(--dim)"
        : err >= 0.05 ? "var(--alarm)" : err >= 0.01 ? "var(--sec)" : null;
      // One casing apart, so three legs from one node stay three legs. Clamped to leave
      // the last chamfer room to land, which is what caps the fan at ~3 legs per node.
      const k = (legs[e.from] = (legs[e.from] ?? -1) + 1);
      const gap = z.x - (a.x + NW);
      pipe(edges, `oe${i}`, fan(a.x + NW, a.y + NH / 2, z.x, z.y + NH / 2,
        Math.min(gap - 12, 14 + k * 14)), m ? "" : "declared", {}, w, tone);
      mouth(a.x + NW, a.y + NH / 2);
      mouth(z.x, z.y + NH / 2);
      flow3(fx, `oe${i}`, `oe${i}`, 2.6 + (i % 3) * .4, 3.2, 2);
    });
    const byName = Object.fromEntries((r.lineage || []).map((z) => [z.service, z]));
    t.nodes.forEach((n) => {
      const p = pos[n.id], row = byName[n.service], sel = n.service === service;
      const h = serviceHealth(n.service);
      //: Declared beside measured. `topology.yaml` says what a component's latency should be;
      //: Silver's `service_health_1m` says what its operations actually took. The repo's rule
      //: applies — the two disagreeing is the finding — and this is the first thing drawn from
      //: `silver.*` rather than derived from Bronze. Absent whenever Silver is not deployed,
      //: which is any stack whose ClickHouse volume predates the DDL; the node then shows the
      //: declared figure alone, exactly as it always did.
      const sh = (snap?.service_health || []).find((r) => r.service === n.service);
      const node = el("g", { class: "hit", tabindex: "0", role: "button",
        "aria-pressed": String(sel),
        // The reason travels with the node for anyone not reading colour.
        "aria-label": `Trace ${n.service} through the pipeline — ${h.state}: ${h.why}`
          + (sh ? ` · measured p50 ${sh.p50} ms, p99 ${sh.p99} ms, ${(sh.error_rate * 100).toFixed(2)}% errors`
                : "") });
      node.dataset.service = n.service;
      // Name on its own line, figure on the next: at 196px a 24-character service name
      // and a right-aligned count were landing on the same pixels.
      node.append(
        // The border belongs to INTERACTION — hover and selection — and nothing else.
        // Health took it too, in the same `--sec` the hover uses, so a warning node and a
        // pointed-at node were indistinguishable and the pointer stopped meaning anything.
        // State lives in the mark below; one channel each.
        el("rect", { class: "nd sub-nd" + (sel ? " sel" : ""), x: p.x, y: p.y,
          width: NW, height: NH, rx: 3 }),
        // A status mark on every node, including the healthy ones: a dot that appears only
        // when something is wrong cannot be told from a node nobody is watching.
        el("circle", { class: "hmark", cx: p.x + 6, cy: p.y + NH / 2, r: 3, fill: h.tone }),
        el("text", { class: "txt", x: p.x + 16, y: p.y + 17 },
          clip(n.service, n.roots ? 21 : 26)),
        el("text", { class: "sub", x: p.x + 16, y: p.y + 33 },
          `${n.kind} · ${n.latency_ms ?? "?"} ms`
          // Not `fmt()`: it abbreviates 1796.6 to "1.8k", which is coarser than the declared
          // "1800" it sits beside — and the comparison is the entire point of the pair.
          + (sh ? ` \u2192 ${Math.round(sh.p50)} ms` : "")),
        el("text", { class: "val", x: p.x + NW - 12, y: p.y + 33 }, row ? fmt(row.total) : "—"));
      if (n.roots) node.append(el("text", { class: "cue end", x: p.x + NW - 12, y: p.y + 17 }, "ROOT"));
      g.append(node);
    });
    // Above the panel band, so it survives a service being selected. These have no node
    // because they are in no declared topology — which is the point being made.
    const off = undeclared();
    if (off.length) g.append(
      el("text", { class: "lbl", x: b.x + 20, y: b.y + 240, style: "fill:var(--alarm)" },
        "UNDECLARED"),
      el("text", { class: "sub", x: b.x + 104, y: b.y + 240 },
        `writing into bronze, in no topology: ${off.map((n) => clip(n, 24)).join(" · ")}`));
    if (service) signalPanel(g, b, byName[service]);
  }

  /** What one service actually sends, and where each part of it lands.
   *
   *  This is the honest form of "show me this service's path". The path everyone pictures
   *  — this service feeds these two tables — does not exist: bronze routes on the
   *  data-point type, so every service reaches all four. What differs is the metric mix,
   *  which is exactly why one service's gauge:sum split is 3:1 and another's is 1:2. */
  function signalPanel(g, b, row) {
    const inv = (snap?.metrics_by_service || {})[service] || { gauge: [], sum: [] };
    const y = b.y + 260, x = b.x + 20, w = b.w - 40;
    g.append(el("rect", { class: "nd sheet", x, y, width: w, height: 106, rx: 4 }),
      el("text", { class: "lbl", x: x + 14, y: y + 22, style: "fill:var(--sec)" },
        service.toUpperCase() + " → BRONZE"));
    const cols = [
      ["otel_logs", "every log record", row?.logs, []],
      ["otel_traces", "every span", row?.traces, []],
      ["otel_metrics_gauge", `${inv.gauge.length} gauge metrics`, row?.gauge, inv.gauge],
      ["otel_metrics_sum", `${inv.sum.length} sum metrics`, row?.sum, inv.sum],
    ];
    const cw = (w - 28) / 4;
    cols.forEach(([tbl, note, n, names], i) => {
      const cx = x + 14 + i * cw;
      g.append(el("text", { class: "txt", x: cx, y: y + 46 }, tbl.replace("otel_", "")),
        el("text", { class: "val", x: cx + cw - 18, y: y + 46 }, n == null ? "—" : fmt(n)),
        el("text", { class: "sub", x: cx, y: y + 61 }, note));
      names.slice(0, 3).forEach((nm, k) => g.append(
        el("text", { class: "sub", x: cx, y: y + 76 + k * 11 },
          "· " + nm.replace(/^.*\//, "").slice(0, 26))));
    });
  }

  function collectorBody(g, b, edges, fx) {
    const r = snap || {};
    const policy = policyOf();
    const byReason = r.reject_by_reason || {};
    if (!open.collector) {
      g.append(
        el("text", { class: "txt", x: b.x + 18, y: b.y + 70 }, "buffer"),
        el("text", { class: "val", x: b.x + b.w - 18, y: b.y + 70 }, fmt(r.records_per_flush)),
        el("text", { class: "txt", x: b.x + 18, y: b.y + 96 }, "export"),
        el("text", { class: "val", x: b.x + b.w - 18, y: b.y + 96 }, fmt(r.export_latency_ms) + " ms"),
        el("text", { class: "sub", x: b.x + 18, y: b.y + 124 }, `validate · ${policy}`));
      return;
    }
    const st = b.stages;
    const note = { receive: "gRPC :4317", validate: policy, buffer: fmt(r.records_per_flush) };
    st.forEach((sg, i) => {
      g.append(el("rect", { class: "nd sub-nd", x: sg.x, y: sg.y, width: sg.w, height: sg.h, rx: 3 }),
        el("text", { class: "txt", x: sg.x + 10, y: sg.y + 19 }, sg.name),
        el("text", { class: "sub", x: sg.x + 10, y: sg.y + 34 }, note[sg.name]));
      if (i < 2) {
        // An explicit, arrow-headed dependency. Every signal goes receive → validate →
        // buffer in that order; nothing enters in the middle and nothing leaves early.
        const id = `ce${i}`;
        pipe(edges, id, `M${sg.x + sg.w} ${sg.y + sg.h / 2} L${st[i + 1].x - 3} ${sg.y + sg.h / 2}`);
        mouth(sg.x + sg.w, sg.y + sg.h / 2);
        mouth(st[i + 1].x, sg.y + sg.h / 2);
        flow3(fx, id, id, 1.3, 2.8, 2);
      }
    });

    // ── the three ways a signal does not simply arrive ──
    //
    // Each outcome taps off the stage that decides it, and what tells the three apart is
    // its RETURN — or the absence of one. Under `warn` a contract failure is flagged and
    // still reaches the buffer; a refused batch sends a status back and the producer
    // re-enters through `receive`; a dropped batch has nowhere to go. Three identical rows
    // with no returns said all three were the same event, and the fate was left to a
    // 7.5px caption nobody reads.
    const contract = byReason.contract || 0, back = byReason.backpressure || 0;
    const warnMode = policy !== "strict";
    // Outcomes are inset from BOTH container edges: the two margins are the channels the
    // returns climb. Without them a return had to cross the rows it came from.
    const ox = b.x + 50, ow = b.w - 100;
    const chL = b.x + 30, chR = b.x + b.w - 30;
    g.append(el("text", { class: "lbl", x: ox, y: b.y + 168 }, "OUTCOMES"));
    // Each tap leaves a real point on a real object — the place in the code where that
    // outcome is decided. An earlier version started the backpressure tap in the empty gap
    // below the arrow, anchored to nothing, and it read as invented.
    const mid = (st[1].x + st[1].w + st[2].x) / 2;
    const outcomes = [
      {
        label: "CONTRACT", v: contract, where: "at validate",
        // validated inside `validate`, so it leaves validate's own bottom edge
        from: [st[1].x + st[1].w / 2, st[1].y + st[1].h],
        what: warnMode ? "flagged · exported anyway" : "discarded at the boundary",
        colour: "var(--sec)", fate: warnMode ? "rejoins the flow" : "ends here",
        // Under `warn` the flagged signal really does continue into the buffer, so the
        // return is drawn and carries the same colours that fell. Under `strict` it does
        // not, and the missing line IS the difference between the two policies — the
        // single most consequential setting in the collector, previously invisible.
        ret: warnMode
          ? { via: chR, band: b.y + 140, side: 1,
              to: [st[2].x + st[2].w * 0.72, st[2].y + st[2].h], carries: true }
          : null,
      },
      {
        label: "BACKPRESSURE", v: back, where: "entering buffer",
        // `buffer.enqueue` refuses on the hop INTO the buffer, so it branches off that arrow
        from: [mid, st[1].y + st[1].h / 2],
        what: "batch refused · resource_exhausted",
        colour: "var(--sec)", fate: "back to the producer",
        // What travels back is a gRPC status, not the batch: the producer still holds the
        // data, and its retry arrives at `receive` like any other export. So the loop
        // closes inside the container, and the line carries no particles — dots on it
        // would claim telemetry moved backwards, which never happens.
        ret: { via: chL, band: b.y + 150, side: -1,
               to: [st[0].x + st[0].w / 2, st[0].y + st[0].h], carries: false },
      },
      {
        label: "DROPPED", v: r.drop_rate || 0, where: "flushing to bronze",
        // the flush loop fails after the buffer, on the way out to ClickHouse. Offset from
        // buffer's centre so the contract return can land on the same edge without a clash.
        from: [st[2].x + st[2].w * 0.35, st[2].y + st[2].h],
        what: "after 3 retries · no dead-letter queue",
        colour: "var(--alarm)", fate: "ends here", ret: null,
      },
    ];
    outcomes.forEach((o, i) => {
      const y = b.y + 178 + i * 46;
      const [fromX, fromY] = o.from, live = o.v > 0, alarm = o.colour.includes("alarm");
      const mark = (live ? " live" : "") + (alarm ? " alarm" : "");
      // One line, straight down from the stage it leaves. Routing it around the side
      // produced three long horizontals sweeping under the whole chain, which read as a
      // bus rather than as "this outcome comes from that box". The drop passes BEHIND the
      // rows above it — edges are painted before nodes — so only the gaps show, and the
      // arrowhead names the row it actually lands on.
      const tapId = `tap${i}`;
      edges.append(el("path", { class: "ed tap" + mark, id: tapId,
        "marker-end": "url(#arrow-tap)",
        d: `M${fromX} ${fromY} L${fromX} ${y - 3}` }));
      // A pad where the branch begins — the same mark every other connection on the board
      // uses to say "this joins here".
      g.append(el("circle", { class: "via tap-via" + mark, id: `tapv${i}`,
        cx: fromX, cy: fromY, r: 3.4 }));
      // What falls out is drawn as WHAT FAILED. `signals_rejected_total` is labelled by
      // both `signal` and `reason`, so a metrics rejection falls amber and a log rejection
      // falls green — the page is not choosing a colour, it is reading one. The drop alone
      // cannot say: `storage_signals_total` is `signal="all"` there because the buffer
      // flushes one mixed batch, so it falls as the mixed sphere, ringed.
      if (alarm) flowBatch(fx, tapId, tapId, 1.7, 4.5, 2);
      else flow3(fx, tapId, tapId, 1.5, 3, 2);
      g.append(el("rect", { class: "nd sub-nd", x: ox, y, width: ow, height: 34, rx: 3,
          style: live ? `stroke:${o.colour}` : null }),
        el("text", { class: "lbl", x: ox + 12, y: y + 14, style: `fill:${o.colour}` }, o.label),
        el("text", { class: "txt", x: ox + 12, y: y + 28 }, fmt(o.v) + "/s"),
        el("text", { class: "sub", x: ox + 106, y: y + 14 }, o.where + " · " + o.what),
        el("text", { class: "sub", x: ox + 106, y: y + 28, style: `fill:${o.colour}` },
          (o.fate === "ends here" ? "⊣ " : "↩ ") + o.fate));
      if (!o.ret) return;
      // Out of the row sideways, up its margin channel, across the band between the chain
      // and the OUTCOMES label, and into the stage it rejoins from below. Nothing else
      // occupies that band, and the two returns use different heights in it so they never
      // share a line.
      const { via, band, side, to, carries } = o.ret;
      const retId = `ret${i}`;
      edges.append(el("path", {
        class: "ed ret" + (carries ? "" : " ctl") + (live ? " live" : ""),
        id: retId, "marker-end": "url(#arrow-tap)",
        d: poly([[side > 0 ? ox + ow : ox, y + 17], [via, y + 17],
                 [via, band], [to[0], band], [to[0], to[1] + 3]]) }));
      if (carries) flow3(fx, retId, retId, 2.2, 3, 2);
    });
  }

  /** Which bronze table each silver model is materialized FROM. Read off the four
   *  `CREATE MATERIALIZED VIEW ... TO silver.x ... FROM bronze.y` statements in
   *  `infra/clickhouse/init.d/02-silver-layer.sql`, not inferred from the names — and it is
   *  not 1:1: gauge and sum both land in `metric_observations`, which is the one thing about
   *  this layer a reader cannot get from anywhere else on the board.
   */
  /** Which signal colour a bronze table carries. Bronze routes on data-point TYPE, so the
   *  four names are the four types; the fallback exists so an added table is drawn in the
   *  neutral lane rather than crashing the render or silently reading as logs. */
  const toneOf = (t) => /log/.test(t) ? "p1" : /trace|span/.test(t) ? "p2"
    : /metric/.test(t) ? "p3" : "p1";

  /** Every strand from BRONZE into SILVER, READ from the lineage rather than listed here.
   *
   *  It is one entry per materialized view that reads a bronze table — which is what a
   *  strand *is*. Written as a constant it was a fourth copy of the DDL, after the SQL, the
   *  MV definitions and `system.tables`, and the first thing to go stale the day someone
   *  adds a model. Add an MV to `02-silver-layer.sql` and a strand appears; nothing here
   *  needs editing.
   */
  const derives = () => {
    const G = graph?.silver_graph || {};
    return Object.entries(G)
      .filter(([, n]) => n.kind === "mv")
      .flatMap(([name, n]) => (n.sources || [])
        .filter((src) => src.startsWith("bronze."))
        .map((src) => [src.split(".")[1], name, toneOf(src.split(".")[1])]))
      .sort((a, z) => bronzeOrder().indexOf(a[0]) - bronzeOrder().indexOf(z[0]));
  };
  //: The order bronze draws its own tables in, so the strands leave in the order they
  //: arrive. Read from the same `graph.tables` bronzeBody iterates, never listed twice.
  const bronzeOrder = () => Object.keys(graph?.tables || {});

  const FEEDS_FALLBACK = "bronze";

  /** SILVER — what Bronze becomes, not where Bronze goes.
   *
   *  The link from bronze is NOT a pipe, and that is the point. Everything else on this
   *  canvas transports something: signals move along a bore from one component to another.
   *  Bronze to Silver moves nothing — ADR-0010's materialized views fire inside ClickHouse
   *  on the same insert that writes bronze. Drawing a run between them would claim a hop
   *  that never happens, so it is drawn as a derivation: a short double bar, no particles.
   */
  //: Inside SILVER: three columns, one per kind, in the order data reaches them.
  //: `colGap` is routing room, not decoration: ten table→view edges have to pass between
  //: those two columns, and at 26 they shared one channel and rendered as a smear.
  const SB = { w: 180, h: 34, gap: 6, colGap: 72, pad: 26, head: 86 };

  /** SILVER's open footprint, measured from the graph rather than typed in.
   *
   *  Three columns because there are three kinds of object in ClickHouse, and that is a
   *  property of ClickHouse, not of this schema. Height is however many rows the tallest
   *  column needs. Add a model or a read view to `02-silver-layer.sql` and the box grows to
   *  hold it with no edit here — which is the whole point of reading `system.tables`
   *  instead of restating it.
   */
  function silverSize() {
    const lay = silverLayout(graph?.silver_graph || {}, { x: 0, y: 0 });
    const cols = Math.max(3, lay?.cols || 3), rows = Math.max(1, lay?.rows || 1);
    return [SB.pad * 2 + SB.w * cols + SB.colGap * (cols - 1),
            SB.head + rows * (SB.h + SB.gap) + 18];
  }

  /** SILVER, opened: every object in the database as its own box, and the lineage between.
   *
   *  Three kinds live in `silver` and collapsing them was the confusion this fixes — the
   *  first version drew three boxes and a list of six names, which said nothing about what
   *  separates them:
   *
   *  - **table** (MergeTree) — stores rows. It has a count, a sort key and a TTL.
   *  - **mv** (MaterializedView) — stores nothing. In ClickHouse this is an *insert
   *    trigger*, not a stored result set: rows land in its source, it runs its SELECT over
   *    that block and inserts into its target. It is why Silver holds only what arrived
   *    after the DDL did.
   *  - **view** — a named query, run when read. No rows exist until someone asks, so there
   *    is no count to show and never will be.
   *
   *  Which is why the edges are not all the same edge. Bronze → mv → table carries
   *  particles: rows really do move, on the insert. table → view carries none: nothing
   *  flows there until a reader runs the query, and animating it would claim a stream that
   *  does not exist. Colour is the source table's signal type throughout.
   */
  function silverBody(g, b, edges, fx) {
    const sv = snap?.silver || {};
    if (!sv.present) {
      g.append(el("text", { class: "txt", x: b.x + 18, y: b.y + 66 }, "not deployed"),
        el("text", { class: "sub", x: b.x + 18, y: b.y + 88 }, "the DDL applies on"),
        el("text", { class: "sub", x: b.x + 18, y: b.y + 102 }, "ClickHouse boot — a volume"),
        el("text", { class: "sub", x: b.x + 18, y: b.y + 116 }, "older than it has no silver"));
      return;
    }
    const models = sv.models || {}, total = Object.values(models).reduce((a, z) => a + z, 0);
    if (!open.silver) {
      g.append(el("text", { class: "txt", x: b.x + 18, y: b.y + 66 }, fmt(total) + " rows"),
        el("text", { class: "sub", x: b.x + 18, y: b.y + 88 },
          `${Object.keys(models).length} models · ${(sv.views || []).length} read views`),
        // Empty is the normal state of a stack nobody has streamed into yet, and it is a
        // different statement from absent. Saying which keeps the box honest.
        el("text", { class: "sub", x: b.x + 18, y: b.y + 106 },
          total ? `${sv.mvs} materialized views feeding` : "empty — run a stream"));
      return;
    }
    const G = graph?.silver_graph || {};
    const lay = silverLayout(G, b);
    if (!lay) return;

    // A key, not column headings: the columns are DAG depth now, so any of them can hold
    // any kind. Kind is carried by the border, and a border style nobody explains is a
    // pattern, not information.
    [["k-mv", "materialized view", "an insert trigger · stores nothing"],
     ["k-tbl", "table", "the rows live here"],
     ["k-view", "read view", "a query · run when read"]].forEach(([k, t, why], i) => {
      const x = b.x + SB.pad + i * 200, y = b.y + 46;
      g.append(el("rect", { class: "nd sub-nd " + (k === "k-tbl" ? "" : k),
          x, y: y - 9, width: 12, height: 12, rx: 2 }),
        el("text", { class: "sub", x: x + 18, y }, t),
        el("text", { class: "sub", x: x + 18, y: y + 12, style: "opacity:.5" }, why));
    });

    // Lineage inside SILVER, drawn before the boxes so the boxes cap the runs. Each read
    // edge gets its own vertical channel in the gap; sharing one turned ten dependencies
    // into a single unreadable smear.
    let lane = 0;
    for (const [name, n] of Object.entries(lay.nodes)) {
      for (const up of lay.feeds[name]) {
        const from = lay.nodes[up];
        if (!from) continue;
        const cls = lay.tone[up] || "p1";
        // An MV WRITING its target is real movement — rows land on that insert — so it gets
        // a pipe with particles. Everything else here is a READ: a view's source, or an MV's
        // input, where nothing travels until the query runs. Same lineage, different claim.
        if (G[up]?.target === name) {
          const id = `sv-${up}`;
          pipe(edges, id, fan(from.x + SB.w, from.cy, n.x, n.cy, 12), "", {}, 7);
          mouth(n.x, n.cy, 7);
          spawn(fx, id, cls);
        } else {
          // `p1..p3` are particle FILL classes; an edge wearing one renders filled.
          edges.append(el("path", { class: "lin " + cls.replace("p", "e"),
            d: fan(from.x + SB.w, from.cy, n.x, n.cy, 10 + (lane++ % 10) * 6) }));
        }
      }
    }

    for (const [name, n] of Object.entries(lay.nodes)) {
      const kind = G[name].kind, sel = name === model;
      const node = el("g", { class: "hit", tabindex: "0", role: "button",
        "aria-label": `${name}, ${KIND_SAYS[kind]}` });
      node.dataset.model = name;
      const rows = models[name];
      node.append(el("rect", { class: "nd sub-nd" + (sel ? " sel" : "") + " k-" + kind,
          x: n.x, y: n.y, width: SB.w, height: SB.h, rx: 3 }),
        el("text", { class: "txt", x: n.x + 9, y: n.y + 15, style: "font-size:9px" },
          clip(name, 28)),
        el("text", { class: "sub", x: n.x + 9, y: n.y + 27, style: "opacity:.6" },
          kind === "view" ? (graph?.silver_views?.[name]?.[0] || "query")
            : kind === "mv" ? "on insert" : "stored"),
        // Only a table has a count. A view's rows do not exist until it is read, and an MV
        // holds none at all — printing 0 there would be a different claim from "none".
        el("text", { class: rows === undefined ? "sub" : "val", x: n.x + SB.w - 9, y: n.y + 21,
            style: rows === undefined ? "text-anchor:end;opacity:.4" : "text-anchor:end" },
          rows === undefined ? "—" : fmt(rows)));
      g.append(node);
      if (kind === "mv") ports.silver[name] = { x: n.x, y: n.cy };
    }
  }

  //: The short form, for the sheet header where there are 320 units to share with a title.
  const KIND_SHORT = { table: "table", mv: "materialized view", view: "read view" };
  //: The long form, for the screen reader, which has no width limit and needs the whole
  //: distinction spelled out — it cannot see the border style that carries it visually.
  const KIND_SAYS = {
    table: "a table — stores rows",
    mv: "a materialized view — an insert trigger, stores nothing",
    view: "a read view — a query, run when read, stores nothing",
  };

  //: Particles for one strand, on the batch arrival that feeds it.
  function spawn(fx, id, cls, r = 2.6) {
    const { dur, n } = pools.__batch || { dur: 3.2, n: 3 };
    const pool = [];
    for (let k = 0; k < n; k++) {
      const c = el("circle", { class: cls, r, opacity: 0 });
      const a = el("animateMotion", { dur: `${(dur * 0.55).toFixed(2)}s`,
        repeatCount: "indefinite", begin: `${(k * dur / n + dur).toFixed(2)}s` });
      a.append(el("mpath", { href: `#${id}` }));
      c.append(a); fx.append(c); pool.push(c);
    }
    pools[id] = pool;
  }

  /** Rows and columns for SILVER's objects, laid out by DEPTH in the DAG, not by kind.
   *
   *  Kind decided the column in the first version and it was wrong the moment the schema
   *  stopped being a straight line. A second-stage MV — one reading a silver table rather
   *  than a bronze one, which is how you build an hourly rollup — belongs *between* two
   *  tables; by kind it landed back in column 0 and its edge ran right to left, drawing a
   *  dependency that reads backwards. A table nothing feeds belongs at the start, not in the
   *  middle. Depth puts each node after everything it reads, whatever it happens to be, and
   *  the kind is carried by the border and the sub-label instead.
   *
   *  Edges are the dependency, in both directions the DDL states them: an MV *reads* its
   *  sources and *writes* its target, so a table's producers are the MVs pointing at it.
   */
  function silverLayout(G, b) {
    const names = Object.keys(G);
    if (!names.length) return null;
    const bare = (r) => r.split(".")[1];

    // Who feeds whom. A table has no `sources` of its own — it is fed by the MVs whose
    // `target` it is, so that edge has to be read backwards out of the MV.
    const feeds = {};
    names.forEach((n) => { feeds[n] = new Set(); });
    names.forEach((n) => {
      (G[n].sources || []).forEach((src) => {
        if (feeds[bare(src)]) feeds[n].add(bare(src));      // reads a silver object
      });
      const t = G[n].target;
      if (t && feeds[t]) feeds[t].add(n);                   // an MV writes this table
    });

    // Depth = one past the deepest thing it reads. `busy` guards a cycle: ClickHouse will
    // let you build one, and an unguarded walk would recurse until the stack gives out.
    const depth = {}, busy = new Set();
    const walk = (n) => {
      if (n in depth) return depth[n];
      if (busy.has(n)) return 0;
      busy.add(n);
      const up = [...feeds[n]].map(walk);
      busy.delete(n);
      return (depth[n] = up.length ? Math.max(...up) + 1 : 0);
    };
    names.forEach(walk);

    const cols = [];
    names.forEach((n) => { (cols[depth[n]] ||= []).push(n); });
    // Within a column, follow the row of whatever feeds you, so runs stay short and mostly
    // straight — the same rule that took the four bronze strands from crossing to flat.
    const row = {};
    cols.forEach((col, c) => {
      col.sort((a, z) => {
        const at = (n) => {
          const up = [...feeds[n]].map((u) => row[u]).filter((r) => r !== undefined);
          return up.length ? Math.min(...up) : (c === 0 ? -1 : 900);
        };
        return at(a) - at(z) || a.localeCompare(z);
      });
      col.forEach((n, i) => { row[n] = i; });
    });

    // Colour is the signal type of the bronze table the chain started from, carried forward
    // so a rollup three hops down still reads as "this is the metrics lineage".
    const tone = {};
    const toneFor = (n) => {
      if (tone[n]) return tone[n];
      const ext = (G[n].sources || []).find((s) => s.startsWith("bronze."));
      if (ext) return (tone[n] = toneOf(bare(ext)));
      const up = [...feeds[n]];
      return (tone[n] = up.length ? toneFor(up[0]) : "p1");
    };
    names.forEach((n) => { tone[n] = undefined; });
    names.forEach(toneFor);

    const nodes = {};
    cols.forEach((col, c) => col.forEach((n, i) => {
      const x = b.x + SB.pad + c * (SB.w + SB.colGap);
      const y = b.y + SB.head + i * (SB.h + SB.gap);
      nodes[n] = { x, y, cy: y + SB.h / 2, col: c, row: i };
    }));
    return { nodes, feeds, tone, cols: cols.length,
             rows: Math.max(...cols.map((c) => c.length)) };
  }

  /** BRONZE ⇒ SILVER, per table, once both boxes are open.
   *
   *  Closed, this is one double bar: the honest summary of a derivation that moves nothing
   *  across a network. Open, the reader is asking a lineage question — *which table becomes
   *  which* — and that question has an answer only a drawing gives cheaply, because the
   *  mapping is not 1:1. `otel_metrics_gauge` and `otel_metrics_sum` both land in
   *  `metric_observations`; nothing else on this board says so.
   *
   *  The strands carry particles and the strands are short, which is the point: the dots
   *  depart on the SAME batch arrival that fills the bronze row, because ADR-0010's
   *  materialized views fire inside ClickHouse on that insert. They are not a second hop
   *  after it. The two vertical channels for the metrics pair are deliberately offset so the
   *  merge is visible as a merge rather than as one line drawn twice.
   */
  function derivations(edges, fx, B) {
    if (!(open.bronze && open.silver)) return;
    let seen = 0;
    derives().forEach(([from, to, cls], i) => {
      const a = ports.bronze[from], z = ports.silver[to];
      if (!a || !z) return;
      const id = `dv${i}`;
      pipe(edges, id, fan(a.x, a.y, z.x, z.y, 30 + i * 8), "", {}, 7);
      mouth(z.x, z.y, 7);
      spawn(fx, id, cls);
      seen++;
    });
  }

  function bronzeBody(g, b, edges, fx) {
    const r = snap || {}, tables = graph?.tables || {};
    const total = Object.values(r.bronze || {}).reduce((a, z) => a + z, 0);
    if (!open.bronze) {
      g.append(el("text", { class: "txt", x: b.x + 18, y: b.y + 66 }, fmt(total) + " rows"),
        el("text", { class: "sub", x: b.x + 18, y: b.y + 88 },
          `${Object.keys(tables).length} tables`),
        el("text", { class: "sub", x: b.x + 18, y: b.y + 106 },
          `${Object.keys(graph?.empty_by_contract || {}).length} empty by contract`));
      return;
    }
    const names = Object.keys(tables), TW = 228, TH = 40;
    // When a service is selected the tables report that service's rows, not the estate's.
    const row = (r.lineage || []).find((z) => z.service === service);
    const KEY = { otel_logs: "logs", otel_traces: "traces",
                  otel_metrics_gauge: "gauge", otel_metrics_sum: "sum" };
    names.forEach((n, i) => {
      // Tables sit right of the fan channel so the bus has room to reach every row
      // without crossing one.
      const y = b.y + 46 + i * (TH + 8), x = b.x + 68;
      const sel = n === table;
      const node = el("g", { class: "hit", tabindex: "0", role: "button",
        "aria-label": `Inspect ${n}` });
      node.dataset.table = n;
      node.append(el("rect", { class: "nd sub-nd" + (sel ? " sel" : ""), x, y,
          width: TW, height: TH, rx: 3 }),
        el("text", { class: "txt", x: x + 10, y: y + 17 }, n.replace("otel_", "")),
        el("text", { class: "val", x: x + TW - 10, y: y + 17 },
          fmt(row ? row[KEY[n]] : (r.bronze || {})[n])),
        el("text", { class: "sub", x: x + 10, y: y + 32 },
          row ? `${service.slice(0, 22)} only` : `${tables[n].section} · +${fmt((r.bronze_rate || {})[n])}/s`));
      g.append(node);
      ports.bronze[n] = { x: x + TW, y: y + TH / 2 };
      // One lane in, fanning to each table — and each strand carries the colour of what
      // actually lands there. Routing is by data-point TYPE, so a log only ever reaches
      // otel_logs; painting every strand the same colour said the opposite.
      const id = `be${i}`;
      pipe(edges, id, fan(b.x, b.y + b.h / 2, x, y + TH / 2));
      mouth(x, y + TH / 2);
      const cls = { otel_logs: "p1", otel_traces: "p2",
                    otel_metrics_gauge: "p3", otel_metrics_sum: "p3" }[n] || "p1";
      // Departures are keyed to the batch ARRIVALS, so a strand leaves at the instant the
      // ball opens. That is the unpacking, not a loop that happens to look like one.
      const { dur, n: inFlight } = pools.__batch || { dur: 3.2, n: 3 };
      const pool = [];
      for (let k = 0; k < inFlight; k++) {
        const c = el("circle", { class: cls, r: 3.2, opacity: 0 });
        const a = el("animateMotion", { dur: `${dur}s`, repeatCount: "indefinite",
          begin: `${(k * dur / inFlight + dur).toFixed(2)}s` });
        a.append(el("mpath", { href: `#${id}` }));
        c.append(a); fx.append(c); pool.push(c);
      }
      pools[id] = pool;
    });
  }

  /* ── the datasheet, only when bronze is open ───────────────── */
  function datasheet(parent, sheet) {
    const d = (graph?.tables || {})[table];
    if (!d || !sheet) return;
    const { x, y, w, h } = sheet;
    parent.append(el("rect", { class: "nd sheet", x, y, width: w, height: h, rx: 4 }),
      el("text", { class: "lbl", x: x + 16, y: y + 24, style: "fill:var(--sec)" },
        table.toUpperCase()));
    (d.summary.match(/.{1,48}(\s|$)/g) || []).slice(0, 2).forEach((line, i) =>
      parent.append(el("text", { class: "sub", x: x + 16, y: y + 42 + i * 13 }, line.trim())));
    d.columns.slice(0, 8).forEach(([name, type], i) => {
      const cy = y + 84 + i * 17;
      parent.append(el("text", { class: "txt", x: x + 16, y: cy }, name),
        el("text", { class: "sub", x: x + w - 16, y: cy, style: "text-anchor:end" }, type));
    });
    parent.append(el("text", { class: "sub", x: x + 16, y: y + h - 12 },
      `TTL ${d.ttl} · ${d.section}`));
  }

  /** The datasheet for a SILVER model — same shape as bronze's, different provenance.
   *
   *  Bronze's is hand-written in `topology.TABLE_DOCS` because the read contract makes a
   *  *subset* claim: only some columns are populated, the rest sit at their ClickHouse
   *  default by design (§2), and no DDL can express that. Silver makes no such claim — the
   *  DDL is the whole definition — so its columns are read live from `system.columns` and
   *  cannot drift from the deployed schema. Only the one-line summary is written by hand,
   *  because a type is metadata and a purpose is a claim.
   */
  function modelsheet(parent, sheet) {
    const d = (graph?.silver_graph || {})[model];
    if (!d || !sheet) return;
    const { x, y, w, h } = sheet;
    parent.append(el("rect", { class: "nd sheet", x, y, width: w, height: h, rx: 4 }),
      el("text", { class: "lbl", x: x + 16, y: y + 24, style: "fill:var(--sec)" },
        model.toUpperCase()),
      // What KIND it is, because that is the thing a reader gets wrong about a ClickHouse
      // `silver` database. On its own line: the long form is 53 characters against a
      // 320-wide sheet, so right-anchored beside the title it ran straight through it.
      el("text", { class: "sub", x: x + w - 16, y: y + 24, style: "text-anchor:end" },
        KIND_SHORT[d.kind] || ""));
    // A view's own purpose comes from its grain and its answer; a table's is written down.
    const vd = graph?.silver_views?.[model];
    const say = d.summary || (vd ? `${vd[0]} · ${vd[1]}` : "");
    (say.match(/.{1,48}(\s|$)/g) || []).slice(0, 2).forEach((line, i) =>
      parent.append(el("text", { class: "sub", x: x + 16, y: y + 42 + i * 13 }, line.trim())));
    // Reads above, writes below. Both at the same y drew one on top of the other.
    if (d.sources?.length)
      parent.append(el("text", { class: "sub", x: x + 16, y: y + 70, style: "opacity:.6" },
        "reads " + clip(d.sources.join(", "), 52)));
    if (d.target)
      parent.append(el("text", { class: "sub", x: x + 16, y: y + 83, style: "opacity:.6" },
        `writes silver.${d.target}`));
    // Two columns: 16 to 19 columns will not fit one, and truncating the list would hide
    // exactly the normalized fields that are the reason this layer exists.
    const cols = d.columns || [], half = Math.ceil(cols.length / 2);
    cols.forEach(([name, type], i) => {
      const cx = x + 16 + (i < half ? 0 : w / 2 - 8);
      const cy = y + 90 + (i % half) * 13;
      parent.append(el("text", { class: "sub", x: cx, y: cy }, clip(name, 20)),
        el("text", { class: "sub", x: cx + w / 2 - 24, y: cy,
          style: "text-anchor:end;opacity:.55" }, clip(shortType(type), 13)));
    });
    // An MV has no columns and no sort key of its own; saying so beats an empty panel.
    parent.append(el("text", { class: "sub", x: x + 16, y: y + h - 12 },
      d.order_by ? `ORDER BY ${clip(d.order_by, 56)}`
        : d.kind === "mv" ? "no storage of its own — the rows land in its target"
        : "no sort key — computed at read time"));
  }

  //: ClickHouse spells types in full; the sheet has 13 characters. The distinction that
  //: matters to a reader is the family, not the codec or the key type.
  const shortType = (t) => t
    .replace(/LowCardinality\((.*)\)/, "$1 (lc)")
    .replace(/Map\(.*\)/, "Map")
    .replace(/DateTime64\(\d+\)/, "DateTime64")
    // Enum8('gauge' = 1, 'sum' = 2) is 30 characters of quoting to say "Enum8".
    .replace(/Enum(\d+)\(.*\)/, "Enum$1");

  /* ── render ────────────────────────────────────────────────── */
  const TITLE = { origin: "ORIGIN", collector: "COLLECTOR-RUST", bronze: "BRONZE",
                  silver: "SILVER" };

  function render() {
    const stage = $("stage");
    pools = {};
    ports = { bronze: {}, silver: {} };
    const L = layout(), B = L.boxes;
    const svg = el("svg", { viewBox: `0 0 ${VW} ${VH}`, preserveAspectRatio: "xMidYMid meet" });
    const defs = el("defs");
    const f = el("filter", { id: "bloom", x: "-70%", y: "-70%", width: "240%", height: "240%" });
    f.append(el("feGaussianBlur", { stdDeviation: "2.6", result: "b" }));
    const m = el("feMerge");
    m.append(el("feMergeNode", { in: "b" }), el("feMergeNode", { in: "SourceGraphic" }));
    f.append(m); defs.append(f);
    // Arrowheads. A dependency without a head is a line, and a line does not say which
    // way the data goes.
    for (const [id, colour] of [["arrow", "var(--rule-arrow)"], ["arrow-sec", "var(--sec)"],
                                ["arrow-tap", "var(--rule-arrow)"]]) {
      const mk = el("marker", { id, viewBox: "0 0 8 8", refX: "7", refY: "4",
        markerWidth: "5", markerHeight: "5", orient: "auto-start-reverse" });
      mk.append(el("path", { d: "M0 1 L7 4 L0 7 z", fill: colour }));
      defs.append(mk);
    }
    svg.append(defs);

    root = el("g", { id: "vp" });
    //: Captions that must sit above the edge layer but are not part of any node.
    const nodesLater = [];
    const edges = el("g", { class: "ed-layer" });
    vias = el("g", { class: "via" });
    const fx = el("g", { filter: "url(#bloom)" });
    const nodes = el("g");
    root.append(edges, vias, fx, nodes);
    svg.append(root);

    // Between-container edges. These exist whatever is expanded — the flow is continuous.
    const lanes = [["logs", "p1"], ["trace", "p2"], ["metrics", "p3"]];
    lanes.forEach(([name, cls], i) => {
      pipe(edges, `L${i}`,
        route(B.origin.out[i][0], B.origin.out[i][1], B.collector.in[i][0], B.collector.in[i][1]));
      flow(fx, `L${i}`, name, cls);
      mouth(B.origin.out[i][0], B.origin.out[i][1]);
      mouth(B.collector.in[i][0], B.collector.in[i][1]);
    });
    pipe(edges, "B0",
      route(B.collector.out[0], B.collector.out[1], B.bronze.in[0], B.bronze.in[1]), "trunk");
    mouth(B.collector.out[0], B.collector.out[1], 24);
    mouth(B.bronze.in[0], B.bronze.in[1], 24);

    // BRONZE ⇒ SILVER. Not a pipe, and no mouths: nothing travels here. ADR-0010's
    // materialized views fire inside ClickHouse on the same insert that writes bronze, so a
    // run with dots in it would draw a hop that never happens. A double bar is the derivation
    // mark — the two rules a reader has to keep apart are "moved" and "derived from".
    const sb = B.bronze, sv = B.silver, dy = 5;
    const x1 = sb.x + sb.w, x2 = sv.x, my = sb.y + sb.h / 2;
    if (!(open.bronze && open.silver)) {
      [-dy, dy].forEach((o) => edges.append(el("path", { class: "derive",
        d: `M${x1} ${my + o} L${x2} ${my + o}` })));
      edges.append(el("path", { class: "derive tip", "marker-end": "url(#arrow-tap)",
        d: `M${x2 - 12} ${my} L${x2 - 1} ${my}` }));
      nodesLater.push(el("text", { class: "sub", x: (x1 + x2) / 2, y: my - 12,
        style: "text-anchor:middle" }, "derived"),
        el("text", { class: "sub", x: (x1 + x2) / 2, y: my + 20,
          style: "text-anchor:middle" }, "on insert"));
    }
    // Three batches in flight, evenly spaced. Each one's ARRIVAL time is what the burst
    // and the per-table fan below are keyed to, so the unpacking is not decorative timing
    // — it happens when the batch actually gets there.
    const BATCH_DUR = 3.2, IN_FLIGHT = 3;
    const blk = [];
    for (let k = 0; k < IN_FLIGHT; k++) {
      const ball = batchBall();
      ball.setAttribute("opacity", 0);
      const a = el("animateMotion", { dur: `${BATCH_DUR}s`, repeatCount: "indefinite",
        begin: `${(k * BATCH_DUR / IN_FLIGHT).toFixed(2)}s` });
      a.append(el("mpath", { href: "#B0" }));
      ball.append(a); fx.append(ball); blk.push(ball);
    }
    pools.blk = blk;
    // The moment of arrival: a ring that opens at the entry point, on the same period.
    for (let k = 0; k < IN_FLIGHT; k++) {
      const at = (k * BATCH_DUR / IN_FLIGHT + BATCH_DUR).toFixed(2);
      const ring = el("circle", { class: "burst", cx: B.bronze.in[0], cy: B.bronze.in[1],
        r: 3, fill: "none", stroke: "var(--sec)", "stroke-width": 1.6, opacity: 0 });
      ring.append(
        el("animate", { attributeName: "r", values: "3;20;20", keyTimes: "0;0.18;1",
          dur: `${BATCH_DUR}s`, begin: `${at}s`, repeatCount: "indefinite" }),
        el("animate", { attributeName: "opacity", values: ".9;0;0", keyTimes: "0;0.18;1",
          dur: `${BATCH_DUR}s`, begin: `${at}s`, repeatCount: "indefinite" }));
      fx.append(ring);
      (pools.burst ||= []).push(ring);
    }
    pools.__batch = { dur: BATCH_DUR, n: IN_FLIGHT };

    for (const id of ["origin", "collector", "bronze", "silver"]) {
      const b = B[id];
      const g = el("g", { class: "hit node", tabindex: "0", role: "button",
        "aria-expanded": String(open[id]),
        "aria-label": `${open[id] ? "Collapse" : "Expand"} ${TITLE[id]}` });
      g.dataset.node = id;
      g.append(el("rect", { class: "nd" + (open[id] ? " open" : ""), x: b.x, y: b.y,
          width: b.w, height: b.h, rx: 5 }));
      // Open, only the header carries the click. The full-size rect covers everything drawn
      // inside the container, so leaving it hit-testable meant the pointer was always over
      // the container even while aiming at a table inside it.
      if (open[id]) g.append(el("rect", { class: "chrome", x: b.x, y: b.y,
        width: b.w, height: 38, rx: 5 }));
      g.append(
        el("text", { class: "lbl", x: b.x + 18, y: b.y + 26 }, TITLE[id]),
        el("text", { class: "cue", x: b.x + b.w - 18, y: b.y + 26,
          style: "text-anchor:end" }, open[id] ? "CLOSE ▾" : "OPEN ▸"));
      nodes.append(g);
      ({ origin: originBody, collector: collectorBody, bronze: bronzeBody,
         silver: silverBody }[id])(g, b, edges, fx);
    }
    derivations(edges, fx, B);
    if (L.sheet) datasheet(nodes, L.sheet);
    if (L.mSheet) modelsheet(nodes, L.mSheet);
    nodesLater.forEach((n) => nodes.append(n));
    // The burst only means something when a batch is actually arriving.
    show("burst", 0);

    stage.replaceChildren(svg);
    stage.querySelectorAll("[data-node]").forEach((n) => {
      n.addEventListener("click", () => { open[n.dataset.node] = !open[n.dataset.node]; repaint(); });
      n.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); n.click(); }
      });
    });
    // Both toggle, and both start unselected: a datasheet is the answer to a click, so it
    // appears on one and goes away on the next. BRONZE used to open with `otel_logs`
    // selected and no way to deselect it, which made the sheet a permanent fixture of the
    // open box rather than something the reader asked for.
    stage.querySelectorAll("[data-table]").forEach((n) => {
      n.addEventListener("click", (e) => {
        e.stopPropagation();
        table = table === n.dataset.table ? null : n.dataset.table;
        repaint();
      });
    });
    stage.querySelectorAll("[data-model]").forEach((n) => {
      n.addEventListener("click", (e) => {
        e.stopPropagation();
        model = model === n.dataset.model ? null : n.dataset.model;
        repaint();
      });
    });
    stage.querySelectorAll("[data-service]").forEach((n) => {
      const pick = (e) => {
        e.stopPropagation();
        service = service === n.dataset.service ? null : n.dataset.service;
        repaint();
      };
      n.addEventListener("click", pick);
      n.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(e); }
      });
    });
    L.content = { w: L.width, h: L.height, x0: L.x0, y0: L.y0 };
    // Refit when the drawing actually changed SIZE — opening a box, or selecting a service
    // and growing ORIGIN for its panel. Not on every repaint: a mode change repaints too and
    // would throw away a pan the reader had just made. Opening a box is a deliberate act
    // with an expectation of seeing what is inside; a data tick is not.
    const prev = lastLayout?.content;
    const resized = !prev || prev.w !== L.content.w || prev.h !== L.content.h;
    lastLayout = L;
    if (resized) fit();
    applyView();
    $("legend").innerHTML = legend();
    if (snap) density(snap);
  }
  let lastLayout = null;

  function legend() {
    if (service) {
      // The rates on screen are the whole pipeline's. Saying so is not a caveat — it is
      // the difference between a filtered view and a lie.
      return `<span class="on">tracing <b>${service}</b></span>
        <span>bronze figures are <b>this service only</b></span>
        <span>rates stay <b>pipeline-wide</b> — the collector does not label by service</span>
        <span class="sp">click it again, or ⌂, to clear</span>`;
    }
    // Every hop carries all three signal types, inside a container as well as between
    // them, so there is one rule and it holds everywhere. An earlier legend claimed a dot
    // meant a trace inside a box; once internal edges started carrying all three, that
    // stopped being true.
    const base = `<span><span class="gl" style="background:var(--pri)"></span>logs</span>
      <span><span class="gl" style="background:var(--ter)"></span>traces</span>
      <span><span class="gl" style="background:var(--sec)"></span>metrics</span>
      <span class="sp">one dot = <b>${QUANTUM} signals</b> of that type</span>
      <span><span class="tri"></span>= <b>one batch</b>, all three mixed</span>`;
    // With the collector open the same three colours take on a second job — they name
    // which type FAILED — so that rule is spelled out only where falling dots exist.
    if (open.origin) return base
      + `<span>producers carry their <b>fused state</b> — volume band, silence, contract keys</span>`
      + `<span>pipe width = <b>traced spans</b> · <span style="color:var(--sec)">≥1%</span>`
      + ` / <span style="color:var(--alarm)">≥5%</span> of them failed</span>`
      + `<span>dashed = <b>declared, never traced</b></span>`;
    return open.collector ? base
      + `<span>leaving the chain = <b>what failed</b></span>
         <span><span class="tri ring"></span>= a <b>lost batch</b>, type unknowable</span>`
      : base;
  }

  /* ── viewport: transform only, never a re-render ───────────── */
  function applyView() {
    if (root) root.setAttribute("transform",
      `translate(${view.x.toFixed(2)} ${view.y.toFixed(2)}) scale(${view.k.toFixed(3)})`);
  }
  //: How far `fit` may scale UP. A graph that never exceeds 1 leaves a 32" screen mostly
  //: empty; one with no ceiling turns three boxes into wall art. 1.8 fills a tall window and
  //: still looks like a diagram.
  const FIT_MAX = 1.8;

  function fit() {
    if (!lastLayout) return;
    const { w, h, x0, y0 } = lastLayout.content;
    if (!(w > 0 && h > 0)) return;
    view.k = clampK(Math.min(FIT_MAX, (VW - 24) / w, (VH - 24) / h));
    // Centre the CONTENT, not the origin: the boxes start at x0/y0, and centring `w × h` as
    // though it began at 0,0 offset the graph by exactly that margin.
    view.x = (VW - w * view.k) / 2 - x0 * view.k;
    view.y = (VH - h * view.k) / 2 - y0 * view.k;
    applyView();
  }
  const clampK = (k) => Math.max(0.3, Math.min(3, k));
  /** Zoom about a point in viewBox space, so the thing under the cursor stays put. */
  function zoomAt(px, py, factor) {
    const k = clampK(view.k * factor);
    if (k === view.k) return;
    view.x = px - (px - view.x) * (k / view.k);
    view.y = py - (py - view.y) * (k / view.k);
    view.k = k;
    applyView();
  }
  const toViewBox = (evt, svg) => {
    const r = svg.getBoundingClientRect();
    return [(evt.clientX - r.left) / r.width * VW, (evt.clientY - r.top) / r.height * VH];
  };

  function wireViewport() {
    const stage = $("stage");
    stage.addEventListener("wheel", (e) => {
      const svg = stage.querySelector("svg"); if (!svg) return;
      e.preventDefault();
      const [px, py] = toViewBox(e, svg);
      zoomAt(px, py, e.deltaY < 0 ? 1.12 : 1 / 1.12);
    }, { passive: false });

    // Right-drag pans, the way a canvas tool does. The context menu is suppressed only
    // while dragging on the stage, so a right-click elsewhere still behaves normally.
    let drag = null;
    stage.addEventListener("contextmenu", (e) => e.preventDefault());
    stage.addEventListener("pointerdown", (e) => {
      if (e.button !== 2 && !(e.button === 0 && e.target.closest("[data-node],[data-table]") === null))
        return;
      const svg = stage.querySelector("svg"); if (!svg) return;
      const [px, py] = toViewBox(e, svg);
      drag = { px, py, x: view.x, y: view.y };
      stage.setPointerCapture(e.pointerId);
      stage.classList.add("grabbing");
    });
    stage.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const svg = stage.querySelector("svg"); if (!svg) return;
      const [px, py] = toViewBox(e, svg);
      view.x = drag.x + (px - drag.px);
      view.y = drag.y + (py - drag.py);
      applyView();
    });
    const end = (e) => {
      if (!drag) return;
      drag = null;
      stage.classList.remove("grabbing");
      if (e.pointerId != null && stage.hasPointerCapture?.(e.pointerId))
        stage.releasePointerCapture(e.pointerId);
    };
    stage.addEventListener("pointerup", end);
    stage.addEventListener("pointercancel", end);

    $("z-in").addEventListener("click", () => zoomAt(VW / 2, VH / 2, 1.25));
    $("z-out").addEventListener("click", () => zoomAt(VW / 2, VH / 2, 1 / 1.25));
    $("z-home").addEventListener("click", () => {
      open.origin = open.collector = open.bronze = open.silver = false;
      table = model = service = null;
      repaint();
      fit();
    });
  }

  /* ── health board ──────────────────────────────────────────
   *
   * Not a second flow diagram. Health answers three questions the pipeline view cannot:
   * what state is it in and why, what has it been doing for the last few minutes, and how
   * far is the tail from the mean. Everything here is either a window or a distribution —
   * an instantaneous 0/s says nothing, because it looks the same whether the number has
   * been zero all day or dropped from a spike one second ago.
   */
  let hist = [];
  const HIST_MAX = 300;
  let ceiling = 80;

  /** A sparkline over the window, with the current value emphasised at the endpoint. */
  function spark(parent, x, y, w, h, key, colour) {
    const pts = hist.slice(-120);
    if (pts.length < 2) {
      parent.append(el("text", { class: "sub", x, y: y + h / 2 }, "collecting…"));
      return 0;
    }
    // `key` may be a field name or a reader, because the contract board charts one slot
    // of an array (`rc`/`rb` carry the per-signal split) and a field name cannot say that.
    const vals = pts.map(typeof key === "function" ? key : (p) => p[key] || 0);
    const max = Math.max(...vals, 1e-9);
    const step = w / (pts.length - 1);
    const yy = (v) => y + h - (v / max) * h;
    const d = vals.map((v, i) => `${i ? "L" : "M"}${(x + i * step).toFixed(1)} ${yy(v).toFixed(1)}`).join(" ");
    parent.append(el("path", { d: `${d} L${x + w} ${y + h} L${x} ${y + h} Z`,
      fill: colour, opacity: .13, stroke: "none" }));
    parent.append(el("path", { d, fill: "none", stroke: colour, "stroke-width": 1.4,
      "stroke-linejoin": "round" }));
    parent.append(el("circle", { cx: x + w, cy: yy(vals[vals.length - 1]), r: 2.6, fill: colour }));
    return max;
  }

  /** Mode over time as coloured regions. Length of a region is time spent in that state —
   *  the one panel that says WHEN something changed and for how long. */
  function timeline(parent, x, y, w, h) {
    const pts = hist.slice(-120);
    if (pts.length < 2) return;
    const step = w / pts.length;
    const paint = { stream: "var(--pri)", batch: "var(--sec)", idle: "var(--rule)" };
    let i = 0;
    while (i < pts.length) {
      let j = i;
      while (j + 1 < pts.length && pts[j + 1].m === pts[i].m) j++;
      parent.append(el("rect", { x: x + i * step, y, width: Math.max(1, (j - i + 1) * step),
        height: h, fill: paint[pts[i].m] || "var(--rule)", opacity: pts[i].m === "idle" ? .5 : .8 }));
      i = j + 1;
    }
  }

  function renderHealth() {
    const r = snap || {};
    const svg = el("svg", { viewBox: `0 0 ${VW} ${VH}`, preserveAspectRatio: "xMidYMid meet" });
    const state = r.health || "idle";
    const tone = { ok: "var(--pri)", warn: "var(--sec)", fail: "var(--alarm)", idle: "var(--dim2)" }[state];

    // ── verdict: the state, and the sentence behind it ──
    svg.append(el("rect", { class: "nd", x: 30, y: 26, width: 940, height: 58, rx: 5,
        style: `stroke:${tone}` }),
      el("circle", { cx: 56, cy: 55, r: 7, fill: tone }),
      el("text", { class: "vtitle", x: 76, y: 50, style: `fill:${tone}` }, state.toUpperCase()),
      el("text", { class: "sub", x: 76, y: 68 }, r.health_note || ""),
      el("text", { class: "sub", x: 950, y: 50, style: "text-anchor:end" },
        `window ${Math.min(hist.length, 120)}s`),
      el("text", { class: "sub", x: 950, y: 68, style: "text-anchor:end" },
        `policy · ${graph?.contract?.validation || ""}`));

    // ── four rolling series: current, mean over the window, peak ──
    const sum = (o) => Object.values(o || {}).reduce((a, b) => a + b, 0);
    const rows = [
      ["INGEST",   "in", "var(--pri)",   sum(r.ingest_rate)],
      ["STORED",   "st", "var(--ter)",   r.persist_rate || 0],
      ["FLUSHES",  "fl", "var(--sec)",   r.flush_rate || 0],
      ["REJECTED", "rj", "var(--alarm)", sum(r.reject_rate)],
    ];
    rows.forEach(([label, key, colour, now], i) => {
      const y = 104 + i * 62;
      const vals = hist.slice(-120).map((h) => h[key] || 0);
      const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
      const peak = vals.length ? Math.max(...vals) : 0;
      svg.append(el("text", { class: "lbl", x: 30, y: y + 14 }, label),
        el("text", { class: "big", x: 30, y: y + 40, style: `fill:${colour}` }, fmt(now) + "/s"),
        el("text", { class: "sub", x: 152, y: y + 26 }, `avg ${fmt(avg)}`),
        el("text", { class: "sub", x: 152, y: y + 40 }, `peak ${fmt(peak)}`));
      spark(svg, 236, y + 2, 430, 44, key, colour);
    });

    // ── the tail the mean hides ──
    const lat = [["p50", r.export_latency_p50], ["p90", r.export_latency_p90],
                 ["p99", r.export_latency_p99]];
    const over = (r.export_latency_p99 || 0) > ceiling;
    svg.append(el("rect", { class: "nd", x: 706, y: 104, width: 264, height: 152, rx: 5,
        style: over ? "stroke:var(--sec)" : null }),
      el("text", { class: "lbl", x: 726, y: 128 }, "EXPORT LATENCY"),
      el("text", { class: "sub", x: 950, y: 128, style: "text-anchor:end" },
        `mean ${fmt(r.export_latency_ms)} ms`));
    const lmax = Math.max(ceiling, r.export_latency_p99 || 0, 1);
    lat.forEach(([name, v], i) => {
      const y = 152 + i * 32;
      svg.append(el("text", { class: "sub", x: 726, y: y + 9 }, name),
        el("rect", { x: 762, y, width: 168, height: 10, rx: 5, fill: "var(--rule)" }),
        el("rect", { x: 762, y, width: Math.max(3, ((v || 0) / lmax) * 168), height: 10, rx: 5,
          fill: i === 2 && over ? "var(--sec)" : "var(--pri)" }),
        el("text", { class: "sub", x: 950, y: y + 9, style: "text-anchor:end" },
          fmt(v) + " ms"));
    });
    svg.append(el("line", { x1: 762 + (ceiling / lmax) * 168, y1: 146,
      x2: 762 + (ceiling / lmax) * 168, y2: 250, stroke: "var(--sec)",
      "stroke-width": 1, "stroke-dasharray": "3 3", opacity: .8 }),
      el("text", { class: "sub", x: 726, y: 248 }, `ceiling ${ceiling} ms`));

    // ── mode over time ──
    svg.append(el("text", { class: "lbl", x: 706, y: 292 }, "MODE OVER TIME"));
    timeline(svg, 706, 300, 264, 16);
    svg.append(el("text", { class: "sub", x: 706, y: 330 },
      hist.length ? `${hist[0]?.m || ""} → ${r.mode || ""}` : "collecting…"));

    // ── rejections split by reason, because they are different problems ──
    const reasons = [
      ["contract", "bad payload · still exported under warn", "var(--sec)"],
      ["backpressure", "batch refused · producer retries", "var(--sec)"],
    ];
    svg.append(el("text", { class: "lbl", x: 30, y: 366 }, "WHY SIGNALS ARE REFUSED"));
    reasons.forEach(([key, what, colour], i) => {
      const y = 380 + i * 30, v = (r.reject_by_reason || {})[key] || 0;
      svg.append(el("text", { class: "sub", x: 30, y: y + 9 }, key),
        el("rect", { x: 128, y, width: 180, height: 9, rx: 4, fill: "var(--rule)" }),
        el("rect", { x: 128, y, width: v > 0 ? 180 : 2, height: 9, rx: 4,
          fill: v > 0 ? colour : "var(--rule)" }),
        el("text", { class: "sub", x: 322, y: y + 9 }, `${fmt(v)}/s · ${what}`));
    });

    // ── cumulative, for scale ──
    svg.append(el("text", { class: "lbl", x: 706, y: 366 }, "SINCE START"),
      el("text", { class: "sub", x: 706, y: 386 },
        `${fmt((r.totals || {}).persisted)} stored`),
      el("text", { class: "sub", x: 706, y: 402 },
        `${fmt(r.export_errors)} batches lost · no dead-letter queue`));

    $("stage-h").replaceChildren(svg);
    // The crumb says "validation ·" so it has to carry the validation policy. It was
    // rendered once from `s.mode` — the delivery mode — and never updated, so the live page
    // read "validation · idle".
    set("h-pol", `validation · ${policyOf()}`);
    $("legend-h").innerHTML = `<span class="on" style="color:${tone}">● ${state}</span>
      <span>${r.health_note || ""}</span>
      <span class="sp">series are a <b>${Math.min(hist.length, 120)}s window</b></span>
      <span>counts are <b>aggregate</b>, never per trace</span>`;
  }

  /** The receive-boundary policy, or `unknown` — never a guess. `warn` is the collector's
   *  own default, which makes it precisely the wrong fallback: a board showing `warn`
   *  because it has not loaded `/api/graph` yet is indistinguishable from one reading a
   *  real `warn`, and knowing which is the entire point of the panel. */
  const policyOf = () => graph?.contract?.validation || "unknown";

  /** Whichever board is visible, redrawn. Adding a third panel to three separate
   *  `hidden` tests is how one of them gets forgotten. */
  const drawBoards = () => {
    if (!$("v-health").hidden) renderHealth();
    if (!$("v-contract").hidden) renderContract();
    if (!$("v-watch").hidden) renderWatch();
  };

  /* ── contract board ────────────────────────────────────────
   *
   * V2.1. The receive boundary is the one place in this pipeline where a contract is
   * actually enforced, and until now nothing rendered it. Two sources, and the split
   * between them is the whole design:
   *
   *   the collector  knows HOW MANY violated and HOW (`signals_rejected_total{signal,
   *                  reason}`) but not WHO — its counters carry no service label.
   *   bronze         knows WHO, because under the default `warn` policy a violating
   *                  signal is exported anyway and the evidence lands in the table.
   *
   * One thing V2.1 asked for is NOT here and cannot be: contract-version adoption per
   * producer. `collector-rust/src/otlp.rs` injects `CONTRACT_VERSION` into every signal it
   * builds — "OTLP carries no contract_version field" — so every producer reads back the
   * collector's own constant. The panel would show 1.0.0 for everyone and mean nothing.
   */
  function renderContract() {
    const r = snap || {};
    const policy = policyOf();
    const svg = el("svg", { viewBox: `0 0 ${VW} ${VH}`, preserveAspectRatio: "xMidYMid meet" });
    const byReason = r.reject_by_reason || {};
    const contract = byReason.contract || 0;
    const ingest = Object.values(r.ingest_rate || {}).reduce((a, z) => a + z, 0);

    // ── the counterfactual, as the headline ──
    //
    // Under `warn` the collector counts what it would have dropped and exports it anyway,
    // so this number IS the answer to "what happens if we promote to strict" — measured,
    // not modelled. Under `off` the same counter reads zero for a completely different
    // reason, and saying so is the difference between evidence and a false all-clear.
    const off = policy === "off", strict = policy === "strict";
    const unknown = policy === "unknown";
    // Three different reasons this number can be zero, and only one of them is good news.
    // `off` means nothing is checked; `idle` means nothing arrived to check; clean means
    // traffic came through and passed. Collapsing them into one green headline is the
    // false all-clear this board exists to prevent.
    const idle = ingest <= 0;
    const clean = !off && !unknown && !idle && contract <= 0;
    const tone = off || unknown || idle ? "var(--dim2)" : contract > 0 ? "var(--sec)" : "var(--pri)";
    const head = unknown ? "POLICY UNREADABLE"
      : off ? "NOT MEASURED"
      : idle ? "NO TRAFFIC"
      : strict ? `${fmt(contract)}/s discarded at the boundary`
      : `${fmt(contract)}/s would be dropped under strict`;
    const note = unknown
      ? "the collector config is not mounted — the counters below are real, the policy is not known"
      : off
        ? "validation is off — this zero means nothing is checked, not that nothing is wrong"
      : idle
        ? "nothing is arriving, so nothing is being validated — the series below still hold the window"
      : strict ? "already dropping. flip to warn to keep the data while you fix producers"
      : clean
        ? "traffic is flowing and passing · this is the only zero that is good news"
        : `flagged and exported anyway · ${(contract / ingest * 100).toFixed(2)}% of throughput`;
    svg.append(el("rect", { class: "nd", x: 30, y: 26, width: 940, height: 62, rx: 5,
        style: `stroke:${tone}` }),
      el("text", { class: "lbl", x: 52, y: 46 }, "GRPC_VALIDATION"),
      el("text", { class: "vtitle", x: 52, y: 70, style: `fill:${tone}` }, policy.toUpperCase()),
      el("text", { class: "big", x: 950, y: 56, style: `text-anchor:end;fill:${tone}` }, head),
      el("text", { class: "sub", x: 950, y: 74, style: "text-anchor:end" }, note));

    // ── violation rate over the window, per signal ──
    //
    // Split by type rather than totalled: `signals_rejected_total` is labelled by both
    // `signal` and `reason`, so "which type is failing" is measured. A single line would
    // throw away the only thing that tells a metrics problem from a logs problem.
    const cols = [
      ["FAILING THE CONTRACT", "rc", "contract", 30,
       "at validate · under warn these still reach bronze"],
      ["REFUSED BY THE BUFFER", "rb", "backpressure", 520,
       "backpressure · the producer was told to retry"],
    ];
    cols.forEach(([title, key, reason, x, sub]) => {
      svg.append(el("text", { class: "lbl", x, y: 116 }, title),
        el("text", { class: "sub", x, y: 130 }, sub));
      LANES.forEach(([name, cls], i) => {
        const colour = { p1: "var(--pri)", p2: "var(--ter)", p3: "var(--sec)" }[cls];
        const y = 146 + i * 34;
        const now = ((r.reject_matrix || {})[reason] || {})[name] || 0;
        svg.append(el("text", { class: "sub", x, y: y + 20 }, name));
        // `spark` returns the peak it scaled to. Without it the shape has no units: a hump
        // reads the same at 4/s and 4000/s, and the figure beside it is the tick, not the
        // window. Two numbers, and the labels say which is which.
        const peak = spark(svg, x + 66, y, 250, 26, (p) => (p[key] || [])[i] || 0, colour);
        svg.append(el("text", { class: "val", x: x + 372, y: y + 20,
            style: `fill:${colour}` }, fmt(now) + "/s"),
          el("text", { class: "sub", x: x + 380, y: y + 20 },
            peak > 1e-6 ? `peak ${fmt(peak)}` : ""));
      });
    });

    // ── who, from bronze ──
    svg.append(el("text", { class: "lbl", x: 30, y: 272 }, "WHO IS VIOLATING"),
      el("text", { class: "sub", x: 168, y: 272 },
        "from bronze — the rows that landed anyway, so the evidence outlives the tick"));
    const rows = r.contract_violations || [];
    if (!rows.length) {
      svg.append(el("text", { class: "sub", x: 30, y: 300 },
        graph ? "no producer is missing a required key" : "collecting…"));
    }
    rows.slice(0, 4).forEach((v, i) => {
      const y = 286 + i * 38;
      // Share of that producer's ROWS, not of its key slots. The sum of per-key counts
      // over-counts a row missing four keys as four, which read as "80%" for a producer
      // whose every row is bad.
      const share = v.rows > 0 ? (v.violating / v.rows) * 100 : 0;
      const keys = Object.keys(v.missing);
      svg.append(el("rect", { class: "nd sub-nd", x: 30, y, width: 940, height: 32, rx: 3,
          style: "stroke:var(--sec)" }),
        el("text", { class: "txt", x: 44, y: y + 20 }, clip(v.service, 26)),
        el("text", { class: "sub", x: 260, y: y + 20 },
          `${fmt(v.violating)} of ${fmt(v.rows)} rows`),
        el("text", { class: "sub", x: 396, y: y + 20, style: "fill:var(--sec)" },
          `${keys.length} of 5 keys missing · ` + keys.join(" · ")),
        el("text", { class: "val", x: 956, y: y + 20, style: "fill:var(--sec)" },
          share.toFixed(0) + "%"));
    });

    $("stage-c").replaceChildren(svg);
    // The mode has no timeline because it has no history: `grpc_validation` is read from
    // the collector's config at startup and is not exposed as a metric, so it cannot
    // change without a restart. Drawing a state strip over a constant would invent one.
    $("legend-c").innerHTML = `<span class="on" style="color:${tone}">● policy <b>${policy}</b></span>
      <span>set at collector startup · not a metric, so it cannot change mid-window</span>
      <span class="sp">series are a <b>${Math.min(hist.length, 120)}s window</b></span>
      <span>producer rows refresh every <b>30s</b></span>`;
  }

  /* ── watchers board ────────────────────────────────────────
   *
   * V2.2, volume. Every competitor surveyed keeps its estimator private; the one credible
   * wedge available to an open project is to publish the algorithm, the window and the
   * meaning of the threshold — so the header states all three rather than saying
   * "ML-powered".
   *
   * The band drawn here IS the alerting rule: both come from `volume_state`, one place, one
   * set of numbers. Metaplane shipped a version where they were computed separately and
   * publicly called reconciling them a simplification.
   */
  //: Rank, tone, label. The two alerting severities used to differ ONLY by colour — both
  //: read "alerting" — which this repo's own rule forbids: colour is never the sole carrier.
  //: The label now names the threshold that was crossed, which doubles as publishing the
  //: rule on every row.
  const WSTATE = {
    fail:        [0, "var(--alarm)", "alerting ≥5σ"],
    warn:        [1, "var(--sec)",   "alerting ≥3σ"],
    unmonitored: [2, "var(--dim2)",  "not monitored"],
    passing:     [3, "var(--pri)",   "passing"],
  };

  /** One producer's series with its band behind it. The band is a filled region, not a pair
   *  of lines, because it is a region: "inside" is the whole claim. */
  function bandSpark(parent, x, y, w, h, v) {
    const pts = v.series || [];
    const vals = pts.map((p) => p[1]);
    const lo = Math.min(v.lo, ...vals, v.median), hi = Math.max(v.hi, ...vals, v.median);
    const span = Math.max(hi - lo, 1e-9);
    const yy = (n) => y + h - ((n - lo) / span) * h;
    const mon = v.state !== "unmonitored";
    if (mon) {
      parent.append(el("rect", { x, y: yy(v.hi), width: w, height: Math.max(1, yy(v.lo) - yy(v.hi)),
        fill: "var(--pri)", opacity: .10 }));
      parent.append(el("line", { x1: x, y1: yy(v.median), x2: x + w, y2: yy(v.median),
        stroke: "var(--dim2)", "stroke-width": 1, "stroke-dasharray": "3 4", opacity: .7 }));
    }
    if (pts.length < 2) return;
    // Buckets are plotted on their own timestamps, so a gap in the series is a gap on the
    // chart — a producer that went quiet leaves a hole rather than a straight line across
    // the absence, which is exactly the thing being measured.
    const t0 = pts[0][0], t1 = pts[pts.length - 1][0], dt = Math.max(t1 - t0, 1);
    const px = (t) => x + ((t - t0) / dt) * w;
    parent.append(el("path", { fill: "none", stroke: mon ? "var(--txt)" : "var(--dim2)",
      "stroke-width": 1.3, "stroke-linejoin": "round",
      d: pts.map((p, i) => `${i ? "L" : "M"}${px(p[0]).toFixed(1)} ${yy(p[1]).toFixed(1)}`).join(" ") }));
    // Only the points the rule would actually alert on are marked, so the dots and the
    // band can never disagree about what counts as an exception.
    if (mon) pts.filter((p) => p[1] < v.lo || p[1] > v.hi).forEach((p) =>
      parent.append(el("circle", { cx: px(p[0]), cy: yy(p[1]), r: 2.4, fill: "var(--alarm)" })));
  }

  function renderWatch() {
    const r = snap || {};
    const rows = r.volume || [];
    const svg = el("svg", { viewBox: `0 0 ${VW} ${VH}`, preserveAspectRatio: "xMidYMid meet" });

    // ── the method, published ──
    svg.append(el("rect", { class: "nd", x: 30, y: 18, width: 940, height: 58, rx: 5 }),
      el("text", { class: "lbl", x: 48, y: 36 }, "VOLUME · ROWS PER MINUTE, PER PRODUCER"),
      el("text", { class: "sub", x: 48, y: 52 },
        "median ± 3σ, σ from MAD × 1.4826 · stddev only where MAD collapses · "
        + "60-minute sliding window · 1-minute buckets, current one excluded (partial) · "
        + "warn 3σ · fail 5σ"),
      // Two different time scopes on one row, and a row marked PASSING with red points on
      // its series is unreadable until you are told which is which.
      el("text", { class: "sub", x: 48, y: 66 },
        "the verdict is the LATEST complete bucket · marked points are every bucket in the "
        + "window the same rule would have alerted on"));

    if (!rows.length) {
      svg.append(el("text", { class: "sub", x: 30, y: 140 },
        graph ? "no producer has enough buckets yet" : "collecting…"));
    }
    // Severity first, then a producer that went silent, then size. A watcher board sorted by
    // volume buries its one interesting row among seven identical ones; median stays as the
    // tiebreak so the order is otherwise stable tick to tick.
    const ranked = [...rows].sort((a, z) =>
      (WSTATE[a.state] || WSTATE.unmonitored)[0] - (WSTATE[z.state] || WSTATE.unmonitored)[0]
      || (z.absent > 0) - (a.absent > 0) || z.median - a.median);
    // What the eight rows add up to, so the answer does not require counting them.
    const tally = (f) => ranked.filter(f).length;
    const alerting = tally((v) => v.state === "warn" || v.state === "fail");
    const grey = tally((v) => v.state === "unmonitored");
    const silent = tally((v) => v.absent > 0);
    const fallback = tally((v) => v.estimator === "stddev");
    svg.append(el("text", { class: "sub", x: 30, y: 92 },
      `${ranked.length} producers · ${alerting} alerting · ${grey} not monitored · `
      + `${silent} silent in some bucket · ${fallback} on the stddev fallback`));
    // Seven bare figures per row and nothing saying which is which. Every column is named,
    // and the names carry their units, so a row can be read without the legend.
    [["PRODUCER", 30, ""], ["LAST 60 MIN · SHADED BAND = THE RULE", 210, ""],
     ["LATEST", 604, "text-anchor:end"], ["DISTANCE FROM MEDIAN", 616, ""],
     // "VERDICT · COVERAGE" grew right from 800 into "ESTIMATOR · FIT" growing left from
     // 956 and the two interleaved. The coverage line under each verdict already carries
     // its own unit ("34/34 buckets"), so the header does not need to repeat it.
     ["VERDICT", 800, ""], ["ESTIMATOR · FIT", 956, "text-anchor:end"],
    ].forEach(([t, x, style]) =>
      svg.append(el("text", { class: "lbl", x, y: 110, style: style || null }, t)));
    svg.append(el("line", { x1: 30, y1: 116, x2: 970, y2: 116,
      stroke: "var(--rule)", "stroke-width": 1 }));
    ranked.slice(0, 8).forEach((v, i) => {
      const y = 124 + i * 39, [, tone, label] = WSTATE[v.state] || WSTATE.unmonitored;
      svg.append(el("text", { class: "txt", x: 30, y: y + 22 }, clip(v.service, 24)));
      bandSpark(svg, 210, y + 4, 330, 30, v);
      svg.append(
        el("text", { class: "val", x: 604, y: y + 22, style: `fill:${tone}` }, fmt(v.latest)),
        el("text", { class: "sub", x: 616, y: y + 22 },
          v.state === "unmonitored" ? v.why : `${v.z}σ · median ${fmt(v.median)}`),
        el("text", { class: "lbl", x: 800, y: y + 18, style: `fill:${tone}` },
          label.toUpperCase()),
        // A separate axis from the band: the estate received something in these buckets and
        // this producer did not. Absence, as a signal — the one a table at rest cannot give.
        el("text", { class: "sub", x: 800, y: y + 30,
            style: v.absent > 0 ? "fill:var(--alarm)" : "fill:var(--dim)" },
          v.absent > 0 ? `silent in ${v.absent} of ${v.estate} buckets`
                       : `${v.seen}/${v.estate} buckets`),
        // Which estimator won, and how well its band actually fits the window it was built
        // from. `oob` is the number that decided: a band rejecting its own training data is
        // describing one mode of it, not the series.
        // One line, not two: end-anchored at 956 it ran left into the bucket count growing
        // right from 800, and they collided into "31/31 bucket5% of window out of band".
        el("text", { class: "sub", x: 956, y: y + 22, style: "text-anchor:end" },
          (v.estimator === "none" ? "—" : v.estimator)
          + (v.oob == null ? "" : ` · ${(v.oob * 100).toFixed(0)}% oob`)));
    });

    $("stage-w").replaceChildren(svg);
    $("legend-w").innerHTML =
      `<span><span class="gl" style="background:var(--pri)"></span>passing</span>
       <span><span class="gl" style="background:var(--sec)"></span>alerting ≥3σ</span>
       <span><span class="gl" style="background:var(--alarm)"></span>alerting ≥5σ</span>
       <span><span class="gl" style="background:var(--dim2)"></span>not monitored — grey is <b>not observed</b>, never fine</span>
       <span class="sp">the shaded band <b>is</b> the alerting rule</span>
       <span>bronze event time · <b>not</b> arrival</span>`;
  }

  /* ── per-tick visibility ───────────────────────────────────── */
  function density(s) {
    const ing = s.ingest_rate || {};
    show("logs", dots(ing.logs || 0));
    show("trace", dots(ing.trace || 0));
    show("metrics", dots(ing.metrics || 0));
    const inFlight = Math.min(3, Math.round((s.flush_rate || 0) * 3.2 / 2));
    show("blk", inFlight);
    show("burst", inFlight);
    const total = Object.values(ing).reduce((a, z) => a + z, 0);
    const rej = Object.values(s.reject_rate || {}).reduce((a, z) => a + z, 0);
    const live = total > 0 ? 1 : 0;
    // Inside a container every hop carries all three types, so each is shown or hidden
    // on its own rather than as a single lane.
    for (let i = 0; i < 12; i++)
      LANES.forEach(([n]) => show(`oe${i}-${n}`, live * ((ing[n] || 0) > 0 ? 2 : 0)));
    for (let i = 0; i < 2; i++)
      LANES.forEach(([n]) => show(`ce${i}-${n}`, live * ((ing[n] || 0) > 0 ? 2 : 0)));
    // Each strand runs on THAT table's growth. `bronze_rate` is per table, so gating all
    // four on one estate-wide figure had the logs strand moving through a metrics-only
    // scenario — the same defect as a hard-coded colour, moved into the gate.
    const tnames = Object.keys(graph?.tables || {});
    for (let i = 0; i < 6; i++)
      show(`be${i}`, ((s.bronze_rate || {})[tnames[i]] || 0) > 0 ? 3 : 0);
    // A derivation strand runs on the growth of the bronze table it reads, for the same
    // reason: the MV fires on that table's insert and on nothing else. A silent source
    // means a still strand, not a strand animating over nothing.
    derives().forEach(([from], i) =>
      show(`dv${i}`, ((s.bronze_rate || {})[from] || 0) > 0 ? 2 : 0));
    // Each tap runs only while its own outcome is happening. A pipeline losing nothing
    // should have three still lines, not three animations implying otherwise.
    //
    // And per SIGNAL TYPE, not per tap: `reject_matrix` is the `signal` × `reason`
    // cross-product, so if only metrics fail the contract, exactly one amber dot falls.
    // The previous version ran a single hard-coded pool per tap, which meant every
    // rejection of any type fell amber — right by accident for metrics, wrong for the
    // other two.
    const byReason = s.reject_by_reason || {};
    const mx = s.reject_matrix || {};
    ["contract", "backpressure"].forEach((reason, i) => {
      const per = mx[reason] || {};
      LANES.forEach(([n]) => {
        const on = (per[n] || 0) > 0 ? 2 : 0;
        show(`tap${i}-${n}`, on);
        show(`ret${i}-${n}`, on);   // absent unless this outcome carries data back
      });
    });
    // The drop is the one payload whose type is not measured — one mixed sphere, ringed.
    show("tap2", (s.drop_rate || 0) > 0 ? 2 : 0);
    // The lines themselves brighten here rather than at render: whether an outcome is
    // live is throughput, not structure, and gating it on a repaint left a tap dim while
    // dots were visibly falling down it.
    [(byReason.contract || 0) > 0, (byReason.backpressure || 0) > 0, (s.drop_rate || 0) > 0]
      .forEach((on, i) => ["tap", "tapv", "ret"].forEach((pre) =>
        $(`${pre}${i}`)?.classList.toggle("live", on)));
    show("h-ok", (s.persist_rate || 0) > 0 ? 4 : 0);
    show("h-rej", rej > 0 ? 2 : 0);
    show("h-drop", (s.drop_rate || 0) > 0 ? 2 : 0);
  }

  /* ── structural repaint ────────────────────────────────────── */
  function repaint() {
    // Every box that can expand belongs in this key. Leaving one out does not fail loudly:
    // the click flips `open[id]`, the key does not change, repaint returns early and the box
    // simply never opens. `silver` was missing and the bug looked like a dead click.
    const key = [snap?.mode || "", graph ? 1 : 0, open.origin, open.collector, open.bronze,
                 open.silver, table, model, service].join("|");
    if (key === painted) return false;
    const first = painted === "";
    painted = key;
    render();          // refits itself when the drawing changed size
    renderHealth();
    return true;
  }

  const set = (id, v) => { const n = $(id); if (n) n.textContent = v; };
  function apply(s) {
    snap = s;
    const ing = Object.values(s.ingest_rate || {}).reduce((a, z) => a + z, 0);
    const rej = Object.values(s.reject_rate || {}).reduce((a, z) => a + z, 0);
    set("t-in", fmt(ing)); set("t-fl", fmt(s.flush_rate)); set("t-bt", fmt(s.records_per_flush));
    set("t-lt", fmt(s.export_latency_ms)); set("t-ps", fmt(s.persist_rate)); set("t-rj", fmt(rej));
    $("tile-rj")?.classList.toggle("bad", rej > 0);
    $("m-col")?.setAttribute("data-up", s.collector_up ? "y" : "n");
    $("m-ch")?.setAttribute("data-up", s.clickhouse_up ? "y" : "n");
    // `rc`/`rb` must be pushed here too, not only served by `/api/history`. The client keeps
    // its own window, so ~120 ticks after load every visible point is one of these — and
    // without the per-signal reject arrays the Contract board's sparklines flatlined to zero
    // while violations were happening. Same shape the server writes, so the two are one
    // series; `LANES` fixes the order.
    const cm = s.reject_matrix || {};
    const bySignal = (reason) => LANES.map(([n]) => (cm[reason] || {})[n] || 0);
    hist.push({ t: s.ts, in: sum2(s.ingest_rate), fl: s.flush_rate, lat: s.export_latency_ms,
      st: s.persist_rate, rj: sum2(s.reject_rate),
      rc: bySignal("contract"), rb: bySignal("backpressure"),
      dr: s.drop_rate, m: s.mode });
    if (hist.length > HIST_MAX) hist.shift();
    // A board only draws when it is on screen. Neither has animation to preserve, but
    // rebuilding a chart nobody is looking at, once a second, is work for nothing.
    drawBoards();
    if (repaint()) return;          // structural only; throughput never rebuilds
    density(s);
  }
  const sum2 = (o) => Object.values(o || {}).reduce((a, b) => a + b, 0);

  /* ── palette · dashboards · stream ─────────────────────────── */
  const setWorld = (w) => {
    document.documentElement.dataset.world = w;
    $("pal").setAttribute("aria-pressed", String(w === "substrate"));
    try { localStorage.setItem("sentinel.world", w); } catch (_) { /* private mode */ }
  };
  let saved = "command";
  try { saved = localStorage.getItem("sentinel.world") || "command"; } catch (_) { /* ignore */ }
  setWorld(saved);
  $("pal").addEventListener("click", () =>
    setWorld(document.documentElement.dataset.world === "command" ? "substrate" : "command"));

  const dtabs = [...document.querySelectorAll('[role="tab"]')];
  dtabs.forEach((t, i) => t.addEventListener("click", () => {
    dtabs.forEach((x, k) => {
      const on = k === i;
      x.setAttribute("aria-selected", String(on));
      x.tabIndex = on ? 0 : -1;
      $(x.getAttribute("aria-controls")).hidden = !on;
    });
    drawBoards();
  }));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("z-home").click();
  });

  // Re-fit when the box changes size — maximising, splitting the screen, switching tabs.
  // `fit()` scales the graph into the viewBox it is given, and the viewBox now tracks the
  // window, so without this the graph kept the scale it was given at load.
  const refit = () => requestAnimationFrame(() => { if (lastLayout) fit(); });
  addEventListener("resize", refit);
  if (window.ResizeObserver) new ResizeObserver(refit).observe($("stage"));

  wireViewport();
  render(); fit();
  // Seed from the server's window so a page opened now shows the last few minutes rather
  // than an empty chart, and two viewers see the same history.
  fetch("/api/history").then((r) => r.json()).then((h) => {
    hist = h.points || [];
    ceiling = h.ceiling_ms || ceiling;
    drawBoards();
  }).catch(() => {});
  fetch("/api/graph").then((r) => r.json()).then((g) => { graph = g; painted = ""; repaint(); fit(); })
    .catch(() => {});
  const es = new EventSource("/stream");
  es.onmessage = (e) => { try { apply(JSON.parse(e.data)); } catch (_) { /* bad frame */ } };
})();
