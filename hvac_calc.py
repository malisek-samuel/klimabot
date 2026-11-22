"""Orientation calculations the bot can run for a customer: cooling and heating load at several outdoor
temperatures, seasonal electricity use from SEER / SCOP, an outdoor-temperature operating range check, kW ↔ BTU/h
and the dew point.

Pure functions, no bot state, no I/O: bot.py's `calculate` tool wraps them (and adds what only the catalog knows —
a set's SEER, SCOP and operating range). Every result says which inputs were assumed, so the bot can tell the
customer. They are orientation figures, not a heat-load design: the offer is still sized by
config/sizing_policy.json (kw_per_m2) and the project manager confirms the size at the site visit (the owner's
decision of 2026-11-22). No euro amounts: consumption is in kWh only, every € in a reply comes from `quote`.

    python hvac_calc.py cooling --m2 25 --outdoor 30 32 35 --sun silne
    python hvac_calc.py heating --m2 25 --outdoor -5 -10 -15 --insulation slaba
    python hvac_calc.py energy --load-kw 2.5 --seer 7.0 --scop 4.6
    python hvac_calc.py convert --value 9000 --unit BTU
    python hvac_calc.py dewpoint --temp 26 --rh 60 --surface 14
"""
import argparse
import json
import math
import re

# --- Assumptions (one place; the results quote them) ---

DEFAULT_HEIGHT_M = 2.6
COOLING_INDOOR_C = 24.0
HEATING_INDOOR_C = 20.0          # EN 12831 living room
COOLING_OUTDOOR_C = (30.0, 32.0, 35.0)
HEATING_OUTDOOR_C = (-5.0, -10.0, -15.0)
# Transmission through walls, windows, roof and floor per m³ of room and K of difference, by insulation level.
# Calibrated so a 25 m² room at -15 °C loses about 0.8 / 1.3 / 2.2 kW (insulated / average / old) together with
# ventilation, the range of residential heat-loss calculations.
TRANSMISSION_W_PER_M3K = {"dobra": 0.30, "priemerna": 0.50, "slaba": 0.90}
INSULATION_LABELS = {"dobra": "zateplené, nové okná", "priemerna": "priemerná izolácia",
                     "slaba": "nezateplené, staré okná"}
AIR_CHANGES_PER_H = 0.5
AIR_HEAT_WH_PER_M3K = 0.34       # ρ·c of air
# Peak solar gain through glazing, W per m² of window, by exposure (internal blinds; no external shading).
SOLAR_W_PER_M2_GLASS = {"tien": 60.0, "bezne": 200.0, "silne": 320.0}
SUN_LABELS = {"tien": "sever alebo tieň", "bezne": "bežné oslnenie", "silne": "juh / západ, veľké okná"}
WINDOW_SHARE_OF_FLOOR = 0.20
TOP_FLOOR_COOLING_W_PER_M2 = 20.0  # a sun-heated roof or attic above the room
TOP_FLOOR_HEATING_FACTOR = 1.2     # more envelope under the roof
PERSON_W = 120.0                   # sensible + latent, light activity
APPLIANCES_W_PER_M2 = 6.0          # lighting and ordinary electronics
# EU 206/2012, Annex: equivalent full-load hours of the seasonal reference (average climate).
COOLING_REFERENCE_HOURS = 350
HEATING_REFERENCE_HOURS = 1400
DEFAULT_LOAD_RATIO = 0.5           # hours of use → equivalent full-load hours: an inverter runs mostly at part load
KW_TO_BTU_H = 3412.142
# Magnus formula (Sonntag 1990 constants), valid about -45…60 °C over water.
MAGNUS_A, MAGNUS_B = 17.62, 243.12

ORIENTATION_NOTE = ("Orientačný výpočet zjednodušenou metódou, nie projekt. Ponuka sa dimenzuje podľa plochy a "
                    "presnú veľkosť potvrdí projektový manažér pri bezplatnej obhliadke.")


