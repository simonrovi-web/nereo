#!/usr/bin/env python3
"""NEREO v2 · archivo unificado 1906–2023.
Une el archivo histórico (planetsig, hasta 2014) con la extracción posterior
(tidytuesday/timothyrenner, hasta 2023), clasifica lo marítimo, marca evidencia
declarada, coincidencias con explicaciones convencionales y un índice de solidez.
No exporta texto narrativo."""
import base64, html, json, os, re
import numpy as np, pandas as pd
from shapely.geometry import shape as shp_shape, Point
from shapely.ops import unary_union
from shapely.prepared import prep

R1, R2 = "fuentes/historico", "fuentes/extension"
OUT = "data"

def unesc(s):
    return html.unescape(html.unescape(s)).replace("&#44", ",") if isinstance(s, str) else ""

# ── A. histórico ─────────────────────────────────────────────────────────
cols = ['datetime','city','state','country','shape','dur_s','dur_t','comments','posted','lat','lon']
a = pd.read_csv(f"{R1}/ufo.csv", names=cols, low_memory=False)
a['lat'] = pd.to_numeric(a.lat, errors='coerce'); a['lon'] = pd.to_numeric(a.lon, errors='coerce')
dt = pd.to_datetime(a['datetime'], format='%m/%d/%Y %H:%M', errors='coerce')
A = pd.DataFrame({
    'dt': dt, 'lat': a.lat, 'lon': a.lon,
    'city': a.city.map(unesc).str.strip().str.title(),
    'state': a.state.fillna('').str.upper(), 'cc': a.country.fillna('').str.upper(),
    'shape': a['shape'].fillna('unknown').str.lower().str.strip(),
    'dur': pd.to_numeric(a.dur_s, errors='coerce').fillna(0),
    'text': a.comments.map(unesc), 'img': False, 'src': 0})
A = A.dropna(subset=['dt','lat','lon'])
corte = A.dt.max()
print("histórico:", len(A), "| hasta", corte.date())

# ── B. extensión 2014–2023 ───────────────────────────────────────────────
b = pd.read_csv(f"{R2}/ufo23.csv", low_memory=False, keep_default_na=False)
p = pd.read_csv(f"{R2}/places.csv", low_memory=False, keep_default_na=False)
p = p.drop_duplicates(subset=['city','state','country_code'])
b = b.merge(p[['city','state','country_code','latitude','longitude','timezone']],
            on=['city','state','country_code'], how='left')
utc = pd.to_datetime(b.reported_date_time_utc, errors='coerce', utc=True)
loc = utc.copy().dt.tz_localize(None)
for tz, idx in b.groupby('timezone').groups.items():
    if not tz or tz == 'NA': continue
    try: loc.loc[idx] = utc.loc[idx].dt.tz_convert(tz).dt.tz_localize(None)
    except Exception: pass
B = pd.DataFrame({
    'dt': loc, 'lat': pd.to_numeric(b.latitude, errors='coerce'), 'lon': pd.to_numeric(b.longitude, errors='coerce'),
    'city': b.city.str.strip(), 'state': b.state.replace('NA','').str.upper(), 'cc': b.country_code.str.upper(),
    'shape': b['shape'].replace('NA','unknown').str.lower().str.strip(),
    'dur': pd.to_numeric(b.duration_seconds, errors='coerce').fillna(0),
    'text': b.summary.astype(str), 'img': b.has_images.astype(str).str.upper().eq('TRUE'), 'src': 1})
B = B.dropna(subset=['dt','lat','lon'])
B = B[B.dt > corte]
print("extensión:", len(B), "| hasta", B.dt.max().date())

df = pd.concat([A, B], ignore_index=True)
df = df[df.lat.between(-90,90) & df.lon.between(-180,180)]
df['year'] = df.dt.dt.year; df = df[(df.year >= 1900) & (df.year <= 2023)]
df['month'] = df.dt.dt.month; df['day'] = df.dt.dt.day; df['hour'] = df.dt.dt.hour
df['dur'] = df.dur.clip(0, 86400)
df = df.reset_index(drop=True)
N = len(df); print("TOTAL:", N)

