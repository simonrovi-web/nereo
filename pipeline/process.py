#!/usr/bin/env python3
"""Procesa el dataset NUFORC: limpia, clasifica avistamientos marítimos/USO y
empaqueta binarios compactos para el visor. No exporta texto narrativo verbatim,
solo metadatos y etiquetas derivadas."""
import base64, html, json, re, sys
import numpy as np
import pandas as pd
from shapely.geometry import shape as shp_shape, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely.prepared import prep

RAW = "fuentes/historico"
OUT = "data"

cols = ['datetime','city','state','country','shape','dur_s','dur_t','comments','posted','lat','lon']
df = pd.read_csv(f"{RAW}/ufo.csv", names=cols, low_memory=False)

# --- limpieza ---------------------------------------------------------------
def unesc(s):
    if not isinstance(s, str): return ""
    return html.unescape(html.unescape(s)).replace("&#44", ",")

df['comments'] = df['comments'].map(unesc)
df['city'] = df['city'].map(unesc).str.strip()
df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
df = df.dropna(subset=['lat','lon'])
df = df[(df.lat.between(-90,90)) & (df.lon.between(-180,180))]

dt = pd.to_datetime(df['datetime'], format='%m/%d/%Y %H:%M', errors='coerce')
df['year'] = dt.dt.year
df['month'] = dt.dt.month
df['hour'] = dt.dt.hour
df = df.dropna(subset=['year'])
df = df[(df.year >= 1900) & (df.year <= 2014)]
df['dur_s'] = pd.to_numeric(df['dur_s'], errors='coerce').fillna(0).clip(0, 86400)
df['shape'] = df['shape'].fillna('unknown').str.lower().str.strip()
df['country'] = df['country'].fillna('').str.lower()
df = df.reset_index(drop=True)
print("registros válidos:", len(df))

# --- clasificación marítima / USO ------------------------------------------
c = df['comments'].str.lower()

EMERGE = r"(out of the (water|ocean|sea|lake)|emerg\w+ from the (water|ocean|sea|lake)|rose (up )?(out )?(from|of) the (water|ocean|sea|lake)|came up out of the (water|ocean|sea|lake)|surfaced from)"
SUBMERGE = r"(into the (water|ocean|sea|lake)|submerg\w+|under ?water|beneath the (surface|water|waves)|under the (water|ocean|sea)|dove into the (water|ocean|sea|lake)|sank into the (water|sea|ocean|lake)|disappear\w* into the (water|ocean|sea|lake))"
OVERWATER = r"(over the (ocean|water|sea|gulf|bay|lake|atlantic|pacific|channel)|out (at|to) sea|off ?shore|over open water|above the (ocean|water|sea)|hovering over the (ocean|water|sea|lake)|miles (out|off) (to sea|the coast|shore))"
VESSEL = r"(on (a|our|my|the) (boat|ship|yacht|kayak|canoe|ferry|barge|trawler)|fishing (boat|vessel|trip)|aboard (the|a|our) (ship|boat|vessel|carrier)|cruise ship|sail(ing|boat)|oil rig|navy (ship|vessel|destroyer)|coast guard (cutter|vessel|ship)|merchant (ship|vessel)|aircraft carrier|on deck)"
SHORE = r"(on the beach|from the beach|at the beach|on the (shore|shoreline|pier|dock|jetty|boardwalk)|along the (coast|shoreline)|overlooking the (ocean|sea|bay|gulf)|coastal|lighthouse|harbou?r|marina|seawall|at the lake ?(shore|front)?)"

m_emerge   = c.str.contains(EMERGE, regex=True, na=False)
m_submerge = c.str.contains(SUBMERGE, regex=True, na=False)
m_over     = c.str.contains(OVERWATER, regex=True, na=False)
m_vessel   = c.str.contains(VESSEL, regex=True, na=False)
m_shore    = c.str.contains(SHORE, regex=True, na=False)

# --- geometría: tierra, lagos, distancia a costa ----------------------------
land = json.load(open(f"{RAW}/ne_land.geojson"))
land_geoms = [shp_shape(f['geometry']) for f in land['features']]
land_union = unary_union(land_geoms)
land_prep = prep(land_union)
coast = land_union.boundary