class CalcError(ValueError):
    """A bad input; the message is Slovak and goes back to the model as a tool error."""


def _num(value, name, low=None, high=None):
    try:
        x = float(str(value).replace(",", ".")) if value is not None else None
    except ValueError:
        raise CalcError(f"{name}: '{value}' nie je číslo")
    if x is None or math.isnan(x):
        raise CalcError(f"{name}: chýba hodnota")
    if (low is not None and x < low) or (high is not None and x > high):
        raise CalcError(f"{name}: {x:g} je mimo rozsahu {low:g} až {high:g}")
    return x


def _temps(values, default, low, high):
    if values in (None, "", []):
        return list(default), True
    if not isinstance(values, (list, tuple)):
        values = [values]
    temps = sorted({_num(v, "vonkajšia teplota", low, high) for v in values})
    if len(temps) > 8:
        raise CalcError("najviac 8 vonkajších teplôt naraz")
    return temps, False


def _choice(value, options, default, name):
    if value in (None, ""):
        return default, True
    key = str(value).strip().lower()
    if key not in options:
        raise CalcError(f"{name}: '{value}' nepoznám, možnosti: {', '.join(options)}")
    return key, False


def _room(area_m2, height_m):
    area = _num(area_m2, "plocha v m²", 1, 2000)
    height = _num(height_m, "výška stropu", 2, 6) if height_m not in (None, "") else DEFAULT_HEIGHT_M
    return area, height, area * height


def cooling_load(area_m2, outdoor_temps_c=None, indoor_temp_c=None, height_m=None, insulation=None, sun=None,
                 windows_m2=None, people=None, appliances_w=None, top_floor=False):
    """Peak sensible + latent cooling load of one room at each outdoor temperature."""
    area, height, volume = _room(area_m2, height_m)
    temps, temps_assumed = _temps(outdoor_temps_c, COOLING_OUTDOOR_C, 15, 50)
    indoor = _num(indoor_temp_c, "vnútorná teplota", 16, 30) if indoor_temp_c not in (None, "") else COOLING_INDOOR_C
    ins, ins_assumed = _choice(insulation, TRANSMISSION_W_PER_M3K, "priemerna", "izolácia")
    exposure, sun_assumed = _choice(sun, SOLAR_W_PER_M2_GLASS, "bezne", "oslnenie")
    windows = (_num(windows_m2, "plocha okien", 0, 500) if windows_m2 not in (None, "")
               else area * WINDOW_SHARE_OF_FLOOR)
    persons = int(_num(people, "počet ľudí", 0, 200)) if people not in (None, "") else 2
    devices = (_num(appliances_w, "spotrebiče vo W", 0, 100_000) if appliances_w not in (None, "")
               else area * APPLIANCES_W_PER_M2)
    assumed = [label for label, flag in (
        (f"výška stropu {height:g} m", height_m in (None, "")),
        (f"vnútri {indoor:g} °C", indoor_temp_c in (None, "")),
        (f"izolácia: {INSULATION_LABELS[ins]}", ins_assumed),
        (f"oslnenie: {SUN_LABELS[exposure]}", sun_assumed),
        (f"okná {windows:.1f} m² (pätina podlahovej plochy)", windows_m2 in (None, "")),
        (f"{persons} osoby", people in (None, "")),
        (f"svetlá a elektronika {devices:.0f} W", appliances_w in (None, "")),
        (f"vonkajšie teploty {', '.join(f'{t:g}' for t in temps)} °C", temps_assumed),
    ) if flag]
    solar = windows * SOLAR_W_PER_M2_GLASS[exposure] + (area * TOP_FLOOR_COOLING_W_PER_M2 if top_floor else 0)
    internal = persons * PERSON_W + devices
    rows = []
    for t in temps:
        dt = t - indoor
        transmission = volume * TRANSMISSION_W_PER_M3K[ins] * dt
        ventilation = volume * AIR_CHANGES_PER_H * AIR_HEAT_WH_PER_M3K * dt
        total = max(0.0, transmission + ventilation + solar + internal)
        rows.append({"outdoor_temp_C": t, "load_kW": round(total / 1000, 2), "W_per_m2": round(total / area),
                     "parts_W": {"steny_a_okna": round(transmission), "vetranie": round(ventilation),
                                 "slnko": round(solar), "ludia_a_spotrebice": round(internal)}})
    return {
        "kind": "cooling_load", "area_m2": area, "indoor_temp_C": indoor, "by_outdoor_temp": rows,
        "assumed": assumed,
        "explanation": ("Vonkajšia teplota mení najmä prestup tepla cez steny a okná a vetranie; väčšiu časť "
                        "záťaže tvorí slnko cez okná a teplo od ľudí a spotrebičov."),
        "note": ORIENTATION_NOTE,
    }


