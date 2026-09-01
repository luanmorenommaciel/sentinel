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

  //: Collapsed and expanded footprints. Layout is computed from these, so a box growing
  //: pushes its neighbours rather than overlapping them.
  const SIZE = {
    origin:    { closed: [212, 196], open: [742, 248], openSel: [742, 386] },
    collector: { closed: [252, 152], open: [500, 344] },
    bronze:    { closed: [176, 136], open: [318, 252] },
  };

  let graph = null, snap = null, table = "otel_logs";
  //: A selected service filters what the graph reports about bronze. It cannot filter the
  //: live rates: `sentinel_signals_ingested_total` carries a `signal` label and no service
  //: label, so per-service throughput simply does not exist upstream of ClickHouse. The
  //: legend says so rather than letting the lanes imply otherwise.
  let service = null;
  const open = { origin: false, collector: false, bronze: false };
  let painted = "", pools = {};
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
  const pipe = (parent, id, d, gauge = "", attrs = {}) => {
    parent.append(el("path", { class: "pw " + gauge, d }),
                  el("path", { class: "pb " + gauge, id, d, ...attrs }));
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
    for (const id of ["origin", "collector", "bronze"]) {
      const key = !open[id] ? "closed"
        : (id === "origin" && service && SIZE[id].openSel) ? "openSel" : "open";
      const [w, h] = SIZE[id][key];
      boxes[id] = { id, x, y: CY - h / 2, w, h };
      x += w + GAP;
    }
    // Signal lanes leave the origin container's right edge, not individual services: the
    // three types are a property of every service, not of any one of them.
    const o = boxes.origin, c = boxes.collector, b = boxes.bronze;
    o.out = [0.28, 0.5, 0.72].map((f) => [o.x + o.w, o.y + o.h * f]);

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
    return { boxes, width: x - GAP + 40, height: 440 };
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

  /* ── node bodies ───────────────────────────────────────────── */
  function originBody(g, b, edges, fx) {
    const r = snap || {}, ing = r.ingest_rate || {};
    if (!open.origin) {
      const rows = [["logs", ing.logs], ["traces", ing.trace], ["metrics", ing.metrics]];
      rows.forEach(([name, v], i) => g.append(
        el("text", { class: "txt", x: b.x + 18, y: b.y + 66 + i * 26 }, name),
        el("text", { class: "val", x: b.x + b.w - 18, y: b.y + 66 + i * 26 }, fmt(v))));
      g.append(el("text", { class: "sub", x: b.x + 18, y: b.y + 158 },
        `${graph?.topology?.nodes?.length || 0} services · ${graph?.topology?.edges?.length || 0} edges`));
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
      const step = (b.h - 56) / list.length;
      pos[n.id] = { x: b.x + 20 + (+d) * (NW + 52), y: b.y + 44 + step * i + (step - NH) / 2 };
    }));
    // Internal edges first, so nodes paint over them.
    //
    // Routed by `fan` rather than `route`: with 52px between columns there is no room for
    // a 45° elbow, and every edge that changes row would overshoot. The stub is staggered
    // per source, because edges leaving one node share a PORT and would otherwise share a
    // vertical column too — three 13px casings on one x is a blob, not a fan.
    const legs = {};
    t.edges.forEach((e, i) => {
      const a = pos[e.from], z = pos[e.to];
      if (!a || !z) return;
      // One casing apart, so three legs from one node stay three legs. Clamped to leave
      // the last chamfer room to land, which is what caps the fan at ~3 legs per node.
      const k = (legs[e.from] = (legs[e.from] ?? -1) + 1);
      const gap = z.x - (a.x + NW);
      pipe(edges, `oe${i}`, fan(a.x + NW, a.y + NH / 2, z.x, z.y + NH / 2,
        Math.min(gap - 12, 14 + k * 14)));
      mouth(a.x + NW, a.y + NH / 2);
      mouth(z.x, z.y + NH / 2);
      flow3(fx, `oe${i}`, `oe${i}`, 2.6 + (i % 3) * .4, 3.2, 2);
    });
    const byName = Object.fromEntries((r.lineage || []).map((z) => [z.service, z]));
    t.nodes.forEach((n) => {
      const p = pos[n.id], row = byName[n.service], sel = n.service === service;
      const node = el("g", { class: "hit", tabindex: "0", role: "button",
        "aria-pressed": String(sel), "aria-label": `Trace ${n.service} through the pipeline` });
      node.dataset.service = n.service;
      // Name on its own line, figure on the next: at 196px a 24-character service name
      // and a right-aligned count were landing on the same pixels.
      node.append(
        el("rect", { class: "nd sub-nd" + (sel ? " sel" : ""), x: p.x, y: p.y,
          width: NW, height: NH, rx: 3 }),
        el("text", { class: "txt", x: p.x + 12, y: p.y + 17 },
          clip(n.service, n.roots ? 22 : 27)),
        el("text", { class: "sub", x: p.x + 12, y: p.y + 33 },
          `${n.kind} · ${n.latency_ms ?? "?"} ms`),
        el("text", { class: "val", x: p.x + NW - 12, y: p.y + 33 }, row ? fmt(row.total) : "—"));
      if (n.roots) node.append(el("text", { class: "cue end", x: p.x + NW - 12, y: p.y + 17 }, "ROOT"));
      g.append(node);
    });
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
    const policy = graph?.contract?.validation || "warn";
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
  function datasheet(parent, b) {
    const d = (graph?.tables || {})[table];
    if (!d) return;
    const x = b.x + b.w + 40, y = b.y, w = 320, h = b.h;
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

  /* ── render ────────────────────────────────────────────────── */
  const TITLE = { origin: "ORIGIN", collector: "COLLECTOR-RUST", bronze: "BRONZE" };

  function render() {
    const stage = $("stage");
    pools = {};
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

    for (const id of ["origin", "collector", "bronze"]) {
      const b = B[id];
      const g = el("g", { class: "hit node", tabindex: "0", role: "button",
        "aria-expanded": String(open[id]),
        "aria-label": `${open[id] ? "Collapse" : "Expand"} ${TITLE[id]}` });
      g.dataset.node = id;
      g.append(el("rect", { class: "nd" + (open[id] ? " open" : ""), x: b.x, y: b.y,
          width: b.w, height: b.h, rx: 5 }),
        el("text", { class: "lbl", x: b.x + 18, y: b.y + 26 }, TITLE[id]),
        el("text", { class: "cue", x: b.x + b.w - 18, y: b.y + 26,
          style: "text-anchor:end" }, open[id] ? "CLOSE ▾" : "OPEN ▸"));
      nodes.append(g);
      ({ origin: originBody, collector: collectorBody, bronze: bronzeBody }[id])(g, b, edges, fx);
    }
    if (open.bronze) datasheet(nodes, B.bronze);
    // The burst only means something when a batch is actually arriving.
    show("burst", 0);

    stage.replaceChildren(svg);
    stage.querySelectorAll("[data-node]").forEach((n) => {
      n.addEventListener("click", () => { open[n.dataset.node] = !open[n.dataset.node]; repaint(); });
      n.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); n.click(); }
      });
    });
    stage.querySelectorAll("[data-table]").forEach((n) => {
      n.addEventListener("click", (e) => { e.stopPropagation(); table = n.dataset.table; repaint(); });
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
    L.content = { w: L.width, h: L.height };
    lastLayout = L;
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
  function fit() {
    if (!lastLayout) return;
    const { w, h } = lastLayout.content;
    view.k = Math.min(1, Math.min((VW - 20) / w, (VH - 20) / h));
    view.x = (VW - w * view.k) / 2;
    view.y = (VH - h * view.k) / 2;
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
      open.origin = open.collector = open.bronze = false;
      table = "otel_logs";
      service = null;
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
    const vals = pts.map((p) => p[key] || 0);
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
    $("legend-h").innerHTML = `<span class="on" style="color:${tone}">● ${state}</span>
      <span>${r.health_note || ""}</span>
      <span class="sp">series are a <b>${Math.min(hist.length, 120)}s window</b></span>
      <span>counts are <b>aggregate</b>, never per trace</span>`;
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
    const key = [snap?.mode || "", graph ? 1 : 0, open.origin, open.collector, open.bronze,
                 table, service].join("|");
    if (key === painted) return false;
    const first = painted === "";
    painted = key;
    render();
    renderHealth();
    if (first) fit();
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
    hist.push({ t: s.ts, in: sum2(s.ingest_rate), fl: s.flush_rate, lat: s.export_latency_ms,
      st: s.persist_rate, rj: sum2(s.reject_rate), dr: s.drop_rate, m: s.mode });
    if (hist.length > HIST_MAX) hist.shift();
    // Health only draws when it is on screen. It has no animation to preserve, but
    // rebuilding a chart nobody is looking at, once a second, is work for nothing.
    if (!$("v-health").hidden) renderHealth();
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
    if (!$("v-health").hidden) renderHealth();
  }));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("z-home").click();
  });

  wireViewport();
  render(); fit();
  // Seed from the server's window so a page opened now shows the last few minutes rather
  // than an empty chart, and two viewers see the same history.
  fetch("/api/history").then((r) => r.json()).then((h) => {
    hist = h.points || [];
    ceiling = h.ceiling_ms || ceiling;
    if (!$("v-health").hidden) renderHealth();
  }).catch(() => {});
  fetch("/api/graph").then((r) => r.json()).then((g) => { graph = g; painted = ""; repaint(); fit(); })
    .catch(() => {});
  const es = new EventSource("/stream");
  es.onmessage = (e) => { try { apply(JSON.parse(e.data)); } catch (_) { /* bad frame */ } };
})();
