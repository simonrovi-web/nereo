import json, os
from shapely.geometry import shape as shp, MultiPolygon, Polygon
R="fuentes/extension"; OUT="data"
def rings(path, tol, amin):
    out=[]
    for f in json.load(open(path))['features']:
        g=shp(f['geometry']).buffer(0).simplify(tol, preserve_topology=True)
        for p in (g.geoms if isinstance(g, MultiPolygon) else [g]):
            if not isinstance(p, Polygon) or p.is_empty or p.area<amin: continue
            out.append([[round(x,2),round(y,2)] for x,y in p.exterior.coords])
            for r in p.interiors:
                if Polygon(r).area>=amin: out.append([[round(x,2),round(y,2)] for x,y in r.coords])
    return out
bat={k:rings(f"{R}/b{k}.geojson",0.22,1.2) for k in ("200","1000","3000","5000")}
lanes=[]
for f in json.load(open(f"{R}/lanes.geojson"))['features']:
    t=(f.get('properties') or {}).get('Type','')
    if t not in ('Major','Middle'): continue
    g=shp(f['geometry']).simplify(0.12)
    for ln in (g.geoms if hasattr(g,'geoms') else [g]):
        c=[[round(x,2),round(y,2)] for x,y in ln.coords]
        if len(c)>1: lanes.append([1 if t=='Major' else 0, c])
naval=[["SOCAL · complejo de entrenamiento",32.9,-118.6,170],["Point Mugu · Sea Range",33.6,-120.3,150],
       ["VACAPES · Virginia Capes",36.4,-74.6,190],["Jacksonville · área de operaciones",30.4,-79.9,170],
       ["AUTEC · Lengua del Océano",24.6,-77.7,110],["PMRF · Barking Sands",22.1,-160.1,160]]
puertos=[["Cabo Cañaveral",28.5,-80.6],["Vandenberg",34.7,-120.6],["Wallops",37.9,-75.5],["Kourou",5.2,-52.8],
         ["Baikonur",45.9,63.3],["Boca Chica · Starbase",25.99,-97.15],["Jiuquan",40.96,100.29],["Tanegashima",30.4,130.97]]
json.dump({"bat":bat,"lanes":lanes,"naval":naval,"puertos":puertos}, open(f"{OUT}/mar.json","w"), separators=(",",":"))
print({k:len(v) for k,v in bat.items()}, "lanes", len(lanes), os.path.getsize(f"{OUT}/mar.json")//1024, "KB")
print(set((f.get('properties') or {}).get('Type') for f in json.load(open(f"{R}/lanes.geojson"))['features']))