c = df.text.str.lower()
def has(rx): return c.str.contains(rx, regex=True, na=False).values

# ── C. marítimo ──────────────────────────────────────────────────────────
m_emerge   = has(r"(?:out of the (?:water|ocean|sea|lake)|emerg\w+ from the (?:water|ocean|sea|lake)|rose (?:up )?(?:out )?(?:from|of) the (?:water|ocean|sea|lake)|came up out of the (?:water|ocean|sea|lake)|surfaced from)")
m_submerge = has(r"(?:into the (?:water|ocean|sea|lake)|submerg\w+|under ?water|beneath the (?:surface|water|waves)|under the (?:water|ocean|sea)|dove into the (?:water|ocean|sea|lake)|sank into the (?:water|sea|ocean|lake))")
m_over     = has(r"(?:over the (?:ocean|water|sea|gulf|bay|lake|atlantic|pacific|channel)|out (?:at|to) sea|off ?shore|over open water|above the (?:ocean|water|sea)|hovering over the (?:ocean|water|sea|lake)|miles (?:out|off) (?:to sea|the coast|shore))")
m_vessel   = has(r"(?:on (?:a|our|my|the) (?:boat|ship|yacht|kayak|canoe|ferry|barge|trawler)|fishing (?:boat|vessel|trip)|aboard (?:the|a|our) (?:ship|boat|vessel|carrier)|cruise ship|sail(?:ing|boat)|oil rig|navy (?:ship|vessel|destroyer)|coast guard (?:cutter|vessel|ship)|aircraft carrier|on deck)")
m_shore    = has(r"(?:on the beach|from the beach|at the beach|on the (?:shore|shoreline|pier|dock|jetty|boardwalk)|along the (?:coast|shoreline)|overlooking the (?:ocean|sea|bay|gulf)|coastal|lighthouse|harbou?r|marina|seawall)")

land_union = unary_union([shp_shape(f['geometry']) for f in json.load(open(f"{R1}/ne_land.geojson"))['features']])
lake_union = unary_union([shp_shape(f['geometry']) for f in json.load(open(f"{R1}/ne_lakes.geojson"))['features']])
land_p, lake_p, coast = prep(land_union), prep(lake_union), land_union.boundary
# cache por coordenada única (muchas ciudades repetidas)
key = list(zip(df.lon.round(4), df.lat.round(4)))
cache = {}
for k in set(key):
    pt = Point(k)
    cache[k] = ((not land_p.contains(pt)) or lake_p.contains(pt), pt.distance(coast) * 111.0)
over_water = np.array([cache[k][0] for k in key]); dist_km = np.array([cache[k][1] for k in key])
coastal = dist_km <= 20.0

mar = np.zeros(N, np.uint8)
mar[coastal | over_water | m_shore] = 1
mar[m_vessel] = 2
mar[m_over | over_water] = 3
mar[m_submerge] = 4
mar[m_emerge] = 5
flags = (m_emerge.astype(np.uint8) | m_submerge.astype(np.uint8) << 1 | m_over.astype(np.uint8) << 2 |
         m_vessel.astype(np.uint8) << 3 | m_shore.astype(np.uint8) << 4 |
         over_water.astype(np.uint8) << 5 | coastal.astype(np.uint8) << 6).astype(np.uint8)

# ── D. evidencia declarada ───────────────────────────────────────────────
e_video = has(r"(?:video ?(?:taped|tape|recorded|recording|footage|camera)?|videotaped|caught on (?:video|camera|tape)|filmed|camcorder|footage)")
e_foto  = has(r"(?:photo(?:graph|s|ed)?|pictures? (?:of|were|was) |took (?:a )?(?:picture|photo)|snapshot|digital camera)") | df.img.values
e_radar = has(r"(?:radar|air traffic control|atc |tower confirmed)")
e_multi = has(r"(?:multiple witness|several (?:people|witnesses)|many witnesses|witnessed by|\b(?:two|three|four|five|six|2|3|4|5|6) (?:of us|witnesses|people saw|observers))")
ev = (e_video.astype(np.uint8) | e_foto.astype(np.uint8) << 1 | e_radar.astype(np.uint8) << 2 | e_multi.astype(np.uint8) << 3).astype(np.uint8)

