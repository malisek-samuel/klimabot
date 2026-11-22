"""Draws web/static/diagrams/ln_ph_r32.svg: the ln p-h diagram of R32 with a typical cooling cycle.

The property data comes from CoolProp, which the bot doesn't need, so it isn't a project dependency:

    python -m venv /tmp/cp && /tmp/cp/bin/pip install CoolProp
    /tmp/cp/bin/python docs/diagrams/make_ln_ph_diagram.py

The cycle's figures are the ones knowledge/technika/diagramy.json explains (keep them in step): evaporating at
5 °C, condensing at 45 °C, 5 K superheat, 5 K subcooling, isentropic compressor efficiency 0.7.
"""
import math
from pathlib import Path

import CoolProp.CoolProp as CP

FLUID = "R32"
T_EVAP, T_COND, SUPERHEAT, SUBCOOL, ETA_IS = 5.0, 45.0, 5.0, 5.0, 0.7
OUT = Path(__file__).resolve().parents[2] / "web" / "static" / "diagrams" / "ln_ph_r32.svg"

W, H = 1000, 760
X0, X1, Y0, Y1 = 96, 960, 78, 478          # plot area
H_MIN, H_MAX = 150, 650                    # kJ/kg
P_MIN, P_MAX = 3, 80                       # bar


def K(c):
    return c + 273.15


def prop(out, a, av, b, bv):
    return CP.PropsSI(out, a, av, b, bv, FLUID)


def x(h):
    return X0 + (h - H_MIN) / (H_MAX - H_MIN) * (X1 - X0)


def y(p):
    return Y1 - (math.log(p) - math.log(P_MIN)) / (math.log(P_MAX) - math.log(P_MIN)) * (Y1 - Y0)


def pt(h, p):
    return f"{x(h):.1f},{y(p):.1f}"


def cycle():
    p0 = prop("P", "T", K(T_EVAP), "Q", 1) / 1e5
    pc = prop("P", "T", K(T_COND), "Q", 0) / 1e5
    h1 = prop("H", "T", K(T_EVAP + SUPERHEAT), "P", p0 * 1e5) / 1e3
    s1 = prop("S", "T", K(T_EVAP + SUPERHEAT), "P", p0 * 1e5)
    h2s = prop("H", "P", pc * 1e5, "S", s1) / 1e3
    h2 = h1 + (h2s - h1) / ETA_IS
    t2 = prop("T", "P", pc * 1e5, "H", h2 * 1e3) - 273.15
    h_gsat_c = prop("H", "P", pc * 1e5, "Q", 1) / 1e3
    h_lsat_c = prop("H", "P", pc * 1e5, "Q", 0) / 1e3
    h3 = prop("H", "T", K(T_COND - SUBCOOL), "P", pc * 1e5) / 1e3
    h4 = h3
    h_gsat_0 = prop("H", "P", p0 * 1e5, "Q", 1) / 1e3
    return dict(p0=p0, pc=pc, h1=h1, h2=h2, h2s=h2s, t2=t2, h3=h3, h4=h4, h_gsat_c=h_gsat_c, h_lsat_c=h_lsat_c,
                h_gsat_0=h_gsat_0, s1=s1)


def dome():
    tc = CP.PropsSI("Tcrit", FLUID) - 273.15
    temps = [-40 + i * 0.5 for i in range(int((tc - 0.3 + 40) / 0.5))]
    liquid = [(prop("H", "T", K(t), "Q", 0) / 1e3, prop("P", "T", K(t), "Q", 0) / 1e5) for t in temps]
    vapour = [(prop("H", "T", K(t), "Q", 1) / 1e3, prop("P", "T", K(t), "Q", 1) / 1e5) for t in temps]
    pcrit = CP.PropsSI("Pcrit", FLUID) / 1e5
    hc = CP.PropsSI("H", "T", CP.PropsSI("Tcrit", FLUID), "Dmass", CP.PropsSI("rhocrit", FLUID), FLUID) / 1e3
    return liquid, vapour, (hc, pcrit), tc


