"""Dependency-free SVG charts: season overview of one run, observed-vs-simulated scatter, and line comparisons."""
import math
from xml.sax.saxutils import escape

FONT = 'font-family="Helvetica, Arial, sans-serif"'
PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]
GRID, AXIS, TEXT = "#e5e7eb", "#6b7280", "#111827"


def _nice_step(span, n=5):
    raw = span / n
    mag = 10.0 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= raw:
            return m * mag
    return 10 * mag


def _axis(lo, hi, n=5):
    """Round axis limits and tick values."""
    if hi <= lo:
        hi = lo + 1.0
    step = _nice_step(hi - lo, n)
    top = step * -(-hi // step)
    bot = step * (lo // step)
    ticks, v = [], bot
    while v <= top + 1e-9:
        ticks.append(round(v, 10))
        v += step
    return bot, top, ticks


def _fmt(v):
    return f"{v:.0f}" if abs(v - round(v)) < 1e-9 or abs(v) >= 100 else f"{v:.2g}"


def _wrap(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" {FONT}>'
            f'<rect width="100%" height="100%" fill="white"/>' + "".join(body) + "</svg>")


def _text(x, y, s, size=12, anchor="start", weight="normal", fill=TEXT, rotate=None):
    t = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" '
            f'fill="{fill}"{t}>{escape(str(s))}</text>')


def _legend(x, y, entries, title=None):
    """entries: (label, color, kind) with kind in line|dash|dot|ring. Returns (fragments, height used)."""
    out, dy = [], 0
    if title:
        out.append(_text(x, y, title, 12, weight="bold"))
        dy = 20
    for label, color, kind in entries:
        cy = y + dy
        if kind in ("line", "dash"):
            d = ' stroke-dasharray="5 3"' if kind == "dash" else ""
            out.append(f'<line x1="{x}" x2="{x + 22}" y1="{cy - 4}" y2="{cy - 4}" stroke="{color}" stroke-width="2.4"{d}/>')
        elif kind == "ring":
            out.append(f'<circle cx="{x + 11}" cy="{cy - 4}" r="5" fill="white" stroke="{color}" stroke-width="2"/>')
        else:
            out.append(f'<circle cx="{x + 11}" cy="{cy - 4}" r="5" fill="{color}" fill-opacity="0.8"/>')
        out.append(_text(x + 30, cy, label, 12))
        dy += 20
    return out, dy


def _notes(x, y, lines):
    return [_text(x, y + 18 * i, s, 12, fill="#374151") for i, s in enumerate(lines)]


# ---------------------------------------------------------------- season overview
def _panel(y0, h, series, title, ylabel, xs, pl, pw, ymin=0.0):
    allv = [v for _, vals, _ in series for v in vals] or [0.0]
    lo, hi, ticks = _axis(min([ymin] + allv), max(allv + [ymin + 1e-9]))
    xmax = max(xs) or 1
    X = lambda x: pl + pw * x / xmax
    Y = lambda v: y0 + h * (1 - (v - lo) / (hi - lo))
    out = [_text(pl, y0 - 8, title, 13, weight="bold")]
    for t in ticks:
        out.append(f'<line x1="{pl}" x2="{pl + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="{GRID}"/>')
        out.append(_text(pl - 7, Y(t) + 4, _fmt(t), 11, "end", fill=AXIS))
    out.append(_text(14, y0 + h / 2, ylabel, 11, "middle", fill=AXIS, rotate=-90))
    for label, vals, color in series:
        pts = " ".join(f"{X(x):.1f},{Y(v):.1f}" for x, v in zip(xs, vals))
        out.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>')
    return out, X, Y


def _xticks(y_axis, xs, X, pl, pw, step=20):
    out = [f'<line x1="{pl}" x2="{pl + pw}" y1="{y_axis}" y2="{y_axis}" stroke="{AXIS}"/>']
    for d in range(0, int(max(xs)) + 1, step):
        out.append(f'<line x1="{X(d):.1f}" x2="{X(d):.1f}" y1="{y_axis}" y2="{y_axis + 4}" stroke="{AXIS}"/>')
        out.append(_text(X(d), y_axis + 17, d, 11, "middle", fill=AXIS))
    return out


def run_svg(daily, title="radicle season overview", events=None):
    """daily: the `daily` list from models.crop.simulate. events: [(day_index, label)] drawn as dashed vertical lines."""
    if not daily:
        raise ValueError("no daily results to plot")
    xs = list(range(len(daily)))
    col = lambda k: [r[k] for r in daily]
    W, pl, pr, ph, gap, top = 900, 70, 190, 125, 48, 60
    pw = W - pl - pr
    panels = [("Root-zone water: depletion vs total available water", "mm",
               [("depletion", col("depletion_mm"), PALETTE[0]), ("available water (TAW)", col("taw_mm"), PALETTE[1])]),
              ("Root-zone salinity", "ECe (dS/m)", [("ECe", col("ece"), PALETTE[1])]),
              ("Disease severity", "fraction 0-1", [("severity", col("disease"), PALETTE[3])]),
              ("Biomass", "g/m2", [("biomass", col("biomass_g_m2"), PALETTE[2])])]
    H = top + (len(panels) + 1) * (ph + gap) + 20
    body = [_text(pl, 28, title, 17, weight="bold")]
    for i, (t, yl, s) in enumerate(panels):
        y0 = top + i * (ph + gap)
        frag, X, Y = _panel(y0, ph, s, t, yl, xs, pl, pw)
        body += frag + _xticks(y0 + ph, xs, X, pl, pw)
        for ex, label in events or []:
            body.append(f'<line x1="{X(ex):.1f}" x2="{X(ex):.1f}" y1="{y0}" y2="{y0 + ph}" stroke="#374151" stroke-dasharray="4 3"/>')
            if i == 0:
                body.append(_text(X(ex) + 4, y0 + 12, label, 11, fill="#374151"))
        body += _legend(pl + pw + 18, y0 + 14, [(l, c, "line") for l, _, c in s])[0]
    # rain and irrigation bars
    y0 = top + len(panels) * (ph + gap)
    rain, irr = col("rain"), col("irrigation")
    lo, hi, ticks = _axis(0, max(rain + irr + [1.0]))
    X = lambda x: pl + pw * x / (max(xs) or 1)
    Y = lambda v: y0 + ph * (1 - v / hi)
    body.append(_text(pl, y0 - 8, "Water inputs per day", 13, weight="bold"))
    for t in ticks:
        body.append(f'<line x1="{pl}" x2="{pl + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="{GRID}"/>' + _text(pl - 7, Y(t) + 4, _fmt(t), 11, "end", fill=AXIS))
    body.append(_text(14, y0 + ph / 2, "mm/day", 11, "middle", fill=AXIS, rotate=-90))
    bw = max(1.2, pw / len(xs) * 0.8)
    for series, color in ((rain, "#38bdf8"), (irr, PALETTE[0])):
        for x, v in zip(xs, series):
            if v > 0:
                body.append(f'<rect x="{X(x) - bw / 2:.1f}" y="{Y(v):.1f}" width="{bw:.1f}" height="{y0 + ph - Y(v):.1f}" fill="{color}" fill-opacity="0.85"/>')
    body += _xticks(y0 + ph, xs, X, pl, pw)
    body.append(_text(pl + pw / 2, y0 + ph + 38, "days after sowing", 12, "middle", fill=AXIS))
    body += _legend(pl + pw + 18, y0 + 14, [("rain", "#38bdf8", "line"), ("irrigation", PALETTE[0], "line")])[0]
    return _wrap(W, H, body)


def season_svg(result, title):
    """Season overview of a full `simulate` result, marking anthesis/silking."""
    daily, s = result["daily"], result["summary"]
    dates = [r["date"] for r in daily]
    ev = [(dates.index(s["anthesis_date"]), "anthesis")] if s.get("anthesis_date") in dates else []
    return run_svg(daily, title, ev)


# ---------------------------------------------------------------- scatter
def scatter_svg(pairs, xlabel, ylabel, title, labels=None, legend=None, notes=None, hollow=None, hollow_label=None,
                point_label="simulation"):
    """pairs: [(observed, simulated)] drawn as filled dots with a 1:1 line on equal axes.
    labels: per-point colour index; legend: names for those colours; hollow: a second set of pairs drawn as rings
    (e.g. before calibration); notes: lines of text (statistics) shown beside the plot."""
    if not pairs:
        raise ValueError("no points to plot")
    allp = list(pairs) + list(hollow or [])
    lo, hi, ticks = _axis(0.0, max(max(p) for p in allp) * 1.05)
    S, ml, mt, mb, W = 470, 70, 56, 62, 720
    X = lambda v: ml + (S - ml - 20) * (v - lo) / (hi - lo)
    Y = lambda v: mt + (S - mt - mb) * (1 - (v - lo) / (hi - lo))
    body = [_text(ml, 30, title, 16, weight="bold"),
            f'<rect x="{ml}" y="{mt}" width="{S - ml - 20}" height="{S - mt - mb}" fill="none" stroke="#d1d5db"/>']
    for t in ticks:
        body.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{mt}" y2="{S - mb}" stroke="{GRID}"/>'
                    f'<line x1="{ml}" x2="{S - 20}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="{GRID}"/>'
                    + _text(X(t), S - mb + 18, _fmt(t), 11, "middle", fill=AXIS) + _text(ml - 8, Y(t) + 4, _fmt(t), 11, "end", fill=AXIS))
    body.append(f'<line x1="{X(lo)}" y1="{Y(lo)}" x2="{X(hi)}" y2="{Y(hi)}" stroke="#6b7280" stroke-width="1.5" stroke-dasharray="6 4"/>')
    body.append(_text(X(hi) - 4, Y(hi) + 28, "1:1 line", 11, "end", fill="#6b7280"))
    body.append(_text(ml + (S - ml - 20) / 2, S - 14, xlabel, 13, "middle"))
    body.append(_text(16, mt + (S - mt - mb) / 2, ylabel, 13, "middle", rotate=-90))
    for o, s in hollow or []:
        body.append(f'<circle cx="{X(o):.1f}" cy="{Y(s):.1f}" r="4.5" fill="white" stroke="#6b7280" stroke-width="1.6"/>')
    for k, (o, s) in enumerate(pairs):
        c = PALETTE[(labels[k] if labels else 0) % len(PALETTE)]
        body.append(f'<circle cx="{X(o):.1f}" cy="{Y(s):.1f}" r="5" fill="{c}" fill-opacity="0.8" stroke="white" stroke-width="0.8"/>')
    x0, y0 = S + 20, mt + 4
    entries = []
    if legend:
        entries += [(n, PALETTE[i % len(PALETTE)], "dot") for i, n in enumerate(legend)]
    elif hollow:
        entries.append((point_label, PALETTE[0], "dot"))
    if hollow:
        entries.append((hollow_label or "other", "#6b7280", "ring"))
    leg, dy = _legend(x0, y0, entries, "Legend")
    body += leg
    if notes:
        body += [_text(x0, y0 + dy + 14, "Statistics", 12, weight="bold")] + _notes(x0, y0 + dy + 34, notes)
    return _wrap(W, S, body)


