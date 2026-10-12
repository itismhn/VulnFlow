"""Tiny dependency-free SVG charts for PDF/HTML reports."""

import math
from collections.abc import Sequence
from html import escape

SEVERITY_COLORS = {
    "critical": "#b91c1c",
    "high": "#ea580c",
    "medium": "#ca8a04",
    "low": "#2563eb",
    "info": "#64748b",
}


def donut(values: dict[str, int], size: int = 180) -> str:
    total = sum(values.values())
    r, stroke = size / 2 - 14, 26
    c = 2 * math.pi * r
    parts, offset = [], 0.0
    for name, value in values.items():
        if not value:
            continue
        length = c * value / total
        parts.append(
            f'<circle r="{r:.1f}" cx="{size / 2}" cy="{size / 2}" fill="none" '
            f'stroke="{SEVERITY_COLORS.get(name, "#94a3b8")}" stroke-width="{stroke}" '
            f'stroke-dasharray="{length:.2f} {c - length:.2f}" stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {size / 2} {size / 2})"/>'
        )
        offset += length
    if not parts:
        parts.append(
            f'<circle r="{r:.1f}" cx="{size / 2}" cy="{size / 2}" fill="none" stroke="#e2e8f0" stroke-width="{stroke}"/>'
        )
    label = (
        f'<text x="50%" y="48%" text-anchor="middle" font-size="26" font-weight="700" fill="#0f172a">{total}</text>'
        f'<text x="50%" y="62%" text-anchor="middle" font-size="11" fill="#64748b">open findings</text>'
    )
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">{"".join(parts)}{label}</svg>'


def stacked_bars(
    labels: Sequence[str], series: dict[str, Sequence[int]], width: int = 640, height: int = 220
) -> str:
    """Horizontal stacked bars, one row per label."""
    if not labels:
        return ""
    row_h = min(28, (height - 10) / len(labels))
    label_w = 150
    totals = [sum(series[s][i] for s in series) for i in range(len(labels))]
    max_total = max(totals) or 1
    scale = (width - label_w - 50) / max_total
    out = []
    for i, label in enumerate(labels):
        y = 5 + i * row_h
        out.append(
            f'<text x="{label_w - 8}" y="{y + row_h * 0.62:.1f}" text-anchor="end" font-size="11" fill="#334155">{escape(label[:24])}</text>'
        )
        x = float(label_w)
        for name, values in series.items():
            w = values[i] * scale
            if w > 0:
                out.append(
                    f'<rect x="{x:.1f}" y="{y + 3:.1f}" width="{w:.1f}" height="{row_h - 8:.1f}" rx="2" fill="{SEVERITY_COLORS.get(name, "#94a3b8")}"/>'
                )
            x += w
        out.append(
            f'<text x="{x + 6:.1f}" y="{y + row_h * 0.62:.1f}" font-size="11" fill="#475569">{totals[i]}</text>'
        )
    h = 10 + len(labels) * row_h
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{h:.0f}" viewBox="0 0 {width} {h:.0f}">{"".join(out)}</svg>'


def trend_lines(
    dates: Sequence[str], series: dict[str, Sequence[int]], width: int = 640, height: int = 200
) -> str:
    if len(dates) < 2:
        return ""
    pad_l, pad_b, pad_t = 40, 24, 10
    max_v = max((max(v) for v in series.values() if v), default=0) or 1
    step = (width - pad_l - 10) / (len(dates) - 1)
    plot_h = height - pad_b - pad_t
    out = []
    for frac in (0, 0.5, 1):
        y = pad_t + plot_h * (1 - frac)
        out.append(f'<line x1="{pad_l}" x2="{width - 10}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e2e8f0"/>')
        out.append(
            f'<text x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="10" fill="#64748b">{round(max_v * frac)}</text>'
        )
    for i in range(0, len(dates), max(1, len(dates) // 6)):
        out.append(
            f'<text x="{pad_l + i * step:.1f}" y="{height - 6}" text-anchor="middle" font-size="10" fill="#64748b">{escape(dates[i])}</text>'
        )
    for name, values in series.items():
        pts = " ".join(
            f"{pad_l + i * step:.1f},{pad_t + plot_h * (1 - v / max_v):.1f}" for i, v in enumerate(values)
        )
        out.append(
            f'<polyline points="{pts}" fill="none" stroke="{SEVERITY_COLORS.get(name, "#94a3b8")}" stroke-width="2"/>'
        )
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">{"".join(out)}</svg>'