lakes = json.load(open(f"{RAW}/ne_lakes.geojson"))
lake_union = unary_union([shp_shape(f['geometry']) for f in lakes['features']])
lake_prep = prep(lake_union)

pts = [Point(xy) for xy in zip(df.lon.values, df.lat.values)]
on_land = np.array([land_prep.contains(p) for p in pts])
on_lake = np.array([lake_prep.contains(p) for p in pts])
over_water = (~on_land) | on_lake
print("sobre agua (geom):", int(over_water.sum()))

# distancia aproximada a la costa, en grados -> km (1 grado ~ 111 km)
tree = STRtree([coast])
dist_deg = np.array([p.distance(coast) for p in pts])
dist_km = dist_deg * 111.0
coastal = dist_km <= 20.0
print("costeros (<=20km):", int(coastal.sum()))

# --- código marítimo (prioridad descendente) --------------------------------
# 0 ninguno | 1 costero | 2 desde embarcación | 3 sobre el agua | 4 entró al agua | 5 emergió del agua
mar = np.zeros(len(df), dtype=np.uint8)
mar[coastal | over_water | m_shore.values] = 1
mar[m_vessel.values] = 2
mar[m_over.values | over_water] = 3
mar[m_submerge.values] = 4
mar[m_emerge.values] = 5
df['mar'] = mar
for k, v in zip(range(6), ["sin relación con agua","costero","desde embarcación","sobre el agua","entró al agua","emergió del agua"]):
    print(f"  mar={k} {v}: {(mar==k).sum()}")

# bits independientes, para que el filtro no dependa de la jerarquía
flags = (m_emerge.values.astype(np.uint8)       << 0 |
         m_submerge.values.astype(np.uint8)     << 1 |
         m_over.values.astype(np.uint8)         << 2 |
         m_vessel.values.astype(np.uint8)       << 3 |
         m_shore.values.astype(np.uint8)        << 4 |
         over_water.astype(np.uint8)            << 5 |
         coastal.astype(np.uint8)               << 6).astype(np.uint8)
# evidencia declarada en el relato
EV_VIDEO = r"(video ?(taped|tape|recorded|recording|footage|camera)?|videotaped|caught on (video|camera|tape)|filmed|camcorder|footage)"
EV_FOTO  = r"(photo(graph|s|ed)?|pictures? (of|were|was) |took (a )?(picture|photo)|snapshot|digital camera)"
EV_RADAR = r"(radar|air traffic control|atc |tower confirmed)"
EV_MULTI = r"(multiple witness|several (people|witnesses)|many witnesses|witnessed by)"
ev = (c.str.contains(EV_VIDEO,regex=True,na=False).values.astype(np.uint8) << 0 |
      c.str.contains(EV_FOTO ,regex=True,na=False).values.astype(np.uint8) << 1 |
      c.str.contains(EV_RADAR,regex=True,na=False).values.astype(np.uint8) << 2 |
      c.str.contains(EV_MULTI,regex=True,na=False).values.astype(np.uint8) << 3).astype(np.uint8)
EVCOUNTS = {"video":int((ev&1>0).sum()),"foto":int((ev&2>0).sum()),
            "radar":int((ev&4>0).sum()),"multitestigo":int((ev&8>0).sum())}
print("evidencia:", EVCOUNTS)

RAWFLAGS = {"emergió del agua": int(m_emerge.sum()), "entró al agua": int(m_submerge.sum()),
            "sobre el agua": int(m_over.sum()), "desde embarcación": int(m_vessel.sum()),
            "orilla / costa": int(m_shore.sum()), "coordenada sobre agua": int(over_water.sum()),
            "franja costera ≤20 km": int(coastal.sum())}
print("flags crudos:", RAWFLAGS)

# --- formas -----------------------------------------------------------------
SHAPES = ['light','triangle','circle','fireball','sphere','disk','oval','formation','cigar',
          'changing','flash','rectangle','cylinder','diamond','chevron','egg','teardrop',
          'cone','cross','other','unknown']