def heating_load(area_m2, outdoor_temps_c=None, indoor_temp_c=None, height_m=None, insulation=None, top_floor=False):
    """Heat loss of one room (transmission + ventilation) at each outdoor temperature."""
    area, height, volume = _room(area_m2, height_m)
    temps, temps_assumed = _temps(outdoor_temps_c, HEATING_OUTDOOR_C, -30, 15)
    indoor = _num(indoor_temp_c, "vnútorná teplota", 15, 26) if indoor_temp_c not in (None, "") else HEATING_INDOOR_C
    ins, ins_assumed = _choice(insulation, TRANSMISSION_W_PER_M3K, "priemerna", "izolácia")
    factor = TOP_FLOOR_HEATING_FACTOR if top_floor else 1.0
    assumed = [label for label, flag in (
        (f"výška stropu {height:g} m", height_m in (None, "")),
        (f"vnútri {indoor:g} °C", indoor_temp_c in (None, "")),
        (f"izolácia: {INSULATION_LABELS[ins]}", ins_assumed),
        (f"vonkajšie teploty {', '.join(f'{t:g}' for t in temps)} °C", temps_assumed),
    ) if flag]
    rows = []
    for t in temps:
        dt = indoor - t
        transmission = volume * TRANSMISSION_W_PER_M3K[ins] * factor * dt
        ventilation = volume * AIR_CHANGES_PER_H * AIR_HEAT_WH_PER_M3K * dt
        total = max(0.0, transmission + ventilation)
        rows.append({"outdoor_temp_C": t, "load_kW": round(total / 1000, 2), "W_per_m2": round(total / area),
                     "parts_W": {"steny_a_okna": round(transmission), "vetranie": round(ventilation)}})
    return {
        "kind": "heating_load", "area_m2": area, "indoor_temp_C": indoor, "by_outdoor_temp": rows,
        "assumed": assumed,
        "explanation": ("Tepelná strata rastie s rozdielom teplôt vnútri a vonku: pri dvojnásobnom rozdiele je "
                        "zhruba dvojnásobná. Výpočtová vonkajšia teplota je na Slovensku podľa lokality približne "
                        "od −11 do −18 °C."),
        "note": ORIENTATION_NOTE + " Výkon jednotky pri nízkych vonkajších teplotách cenníky neuvádzajú.",
    }