def isentrope(s, p_from, p_to, n=30):
    out = []
    for i in range(n + 1):
        p = p_from * (p_to / p_from) ** (i / n)
        out.append((prop("H", "P", p * 1e5, "S", s) / 1e3, p))
    return out


def isotherm(t):
    """An isotherm: liquid part (nearly vertical), across the dome, then the vapour part."""
    psat = prop("P", "T", K(t), "Q", 0) / 1e5
    pts = []
    for i in range(16):
        p = P_MAX * (psat / P_MAX) ** (i / 15)
        if p <= psat * 1.001:
            break
        pts.append((prop("H", "T", K(t), "P", p * 1e5) / 1e3, p))
    pts += [(prop("H", "T", K(t), "Q", 0) / 1e3, psat), (prop("H", "T", K(t), "Q", 1) / 1e3, psat)]
    for i in range(1, 21):
        p = psat * (P_MIN / psat) ** (i / 20)
        pts.append((prop("H", "T", K(t), "P", p * 1e5) / 1e3, p))
    return [(h, p) for h, p in pts if H_MIN <= h <= H_MAX]


def label_along(curve, p_at, side, text, gap=9):
    """Text along a saturation line at pressure p_at, `gap` px off it (side +1: to the right of the line)."""
    pts = [(x(h), y(p)) for h, p in curve]
    i = min(range(1, len(curve)), key=lambda k: abs(curve[k][1] - p_at))
    (xa, ya), (xb, yb) = pts[i - 1], pts[min(i + 1, len(pts) - 1)]
    ang = math.degrees(math.atan2(yb - ya, xb - xa))
    if ang > 90 or ang < -90:
        ang -= 180 if ang > 0 else -180
    nx, ny = -math.sin(math.radians(ang)), math.cos(math.radians(ang))  # unit normal (screen coords)
    if nx * side < 0:
        nx, ny = -nx, -ny
    cx, cy = pts[i][0] + nx * gap, pts[i][1] + ny * gap
    return (f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="11.5" fill="#1e3a8a" text-anchor="middle" '
            f'dominant-baseline="middle" transform="rotate({ang:.1f} {cx:.1f} {cy:.1f})">{text}</text>')


def polyline(points):
    return " ".join(pt(h, p) for h, p in points)


def num(v, d=0):
    return f"{v:.{d}f}".replace(".", ",")