# ── E. coincidencias con explicaciones convencionales ────────────────────
md = df.month.values * 100 + df.day.values
LLUVIAS = [("Cuadrántidas",103,1),("Líridas",422,1),("Eta Acuáridas",505,2),("Delta Acuáridas",729,2),
           ("Perseidas",812,2),("Oriónidas",1021,2),("Leónidas",1117,1),("Gemínidas",1213,2)]
doy = df.dt.dt.dayofyear.values
def doy_of(mmdd): return pd.Timestamp(2001, mmdd//100, mmdd%100).dayofyear
luminoso = df['shape'].isin(['fireball','light','flash','teardrop','orb','star','unknown','other']).values
x_met = np.zeros(N, bool)
for _, mmdd, w in LLUVIAS:
    x_met |= (np.abs(doy - doy_of(mmdd)) <= w)
x_met &= luminoso
cc = df.cc.values
x_fuego = ((md == 704) & (cc == 'US')) | ((md == 701) & (cc == 'CA')) | ((md == 1105) & (cc == 'GB')) | (md == 1231) | (md == 101)

L = pd.read_csv(f"{R2}/launches.csv")
L = L[(L.state_code == 'US') & (L.launch_year <= 2023)]
ldates = set(pd.to_datetime(L.launch_date, errors='coerce').dropna().dt.date)
PUERTOS = [(28.5,-80.6),(34.7,-120.6),(37.9,-75.5)]   # Cañaveral, Vandenberg, Wallops
def hav(la1, lo1, la2, lo2):
    la1, lo1, la2, lo2 = map(np.radians, (la1, lo1, la2, lo2))
    h = np.sin((la2-la1)/2)**2 + np.cos(la1)*np.cos(la2)*np.sin((lo2-lo1)/2)**2
    return 6371 * 2 * np.arcsin(np.sqrt(h))
cerca = np.zeros(N, bool)
for la, lo in PUERTOS: cerca |= hav(df.lat.values, df.lon.values, la, lo) <= 800
dd = df.dt.dt.date.values
dnext = (df.dt + pd.Timedelta(days=1)).dt.date.values
x_lanz = cerca & np.array([(d in ldates) or (q in ldates) for d, q in zip(dd, dnext)]) & (df.hour.values >= 17) | \
         (cerca & np.array([d in ldates for d in dd]) & (df.hour.values < 7))
exp = (x_met.astype(np.uint8) | x_fuego.astype(np.uint8) << 1 | x_lanz.astype(np.uint8) << 2).astype(np.uint8)

# ── F. índice de solidez (0–5) ───────────────────────────────────────────
sol = (1 + ((ev & 3) > 0).astype(int) + ((ev & 4) > 0).astype(int) + ((ev & 8) > 0).astype(int)
         + ((df.dur.values >= 60) & (df.dur.values <= 3600)).astype(int) - (exp > 0).astype(int))
sol = np.clip(sol, 0, 5).astype(np.uint8)

# ── G. empaquetado ───────────────────────────────────────────────────────
SHAPES = ['light','triangle','circle','fireball','sphere','orb','disk','oval','formation','cigar','changing','flash',
          'rectangle','cylinder','diamond','chevron','egg','teardrop','cone','cross','star','other','unknown']
sidx = df['shape'].map({s:i for i,s in enumerate(SHAPES)}).fillna(len(SHAPES)-1).astype(np.uint8).values

def place(city, st, co):
    tail = st if st else co
    return f"{city}, {tail}" if city and tail else (city or tail or "—")
places = [place(a_, b_, c_) for a_, b_, c_ in zip(df.city.fillna(''), df.state.fillna(''), df.cc.fillna(''))]
uniq = sorted(set(places)); pm = {q:i for i,q in enumerate(uniq)}
pidx = np.array([pm[q] for q in places], np.uint32); assert len(uniq) < 65535, len(uniq)

b64 = lambda arr: base64.b64encode(np.ascontiguousarray(arr).tobytes()).decode()
core = {"n": N, "shapes": SHAPES, "places": uniq, "y0": int(df.year.min()), "y1": int(df.year.max()),
  "place": b64(pidx.astype(np.uint16)),
  "lat": b64(np.round(df.lat.values*1e4).astype(np.int32)), "lon": b64(np.round(df.lon.values*1e4).astype(np.int32)),
  "year": b64(df.year.values.astype(np.uint16)), "month": b64(df.month.values.astype(np.uint8)),
  "day": b64(df.day.values.astype(np.uint8)), "hour": b64(df.hour.values.astype(np.uint8)),
  "shape": b64(sidx), "mar": b64(mar), "flags": b64(flags), "ev": b64(ev), "exp": b64(exp), "sol": b64(sol),
  "dur": b64(np.minimum(np.round(np.log1p(df.dur.values)*1000), 65535).astype(np.uint16)),
  "dcoast": b64(np.minimum(np.round(dist_km), 65535).astype(np.uint16))}
os.makedirs(OUT, exist_ok=True)
json.dump(core, open(f"{OUT}/points.json","w"), separators=(",",":"), ensure_ascii=False)
print("points.json:", os.path.getsize(f"{OUT}/points.json")//1024, "KB | lugares:", len(uniq))

mdf = df[mar > 0]
LATAM = ['MX','BR','AR','CL','CO','PE','VE','EC','UY','PY','BO','CR','PA','GT','DO','PR','CU','HN','SV','NI']
vc = lambda s: {str(k): int(v) for k, v in s.items()}
stats = {"total": N, "marine_total": int((mar>0).sum()), "uso_total": int((mar>=4).sum()), "over_water": int(over_water.sum()),
 "corte": str(corte.date()), "hasta": str(df.dt.max().date()), "ext": int((df.src==1).sum()),
 "byYear": vc(df.year.value_counts().sort_index()), "byYearMarine": vc(mdf.year.value_counts().sort_index()),
 "byHour": vc(df.hour.value_counts().sort_index()), "byHourMarine": vc(mdf.hour.value_counts().sort_index()),
 "byShape": vc(df['shape'].value_counts()), "byShapeMarine": vc(mdf['shape'].value_counts()),
 "byMar": {str(k): int((mar==k).sum()) for k in range(6)},
 "rawFlags": {"emergió del agua": int(m_emerge.sum()), "entró al agua": int(m_submerge.sum()), "sobre el agua": int(m_over.sum()),
              "desde embarcación": int(m_vessel.sum()), "orilla / costa": int(m_shore.sum()),
              "coordenada sobre agua": int(over_water.sum()), "franja costera ≤20 km": int(coastal.sum())},
 "evidence": {"video": int(e_video.sum()), "foto": int(e_foto.sum()), "radar": int(e_radar.sum()), "multitestigo": int(e_multi.sum())},
 "explained": {"meteoros": int(x_met.sum()), "fuegos": int(x_fuego.sum()), "lanzamientos": int(x_lanz.sum()), "cualquiera": int((exp>0).sum())},
 "bySol": {str(k): int((sol==k).sum()) for k in range(6)},
 "byCountry": vc(df.cc.replace('', 'N/D').value_counts().head(14)),
 "latam": int(df.cc.isin(LATAM).sum()),
 "july4": int(((md==704)&(cc=='US')).sum()), "mediaDiaUS": round(float((cc=='US').sum())/365.25, 1),
 "topMarineCities": [[k, int(v)] for k, v in pd.Series([places[i] for i in mdf.index]).value_counts().head(25).items()],
 "medianDurMarine": float(mdf.dur.median()), "medianDurAll": float(df.dur.median())}
json.dump(stats, open(f"{OUT}/stats.json","w"), separators=(",",":"), ensure_ascii=False)
for k in ("total","marine_total","uso_total","ext","hasta","evidence","explained","bySol","latam","july4","mediaDiaUS"):
    print(" ", k, stats[k])