# ---------------------------------------------------------------- lines
def lines_svg(series, xlabel, ylabel, title, notes=None):
    """series: [(label, [(x, y), ...], color_index, dashed)]; a legend sits beside the plot."""
    pts_all = [p for _, pts, _, _ in series for p in pts]
    if not pts_all:
        raise ValueError("no points to plot")
    xlo, xhi, xt = _axis(min(p[0] for p in pts_all), max(p[0] for p in pts_all))
    ylo, yhi, yt = _axis(0.0, max(p[1] for p in pts_all) * 1.05)
    W, H, ml, mt, mb, pw = 780, 430, 70, 56, 62, 470
    X = lambda v: ml + pw * (v - xlo) / (xhi - xlo)
    Y = lambda v: mt + (H - mt - mb) * (1 - (v - ylo) / (yhi - ylo))
    body = [_text(ml, 30, title, 16, weight="bold"), f'<rect x="{ml}" y="{mt}" width="{pw}" height="{H - mt - mb}" fill="none" stroke="#d1d5db"/>']
    for t in xt:
        body.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{mt}" y2="{H - mb}" stroke="{GRID}"/>' + _text(X(t), H - mb + 18, _fmt(t), 11, "middle", fill=AXIS))
    for t in yt:
        body.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="{GRID}"/>' + _text(ml - 8, Y(t) + 4, _fmt(t), 11, "end", fill=AXIS))
    body.append(_text(ml + pw / 2, H - 16, xlabel, 13, "middle"))
    body.append(_text(16, mt + (H - mt - mb) / 2, ylabel, 13, "middle", rotate=-90))
    entries = []
    for label, pts, ci, dashed in series:
        c = PALETTE[ci % len(PALETTE)]
        d = ' stroke-dasharray="6 4"' if dashed else ""
        body.append(f'<polyline fill="none" stroke="{c}" stroke-width="2.2"{d} points="{" ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in pts)}"/>')
        for x, y in pts:
            body.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="3.5" fill="{"white" if dashed else c}" stroke="{c}" stroke-width="1.6"/>')
        entries.append((label, c, "dash" if dashed else "line"))
    leg, dy = _legend(ml + pw + 24, mt + 4, entries, "Legend")
    body += leg
    if notes:
        body += [_text(ml + pw + 24, mt + dy + 14, "Notes", 12, weight="bold")] + _notes(ml + pw + 24, mt + dy + 34, notes)
    return _wrap(W, H, body)
