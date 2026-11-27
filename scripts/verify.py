#!/usr/bin/env python3
"""بلال: فحوصات التحقق (issue #8) -> data/verification.json وطباعة النتيجة."""
import json, os
from shapely.geometry import shape
from pyproj import Geod
S = json.load(open("data/stats.json")); G = json.load(open("data/suitable_egypt.geojson"))
geod = Geod(ellps="WGS84"); ref = S["egypt_reference_area_km2"]
cls = {(c["slope_max_deg"], c["access_max_km"]): c["area_km2"] for c in S["classes"]}
checks = {}
checks["max_class_area_le_egypt"] = max(cls.values()) <= ref
sl, ac = (3, 5, 10), (10, 25, None)
checks["slope_nesting_3_le_5_le_10"] = all(cls[(3, a)] <= cls[(5, a)] <= cls[(10, a)] for a in ac)
checks["access_nesting_10_le_25_le_all"] = all(cls[(s, 10)] <= cls[(s, 25)] <= cls[(s, None)] for s in sl)
checks["grid_vs_natural_earth_area_diff_pct"] = round(100 * (S["egypt_cells_area_km2_from_grid"] - ref) / ref, 2)
# مساحة الـ polygons المعروضة لكل نسخة مقابل مساحة الشبكة
shown = {}
for s in (1, 2, 3):
    for a in (1, 2, 3):
        km2 = 0.0
        for f in G["features"]:
            if f["properties"]["s"] <= s and f["properties"]["a"] <= a:
                g = shape(f["geometry"]); km2 += abs(geod.geometry_area_perimeter(g)[0]) / 1e6
        key = f"slope<={ {1:3,2:5,3:10}[s] }, access<={ {1:10,2:25,3:'all'}[a] }"
        grid = cls[({1: 3, 2: 5, 3: 10}[s], {1: 10, 2: 25, 3: None}[a])]
        shown[key] = {"displayed_polygons_km2": round(km2), "grid_km2": grid, "displayed_vs_grid_pct": round(100 * km2 / grid, 1)}
xs, ys = [], []
npoly = 0
for f in G["features"]:
    g = shape(f["geometry"]); npoly += len(g.geoms) if hasattr(g, "geoms") else 1
    b = g.bounds; xs += [b[0], b[2]]; ys += [b[1], b[3]]
out = {"checks": checks, "geojson": {"features": len(G["features"]), "polygons": npoly, "bbox": [min(xs), min(ys), max(xs), max(ys)], "size_mb": round(os.path.getsize("data/suitable_egypt.geojson") / 1e6, 2)}, "displayed_vs_grid": shown}
json.dump(out, open("data/verification.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
