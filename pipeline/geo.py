#!/usr/bin/env python3
"""Simplifica la geometría Natural Earth y la exporta compacta para el visor."""
import json, os
from shapely.geometry import shape as shp
from shapely.geometry import MultiPolygon, Polygon

RAW = "fuentes/historico"
OUT = "data"
os.makedirs(OUT, exist_ok=True)

def rings_from(geom, tol, min_area):
    out = []
    g = geom.simplify(tol, preserve_topology=True)
    polys = g.geoms if isinstance(g, MultiPolygon) else [g]
    for p in polys:
        if not isinstance(p, Polygon) or p.is_empty: continue
        if p.area < min_area: continue
        out.append([[round(x,3), round(y,3)] for x,y in p.exterior.coords])
        for r in p.interiors:
            if Polygon(r).area >= min_area:
                out.append([[round(x,3), round(y,3)] for x,y in r.coords])
    return out

def lines_from(fc, tol):
    out = []
    for f in fc['features']:
        g = shp(f['geometry']).simplify(tol, preserve_topology=True)
        geoms = g.geoms if hasattr(g, 'geoms') else [g]
        for ln in geoms:
            c = [[round(x,3), round(y,3)] for x,y in ln.coords]
            if len(c) > 1: out.append(c)
    return out

land = json.load(open(f"{RAW}/ne50_land.geojson"))
land_rings = []
for f in land['features']:
    land_rings += rings_from(shp(f['geometry']), 0.05, 0.004)

lakes = json.load(open(f"{RAW}/ne50_lakes.geojson"))
lake_rings = []
for f in lakes['features']:
    lake_rings += rings_from(shp(f['geometry']), 0.05, 0.02)

borders = lines_from(json.load(open(f"{RAW}/ne50_borders.geojson")), 0.08)

world = {"land": land_rings, "lakes": lake_rings, "borders": borders}
json.dump(world, open(f"{OUT}/world.json","w"), separators=(",",":"))
print("world.json:", os.path.getsize(f"{OUT}/world.json")//1024, "KB",
      "| anillos tierra:", len(land_rings), "| lagos:", len(lake_rings), "| fronteras:", len(borders))