def main():
    c = cycle()
    liquid, vapour, (hc, pcrit), tc = dome()
    s = []
    a = s.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
      f'aria-labelledby="t d" font-family="Inter, \'Segoe UI\', system-ui, sans-serif">')
    a('<title id="t">ln p-h diagram chladiva R32: chladiaci cyklus klimatizácie</title>')
    a(f'<desc id="d">Logaritmický tlak na zvislej osi, merná entalpia na vodorovnej. Medza sýtosti tvorí kopulu s '
      f'kritickým bodom navrchu. Cyklus: 1→2 kompresia v kompresore z {num(c["p0"], 1)} na {num(c["pc"], 1)} bar, '
      f'2→3 kondenzácia pri {num(T_COND)} °C, 3→4 škrtenie v expanznom ventile, 4→1 vyparovanie pri '
      f'{num(T_EVAP)} °C vo výparníku.</desc>')
    a(f'''<defs>
  <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerUnits="userSpaceOnUse" markerWidth="13" markerHeight="13" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker>
  <marker id="arrS" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker>
  <clipPath id="plot"><rect x="{X0}" y="{Y0}" width="{X1 - X0}" height="{Y1 - Y0}"/></clipPath>
  <linearGradient id="wet" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#dbeafe"/><stop offset="1" stop-color="#e0f2fe"/></linearGradient>
</defs>''')
    a(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    a(f'<text x="{X0}" y="40" font-size="22" font-weight="700" fill="#0f172a">ln p-h diagram chladiva R32 — chladiaci cyklus</text>')
    a(f'<text x="{X0}" y="62" font-size="13.5" fill="#475569">Orientačne: vyparovanie {num(T_EVAP)} °C, kondenzácia '
      f'{num(T_COND)} °C, prehriatie {num(SUPERHEAT)} K, podchladenie {num(SUBCOOL)} K. Údaje R32 z CoolProp.</text>')

    # grid and axes
    a('<g stroke="#e2e8f0" stroke-width="1">')
    for h in range(200, H_MAX + 1, 50):
        a(f'<line x1="{x(h):.1f}" y1="{Y0}" x2="{x(h):.1f}" y2="{Y1}"/>')
    p_ticks = [3, 4, 5, 6, 8, 10, 15, 20, 30, 40, 50, 60, 80]
    for p in p_ticks:
        a(f'<line x1="{X0}" y1="{y(p):.1f}" x2="{X1}" y2="{y(p):.1f}"/>')
    a('</g>')
    a(f'<rect x="{X0}" y="{Y0}" width="{X1 - X0}" height="{Y1 - Y0}" fill="none" stroke="#94a3b8"/>')
    a('<g font-size="12.5" fill="#475569">')
    for h in range(200, H_MAX + 1, 100):
        a(f'<text x="{x(h):.1f}" y="{Y1 + 18}" text-anchor="middle">{h}</text>')
    for p in [3, 5, 10, 20, 30, 50, 80]:
        a(f'<text x="{X0 - 8}" y="{y(p) + 4:.1f}" text-anchor="end">{p}</text>')
    a('</g>')
    a(f'<text x="{(X0 + X1) / 2:.0f}" y="{Y1 + 40}" text-anchor="middle" font-size="13.5" fill="#334155" '
      f'font-weight="600">merná entalpia h [kJ/kg] →</text>')
    a(f'<text transform="translate(30 {(Y0 + Y1) / 2:.0f}) rotate(-90)" text-anchor="middle" font-size="13.5" '
      f'fill="#334155" font-weight="600">tlak p [bar], logaritmická mierka →</text>')

    # wet region and saturation lines
    a('<g clip-path="url(#plot)">')
    a(f'<polygon points="{polyline(liquid)} {pt(hc, pcrit)} {polyline(reversed(vapour))}" fill="url(#wet)" opacity="0.8"/>')
    a(f'<polyline points="{polyline(liquid)} {pt(hc, pcrit)}" fill="none" stroke="#1e3a8a" stroke-width="2.2"/>')
    a(f'<polyline points="{pt(hc, pcrit)} {polyline(reversed(vapour))}" fill="none" stroke="#1e3a8a" stroke-width="2.2"/>')
    a(f'<circle cx="{x(hc):.1f}" cy="{y(pcrit):.1f}" r="4.5" fill="#1e3a8a"/>')
    a(f'<text x="{x(hc) + 9:.1f}" y="{y(pcrit) - 6:.1f}" font-size="12.5" fill="#1e3a8a">kritický bod '
      f'({num(tc, 0)} °C, {num(pcrit, 0)} bar)</text>')

    # isotherms of the cycle and the isentrope through 1
    for t, colour in ((T_EVAP, "#0284c7"), (T_COND, "#dc2626")):
        a(f'<polyline points="{polyline(isotherm(t))}" fill="none" stroke="{colour}" stroke-width="1" '
          f'stroke-dasharray="3 4" opacity="0.7"/>')
    iso_c = isotherm(T_COND)
    h_lab = max(h for h, _ in iso_c)
    a(f'<text x="{x(h_lab) - 4:.1f}" y="{y(P_MIN) - 6:.1f}" font-size="11.5" fill="#dc2626" text-anchor="end">'
      f'izoterma {num(T_COND)} °C</text>')
    a(f'<polyline points="{polyline(isentrope(c["s1"], c["p0"], c["pc"] * 1.6))}" fill="none" stroke="#64748b" '
      f'stroke-width="1.2" stroke-dasharray="1.5 4"/>')
    lab = isentrope(c["s1"], c["p0"], c["pc"] * 1.6)[-1]
    a(f'<text x="{x(lab[0]) - 6:.1f}" y="{y(lab[1]) + 4:.1f}" font-size="11.5" fill="#64748b" text-anchor="end">'
      f'izoentropa (ideálna kompresia)</text>')

    a('</g>')
    # region labels
    a('<g font-size="13" fill="#334155" font-style="italic">')
    a(f'<text x="{x(205):.1f}" y="{y(55):.1f}" text-anchor="middle">kvapalina</text>')
    a(f'<text x="{x(205):.1f}" y="{y(48):.1f}" text-anchor="middle">(podchladená)</text>')
    a(f'<text x="{x(390):.1f}" y="{y(4.2):.1f}" text-anchor="middle">mokrá para (kvapalina + para)</text>')
    a(f'<text x="{x(610):.1f}" y="{y(6):.1f}" text-anchor="middle">prehriata</text>')
    a(f'<text x="{x(610):.1f}" y="{y(5.2):.1f}" text-anchor="middle">para</text>')
    a('</g>')
    for curve, p_at, side, text in ((liquid, 4.1, 1, "sýta kvapalina (x = 0)"), (vapour, 5.0, -1, "sýta para (x = 1)")):
        a(label_along(curve, p_at, side, text))

    # the cycle
    p0, pc = c["p0"], c["pc"]
    comp = isentrope(c["s1"], p0, pc)  # ideal path, then stretched to the real end point
    real = [(c["h1"] + (h - c["h1"]) * (c["h2"] - c["h1"]) / (c["h2s"] - c["h1"]), p) for h, p in comp]
    seg = [
        ("#ea580c", polyline(real)),                                                       # 1→2
        ("#dc2626", f'{pt(c["h2"], pc)} {pt(c["h3"], pc)}'),                               # 2→3
        ("#7c3aed", f'{pt(c["h3"], pc)} {pt(c["h4"], p0)}'),                               # 3→4
        ("#0284c7", f'{pt(c["h4"], p0)} {pt(c["h1"], p0)}'),                               # 4→1
    ]
    for colour, points in seg:
        a(f'<polyline points="{points}" fill="none" stroke="{colour}" stroke-width="4" stroke-linejoin="round" '
          f'stroke-linecap="round"/>')
    # direction arrows in the middle of each process
    mids = [
        ("#ea580c", real[len(real) // 2 - 2], real[len(real) // 2 + 2]),
        ("#dc2626", (c["h2"] - 0.45 * (c["h2"] - c["h3"]), pc), (c["h2"] - 0.55 * (c["h2"] - c["h3"]), pc)),
        ("#7c3aed", (c["h3"], pc * (p0 / pc) ** 0.45), (c["h3"], pc * (p0 / pc) ** 0.55)),
        ("#0284c7", (c["h4"] + 0.45 * (c["h1"] - c["h4"]), p0), (c["h4"] + 0.55 * (c["h1"] - c["h4"]), p0)),
    ]
    for colour, (ha, pa), (hb, pb) in mids:
        a(f'<line x1="{x(ha):.1f}" y1="{y(pa):.1f}" x2="{x(hb):.1f}" y2="{y(pb):.1f}" stroke="{colour}" '
          f'stroke-width="4" marker-end="url(#arr)"/>')
    for label, h, p, dx, dy in (("1", c["h1"], p0, 0, 26), ("2", c["h2"], pc, 0, -14),
                                ("3", c["h3"], pc, 0, -14), ("4", c["h4"], p0, 0, 26)):
        a(f'<circle cx="{x(h):.1f}" cy="{y(p):.1f}" r="5" fill="#0f172a"/>')
        a(f'<circle cx="{x(h) + dx:.1f}" cy="{y(p) + dy - 5:.1f}" r="11" fill="#0f172a"/>')
        a(f'<text x="{x(h) + dx:.1f}" y="{y(p) + dy:.1f}" text-anchor="middle" font-size="13" font-weight="700" '
          f'fill="#ffffff">{label}</text>')
    # pressure labels of the two levels
    a(f'<text x="{x(c["h3"]) - 34:.1f}" y="{y(pc) + 4:.1f}" text-anchor="end" font-size="12" fill="#dc2626">'
      f'vysoký tlak {num(pc, 1)} bar</text>')
    a(f'<text x="{x(c["h4"]) - 34:.1f}" y="{y(p0) + 4:.1f}" text-anchor="end" font-size="12" fill="#0284c7">'
      f'nízky tlak {num(p0, 1)} bar</text>')
    a(f'<text x="{x(c["h2"]) + 12:.1f}" y="{y(pc) + 4:.1f}" font-size="12" fill="#ea580c">výtlak {num(c["t2"])} °C</text>')

    # enthalpy differences under the plot: q0, w, qk
    def bracket(h_a, h_b, yy, colour, text, side="middle"):
        a(f'<line x1="{x(h_a):.1f}" y1="{yy}" x2="{x(h_b):.1f}" y2="{yy}" stroke="{colour}" stroke-width="2" '
          f'marker-start="url(#arrS)" marker-end="url(#arrS)"/>')
        tx, ty = ((x(h_a) + x(h_b)) / 2, yy - 7) if side == "middle" else (x(h_a) - 8, yy + 4.5)
        a(f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{"middle" if side == "middle" else "end"}" '
          f'font-size="12.5" font-weight="600" fill="{colour}">{text}</text>')
    yb = Y1 + 76
    bracket(c["h4"], c["h1"], yb, "#0284c7", f'q₀ = h₁ − h₄ ≈ {num(c["h1"] - c["h4"])} kJ/kg (teplo z miestnosti)')
    bracket(c["h1"], c["h2"], yb + 34, "#ea580c", f'w = h₂ − h₁ ≈ {num(c["h2"] - c["h1"])} kJ/kg (práca kompresora)', side="left")
    bracket(c["h3"], c["h2"], yb + 72, "#dc2626", f'q_k = h₂ − h₃ ≈ {num(c["h2"] - c["h3"])} kJ/kg (teplo von)')
    for h in (c["h4"], c["h1"], c["h2"], c["h3"]):
        a(f'<line x1="{x(h):.1f}" y1="{Y1}" x2="{x(h):.1f}" y2="{yb + 72}" stroke="#cbd5e1" stroke-dasharray="2 3"/>')

    # legend
    lx, ly = X0, H - 92
    items = [("#ea580c", "1→2 kompresia (kompresor)"), ("#dc2626", "2→3 kondenzácia (kondenzátor)"),
             ("#7c3aed", "3→4 škrtenie (expanzný ventil)"), ("#0284c7", "4→1 vyparovanie (výparník)")]
    for i, (colour, text) in enumerate(items):
        xx, yy = lx + (i % 2) * 400, ly + (i // 2) * 24
        a(f'<line x1="{xx}" y1="{yy}" x2="{xx + 24}" y2="{yy}" stroke="{colour}" stroke-width="5" stroke-linecap="round"/>')
        a(f'<text x="{xx + 32}" y="{yy + 4.5}" font-size="13" fill="#0f172a">{text}</text>')
    a(f'<text x="{lx}" y="{H - 30}" font-size="12.5" fill="#475569">Pri chladení je výparník vo vnútornej jednotke '
      f'a kondenzátor vo vonkajšej; pri kúrení ich štvorcestný ventil vymení.</text>')
    a(f'<text x="{lx}" y="{H - 11}" font-size="12.5" fill="#475569">Chladiaci faktor v tomto bode ≈ q₀ / w = '
      f'{num((c["h1"] - c["h4"]) / (c["h2"] - c["h1"]), 1)} (okamžitá hodnota, nie sezónny SEER).</text>')
    a('</svg>')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(s) + "\n", encoding="utf-8")
    print(OUT, {k: round(v, 2) for k, v in c.items()})


if __name__ == "__main__":
    main()
