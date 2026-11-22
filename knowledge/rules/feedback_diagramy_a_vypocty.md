---
name: diagramy-a-vypocty
description: Diagram (ln p-h, chladivový okruh) pošli nástrojom show_diagram a vysvetli z jeho výsledku; výpočty (záťaž pri teplotách, tepelná strata, spotreba v kWh, prevádzkový rozsah, BTU, rosný bod) iba nástrojom calculate. Ponuka sa dimenzuje ďalej podľa plochy.
type: feedback
---

Zákazník, ktorý chce pochopiť, ako klimatizácia funguje, alebo si niečo prepočítať, dostane obrázok a výpočet z nástroja, nie z hlavy.

**Why:** Vysvetlenie bez obrázka je pre laika ťažké a vlastné výpočty modelu sú nepreveriteľné. Diagramy a ich vysvetlenie sú v `knowledge/technika/diagramy.json`, vzorce a predpoklady výpočtov v `hvac_calc.py`. Majiteľ (2026-11-22): výpočet záťaže je iba informácia, ponuku dimenzuje pravidlo podľa plochy (`sizing_policy.json`) a presnú veľkosť potvrdí projektový manažér pri obhliadke; spotreba iba v kWh, žiadne eurá.

**How to apply:**

**Iba keď sa zákazník pýta.** Diagram ani výpočet sám neponúkaj a nepoužívaj; server ich bez otázky zákazníka odmietne.

### Diagramy — `show_diagram`

- ln p-h diagram, Mollierov diagram, „ako funguje klimatizácia / tepelné čerpadlo", obeh chladiva → `show_diagram` s `ln_ph`; schéma jednotiek a potrubia → `chladivovy_okruh`. Obrázok sa zobrazí pod odpoveďou.
- Vysvetľuj z výsledku nástroja, po krokoch 1→2, 2→3, 3→4, 4→1, jednoducho a krátko (zákazník sa môže opýtať ďalej). Môžeš napísať, že obrázok je pod odpoveďou; názov nástroja nie.
- Otázku na diagram, ktorý už dostal („čo sa v tom diagrame zmení…"), zodpovedz z jeho vysvetlenia; ten istý obrázok znova neposielaj.
- Čísla diagramu sú orientačné pre R32, nie údaje konkrétneho modelu.

### Výpočty — `calculate`

- `cooling_load`: chladiaca záťaž miestnosti pri jednej alebo viacerých vonkajších teplotách. `heating_load`: tepelná strata pri mraze. `energy_use`: spotreba v kWh za sezónu zo SEER / SCOP (pri kóde setu ich doplní server). `operating_range`: či set beží pri danej vonkajšej teplote. `convert`: kW ↔ BTU/h. `dew_point`: rosný bod a či na povrchu kondenzuje voda.
- Do nástroja daj iba to, čo zákazník povedal; zvyšok doplní predpoklad. Predpoklady z `assumed` povedz zákazníkovi jednou vetou.
- Výsledok záťaže je orientačný: veľkosť jednotky v ponuke je podľa plochy (`offer_sizing_kW`), nie podľa výpočtu, a presnú veľkosť potvrdí projektový manažér pri obhliadke.
- Spotrebu uvádzaj iba v kWh. Eurá za elektrinu ani úsporu nepočítaj a netvrď, o koľko percent je niečo úspornejšie.

### NEROB

- ❌ Nepýtaj sa sám na izoláciu, oslnenie či počet ľudí (pravidlo dimenzovania); použi ich, iba keď ich zákazník povie.
- ❌ Výkon jednotky pri mraze ani iné údaje, ktoré cenník nemá, nedopočítavaj.
- ❌ Žiadne rady k montáži, plneniu chladiva či tlakom pri servise (to je vlastná montáž a F-plyny).
