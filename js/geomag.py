"""Genera data/geomag.json desde el IGRF. Nada se calcula en el navegador."""
import json, datetime, numpy as np, ppigrf
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

EPOCA = datetime.datetime(2026, 1, 1)
R = 1  # redondeo de coordenadas (decimales)

lats = np.arange(-89.5, 90.0, 1.0)
lons = np.arange(-180.0, 180.5, 1.0)
LON, LAT = np.meshgrid(lons, lats)
Be, Bn, Bu = ppigrf.igrf(LON.ravel(), LAT.ravel(), np.zeros(LON.size), EPOCA)
Be, Bn, Bu = [a.reshape(LAT.shape) for a in (Be, Bn, Bu)]
H = np.hypot(Be, Bn)
F = np.sqrt(Be**2 + Bn**2 + Bu**2)
INC = np.degrees(np.arctan2(-Bu, H))      # Z = -Bu (hacia abajo); I=0 => ecuador magnético
DEC = np.degrees(np.arctan2(Be, Bn))

def partir(linea):
    """Corta una polilínea donde cruza el antimeridiano."""
    out, cur = [], [linea[0]]
    for a, b in zip(linea, linea[1:]):
        if abs(b[0] - a[0]) > 180:
            out.append(cur); cur = [b]
        else:
            cur.append(b)
    out.append(cur)
    return [l for l in out if len(l) > 1]

def contornos(Z, niveles, campo_cerrado=False):
    """Extrae contornos como listas de [lon,lat], partidas en el antimeridiano."""
    fig, ax = plt.subplots()
    cs = ax.contour(LON, LAT, Z, levels=niveles)
    res = []
    for lvl, segs in zip(cs.levels, [cs.allsegs[i] for i in range(len(cs.levels))]):
        lineas = []
        for s in segs:
            if len(s) < 3: continue
            pts = [[round(float(x), R), round(float(y), R)] for x, y in s]
            lineas.extend(partir(pts))
        if lineas:
            res.append({"v": float(lvl), "lineas": lineas})
    plt.close(fig)
    return res

# ── latitud geomagnética (dipolo centrado) para la franja auroral ──
# polo geomagnético norte a partir de la inclinación: usamos el dipolo del IGRF
# vía el punto de inclinación máxima, y de ahí la colatitud geomagnética.
def polo_dip(hemis):
    """Polo de inclinación (dip pole): donde H es mínima en cada hemisferio."""
    m = LAT > 0 if hemis == "N" else LAT < 0
    Hm = np.where(m, H, np.inf)
    i, j = np.unravel_index(np.argmin(Hm), Hm.shape)
    # refinamiento local con malla fina
    la0, lo0 = LAT[i, j], LON[i, j]
    fla = np.arange(la0 - 1.5, la0 + 1.55, 0.1)
    flo = np.arange(lo0 - 4.0, lo0 + 4.05, 0.25)
    FLO, FLA = np.meshgrid(flo, fla)
    e, n, u = ppigrf.igrf(FLO.ravel(), FLA.ravel(), np.zeros(FLO.size), EPOCA)
    h = np.hypot(e, n).reshape(FLA.shape)
    a, b = np.unravel_index(np.argmin(h), h.shape)
    return [round(float(FLO[a, b]), 2), round(float(FLA[a, b]), 2)]

def deriva(hemis, años):
    out = []
    for y in años:
        d = datetime.datetime(y, 1, 1)
        m = LAT > 0 if hemis == "N" else LAT < 0
        e, n, u = ppigrf.igrf(LON.ravel(), LAT.ravel(), np.zeros(LON.size), d)
        h = np.hypot(e, n).reshape(LAT.shape)
        hm = np.where(m, h, np.inf)
        i, j = np.unravel_index(np.argmin(hm), hm.shape)
        out.append([y, round(float(LON[i, j]), 1), round(float(LAT[i, j]), 1)])
    return out

# latitud geomagnética aproximada desde el polo geomagnético (dipolo)
pn = polo_dip("N")
plon, plat = np.radians(pn[0]), np.radians(pn[1])
la_r, lo_r = np.radians(LAT), np.radians(LON)
cos_c = (np.sin(plat)*np.sin(la_r) + np.cos(plat)*np.cos(la_r)*np.cos(lo_r - plon))
MLAT = 90 - np.degrees(np.arccos(np.clip(cos_c, -1, 1)))

datos = {
  "meta": {
    "modelo": "IGRF-14 (14.ª generación del International Geomagnetic Reference Field)",
    "vigencia": "1900.0 – 2030.0",
    "epoca": "2026.0",
    "altitud": "nivel del mar",
    "calculo": "Calculado con ppigrf sobre una malla de 1° y contorneado con matplotlib. Nada se calcula en el navegador.",
    "fuente": "https://www.ncei.noaa.gov/products/international-geomagnetic-reference-field",
    "aas": "La Anomalía del Atlántico Sur se delimita por el contorno de 32.000 nT a nivel del mar (Pavón-Carrasco y De Santis, 2016). Es la región donde el campo es más débil respecto de un dipolo ideal centrado en la Tierra, no el punto más débil del planeta sin más.",
    "auroral": "Franja de latitud geomagnética 65°–70° calculada desde el polo de inclinación. Es aproximada y vale para condiciones tranquilas: durante tormentas el óvalo baja de latitud.",
    "polos": "Polos de inclinación, donde el campo apunta vertical. Posición aproximada: cerca del polo la longitud queda mal determinada.",
    "aviso": "Geofísica de contexto. El campo magnético no explica ni causa avistamientos. La franja auroral sí sirve de descarte: las auroras se confunden con luces anómalas."
  },
  "intensidad": contornos(F, [26000, 30000, 34000, 38000, 42000, 46000, 50000, 54000, 58000, 62000]),
  "aas":        contornos(F, [32000]),
  "declinacion":contornos(DEC, [-60,-40,-20, 0, 20, 40, 60]),
  "ecuador":    contornos(INC, [0]),
  "auroral":    contornos(MLAT, [-70, -65, 65, 70]),
  "polos": {
    "n": polo_dip("N"), "s": polo_dip("S"),
    "derivaN": deriva("N", list(range(1900, 2026, 10)) + [2026]),
    "derivaS": deriva("S", list(range(1900, 2026, 10)) + [2026]),
  },
}

p = "/tmp/claude-0/-home-claude/56e18584-83bb-5e93-96f6-a11bd7078f24/scratchpad/nereo-repo/data/geomag.json"
with open(p, "w", encoding="utf-8") as f:
    json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
    f.write("\n")

import os
print("escrito:", round(os.path.getsize(p)/1024), "KB")
print("polo norte magnético:", datos["polos"]["n"], " polo sur:", datos["polos"]["s"])
print("AAS (32.000 nT):", len(datos["aas"][0]["lineas"]), "tramo(s)")
print("ecuador magnético:", len(datos["ecuador"][0]["lineas"]), "tramo(s)")
print("deriva polo N 1900 →", datos["polos"]["derivaN"][0][1:], " 2026 →", datos["polos"]["derivaN"][-1][1:])