def energy_use(cooling_load_kw=None, heating_load_kw=None, seer=None, scop=None, cooling_hours=None,
               heating_hours=None, hours_per_day=None, cooling_days=None, heating_days=None, load_ratio=None):
    """Seasonal electricity in kWh: load × equivalent full-load hours / SEER (cooling) or / SCOP (heating).
    Without hours, the EU 206/2012 reference season (350 h cooling, 1400 h heating, average climate)."""
    if cooling_load_kw in (None, "") and heating_load_kw in (None, ""):
        raise CalcError("chýba výkon alebo záťaž v kW (chladenie alebo kúrenie)")
    ratio = _num(load_ratio, "podiel záťaže", 0.1, 1) if load_ratio not in (None, "") else DEFAULT_LOAD_RATIO
    per_day = _num(hours_per_day, "hodiny denne", 0.5, 24) if hours_per_day not in (None, "") else None
    out = {"kind": "energy_use", "assumed": [], "note": (
        "Spotreba elektriny v kWh, orientačne; skutočná závisí od počasia, nastavenej teploty a domu. "
        "V eurách ju neuvádzame.")}

    def season(mode, load, efficiency, eff_name, hours, days, ref_hours):
        p = _num(load, f"výkon pre {mode} v kW", 0.1, 100)
        if efficiency in (None, ""):
            raise CalcError(f"pre {mode} chýba {eff_name}")
        e = _num(efficiency, eff_name, 1, 15)
        if hours not in (None, ""):
            h = _num(hours, f"hodiny plného výkonu ({mode})", 1, 8760)
            how = f"{h:g} h plného výkonu"
        elif per_day is not None and days not in (None, ""):
            d = _num(days, f"dni ({mode})", 1, 366)
            h = per_day * d * ratio
            how = f"{per_day:g} h denne × {d:g} dní × podiel záťaže {ratio:g}"
            if load_ratio in (None, ""):
                out["assumed"].append(f"invertor beží v priemere na {ratio:.0%} výkonu")
        else:
            h = ref_hours
            how = f"referenčná sezóna EÚ {ref_hours} h plného výkonu (nariadenie 206/2012, priemerná klíma)"
            out["assumed"].append(f"{mode}: {how}")
        thermal = p * h
        return {"load_kW": p, eff_name: e, "full_load_hours": round(h), "hours_basis": how,
                "heat_moved_kWh": round(thermal), "electricity_kWh": round(thermal / e)}

    if cooling_load_kw not in (None, ""):
        out["cooling"] = season("chladenie", cooling_load_kw, seer, "SEER", cooling_hours, cooling_days,
                                COOLING_REFERENCE_HOURS)
    if heating_load_kw not in (None, ""):
        out["heating"] = season("kúrenie", heating_load_kw, scop, "SCOP", heating_hours, heating_days,
                                HEATING_REFERENCE_HOURS)
    out["explanation"] = ("SEER a SCOP hovoria, koľko kWh tepla jednotka prenesie za sezónu na 1 kWh elektriny; "
                          "spotreba = prenesené teplo / SEER (chladenie) alebo / SCOP (kúrenie).")
    return out


_RANGE_RE = re.compile(r"([+\-−]?\s*\d+(?:[.,]\d+)?)\s*/\s*([+\-−]?\s*\d+(?:[.,]\d+)?)")


def parse_range(text):
    """'-15/+46' → (-15.0, 46.0); None when the text holds no such pair."""
    m = _RANGE_RE.search(str(text))
    if not m:
        return None
    lo, hi = (float(x.replace("−", "-").replace(" ", "").replace(",", ".")) for x in m.groups())
    return (min(lo, hi), max(lo, hi))


def operating_range(outdoor_temp_c, low_c, high_c, mode):
    """Whether a unit runs at the outdoor temperature, from its price-list operating range."""
    t = _num(outdoor_temp_c, "vonkajšia teplota", -50, 60)
    mode_sk = "chladenie" if mode == "cooling" else "kúrenie"
    ok = low_c <= t <= high_c
    return {"kind": "operating_range", "mode": mode_sk, "outdoor_temp_C": t, "range_C": [low_c, high_c],
            "within_range": ok,
            "note": ("Rozsah vonkajších teplôt z cenníka výrobcu. Mimo neho jednotka v tomto režime nebeží "
                     "alebo sa chráni; výkon pri hraničných teplotách cenník neuvádza.")}