sidx = df['shape'].map({s:i for i,s in enumerate(SHAPES)}).fillna(len(SHAPES)-1).astype(np.uint8)

# --- empaquetado binario ----------------------------------------------------
def b64(arr): return base64.b64encode(arr.tobytes()).decode()

lat_i = np.round(df.lat.values * 1e4).astype(np.int32)
lon_i = np.round(df.lon.values * 1e4).astype(np.int32)
year  = df.year.values.astype(np.uint16)
month = df.month.fillna(0).values.astype(np.uint8)
hour  = df.hour.fillna(99).values.astype(np.uint8)
dur   = np.minimum(np.round(np.log1p(df.dur_s.values) * 1000), 65535).astype(np.uint16)
dkm   = np.minimum(np.round(dist_km), 65535).astype(np.uint16)

# diccionario de lugares: "ciudad, estado/país" -> índice
def place(r):
    city = (r.city or "").strip().title()
    st = (r.state or "").upper() if isinstance(r.state, str) else ""
    co = (r.country or "").upper()
    tail = st if st else co
    return f"{city}, {tail}" if city and tail else (city or tail or "—")

places = [place(r) for r in df.itertuples()]
uniq = sorted(set(places))
pidx_map = {p: i for i, p in enumerate(uniq)}
pidx = np.array([pidx_map[p] for p in places], dtype=np.uint32)
assert len(uniq) < 65535, len(uniq)
pidx = pidx.astype(np.uint16)
print("lugares únicos:", len(uniq))

core = {
  "n": int(len(df)),
  "shapes": SHAPES,
  "places": uniq,
  "place": b64(pidx),
  "marLabels": ["—","costero","desde embarcación","sobre el agua","entró al agua","emergió del agua"],
  "lat": b64(lat_i), "lon": b64(lon_i), "year": b64(year), "month": b64(month),
  "hour": b64(hour), "shape": b64(sidx.values), "mar": b64(mar), "flags": b64(flags), "ev": b64(ev), "dur": b64(dur), "dcoast": b64(dkm),
}
import os
os.makedirs(OUT, exist_ok=True)
json.dump(core, open(f"{OUT}/points.json","w"), separators=(",",":"))
print("points.json:", os.path.getsize(f"{OUT}/points.json")//1024, "KB")

mdf = df[df.mar > 0].copy()

# --- estadísticas agregadas -------------------------------------------------
stats = {
 "total": int(len(df)),
 "marine_total": int((mar>0).sum()),
 "uso_total": int(((mar==4)|(mar==5)).sum()),
 "over_water": int(over_water.sum()),
 "byYear": {str(int(y)): int(n) for y,n in df.year.value_counts().sort_index().items()},
 "byYearMarine": {str(int(y)): int(n) for y,n in mdf.year.value_counts().sort_index().items()},
 "byHour": {str(int(h)): int(n) for h,n in df[df.hour<24].hour.value_counts().sort_index().items()},
 "byHourMarine": {str(int(h)): int(n) for h,n in mdf[mdf.hour<24].hour.value_counts().sort_index().items()},
 "byShape": {s: int(n) for s,n in df['shape'].value_counts().items()},
 "byShapeMarine": {s: int(n) for s,n in mdf['shape'].value_counts().items()},
 "byMar": {str(k): int((mar==k).sum()) for k in range(6)},
 "rawFlags": RAWFLAGS,
 "evidence": EVCOUNTS,
 "byCountry": {c: int(n) for c,n in df['country'].replace('', 'n/d').value_counts().head(12).items()},
 "topMarineCities": [[c.title(), int(n)] for c,n in mdf.city.value_counts().head(25).items()],
 "medianDurMarine": float(mdf.dur_s.median()),
 "medianDurAll": float(df.dur_s.median()),
}
json.dump(stats, open(f"{OUT}/stats.json","w"), separators=(",",":"))
print("stats.json ok | marítimos:", stats["marine_total"], "| USO:", stats["uso_total"])