def convert(value, unit):
    """kW ↔ BTU/h (the 'BTU' of an AC is BTU per hour: a 9000 BTU unit is about 2.6 kW)."""
    v = _num(value, "hodnota", 0.01, 1_000_000)
    u = str(unit or "").strip().lower().replace(" ", "").replace("/h", "")
    if u in ("btu", "btuh"):
        return {"kind": "convert", "BTU_h": v, "kW": round(v / KW_TO_BTU_H, 2),
                "note": "1 kW = 3 412 BTU/h; výrobcovia triedy zaokrúhľujú (9000 BTU ≈ 2,6 kW)."}
    if u == "kw":
        return {"kind": "convert", "kW": v, "BTU_h": round(v * KW_TO_BTU_H),
                "note": "1 kW = 3 412 BTU/h."}
    raise CalcError(f"jednotka: '{unit}' nepoznám, možnosti: kW, BTU")


def dew_point(temp_c, rh_pct, surface_temp_c=None):
    """Dew point (Magnus) and, with a surface temperature, whether water condenses on it."""
    t = _num(temp_c, "teplota vzduchu", -40, 60)
    rh = _num(rh_pct, "relatívna vlhkosť v %", 1, 100)
    g = math.log(rh / 100) + MAGNUS_A * t / (MAGNUS_B + t)
    td = MAGNUS_B * g / (MAGNUS_A - g)
    out = {"kind": "dew_point", "air_temp_C": t, "relative_humidity_pct": rh, "dew_point_C": round(td, 1),
           "explanation": ("Rosný bod je teplota, pod ktorou sa z vlhkého vzduchu začne vylučovať voda. Výparník "
                           "vnútornej jednotky je pri chladení studenší, preto vzduch odvlhčuje a kondenzát "
                           "odteká hadičkou.")}
    if surface_temp_c not in (None, ""):
        s = _num(surface_temp_c, "teplota povrchu", -40, 60)
        out.update(surface_temp_C=s, condensation=s <= td)
    return out


def _main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("cooling", "heating"):
        s = sub.add_parser(name)
        s.add_argument("--m2", type=float, required=True)
        s.add_argument("--outdoor", type=float, nargs="*")
        s.add_argument("--indoor", type=float)
        s.add_argument("--height", type=float)
        s.add_argument("--insulation", choices=sorted(TRANSMISSION_W_PER_M3K))
        s.add_argument("--top-floor", action="store_true")
        if name == "cooling":
            s.add_argument("--sun", choices=sorted(SOLAR_W_PER_M2_GLASS))
            s.add_argument("--windows", type=float)
            s.add_argument("--people", type=int)
            s.add_argument("--appliances", type=float)
    s = sub.add_parser("energy")
    s.add_argument("--load-kw", type=float, help="cooling load or capacity in kW")
    s.add_argument("--heat-kw", type=float, help="heating load in kW")
    s.add_argument("--seer", type=float)
    s.add_argument("--scop", type=float)
    s.add_argument("--hours-per-day", type=float)
    s.add_argument("--cooling-days", type=float)
    s.add_argument("--heating-days", type=float)
    s = sub.add_parser("convert")
    s.add_argument("--value", type=float, required=True)
    s.add_argument("--unit", required=True, choices=["kW", "BTU"])
    s = sub.add_parser("dewpoint")
    s.add_argument("--temp", type=float, required=True)
    s.add_argument("--rh", type=float, required=True)
    s.add_argument("--surface", type=float)
    a = p.parse_args(argv)
    if a.cmd == "cooling":
        r = cooling_load(a.m2, a.outdoor, a.indoor, a.height, a.insulation, a.sun, a.windows, a.people, a.appliances,
                         a.top_floor)
    elif a.cmd == "heating":
        r = heating_load(a.m2, a.outdoor, a.indoor, a.height, a.insulation, a.top_floor)
    elif a.cmd == "energy":
        r = energy_use(a.load_kw, a.heat_kw, a.seer, a.scop, hours_per_day=a.hours_per_day,
                       cooling_days=a.cooling_days, heating_days=a.heating_days)
    elif a.cmd == "convert":
        r = convert(a.value, a.unit)
    else:
        r = dew_point(a.temp, a.rh, a.surface)
    print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
