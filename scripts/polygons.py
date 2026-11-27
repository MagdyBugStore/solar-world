#!/usr/bin/env python3
"""بلال: تحويل الشبكة إلى polygons مبسّطة + stats.json (issue #6). يقرأ work/grid/classes.npz.
كل خلية لها كود واحد: s = أصغر فئة انحدار تقبلها (1: ≤3°، 2: ≤5°، 3: ≤10°)، a = أقرب فئة وصول (1: ≤10 كم، 2: ≤25 كم، 3: أبعد).
الواجهة تعرض الخلية لو s ≤ الانحدار المختار و a ≤ الوصول المختار.
"""
import datetime, json, math, os, sys
import numpy as np
from rasterio import features
from rasterio.transform import from_origin
from shapely.geometry import shape, mapping, MultiPolygon, Polygon
from shapely.ops import unary_union
from pyproj import Geod

GRID = os.environ.get("GRID_DIR", "work/grid"); RAW = os.environ.get("RAW_DIR", "work/raw"); OUT = os.environ.get("DATA_DIR", "data")
N = 432; CC = os.environ.get("COUNTRY", "EGY")   # EGY أو LBY
NAME = {"EGY": "egypt", "LBY": "libya"}[CC]
LON0, LAT1 = {"EGY": (24.0, 32.0), "LBY": (9.0, 34.0)}[CC]
TR = from_origin(LON0, LAT1, 1 / N, 1 / N)
SIMPLIFY_DEG = float(os.environ.get("SIMPLIFY_DEG", "0.006"))   # نحو 165 م، غير موثق
MIN_AREA_KM2 = float(os.environ.get("MIN_AREA_KM2", "60"))     # غير موثق

# مساحة نطاق خط عرض على WGS84 (إسقاط متساوي المساحة، مكافئ EPSG:6933): R_q^2 * Δλ * Δq/2
A, E2 = 6378137.0, 0.0066943799901413165
E = math.sqrt(E2)
def q(phi):
    s = math.sin(phi)
    return (1 - E2) * (s / (1 - E2 * s * s) - (1 / (2 * E)) * math.log((1 - E * s) / (1 + E * s)))
QP = q(math.pi / 2)
RQ2 = A * A / 2
def band_area_km2(lat_top, lat_bot, dlon_deg):
    return RQ2 * math.radians(dlon_deg) * (q(math.radians(lat_top)) - q(math.radians(lat_bot))) / 1e6

def main():
    d = np.load(f"{GRID}/classes.npz"); sc = d["slope_class"]; ac = d["access_class"]; inside = d["inside"]
    H, W = sc.shape
    code = np.where(sc > 0, sc * 10 + ac, 0).astype(np.uint8)
    # --- مساحة كل صف (كم²)
    row_area = np.array([band_area_km2(LAT1 - r / N, LAT1 - (r + 1) / N, 1 / N) for r in range(H)])
    # --- مساحة مصر المرجعية من Natural Earth (ADM0_A3 == EGY)
    import shapefile
    sf = shapefile.Reader(f"{RAW}/ne/ne_10m_admin_0_countries"); nm = [f[0] for f in sf.fields[1:]]
    rec = [(dict(zip(nm, s.record)), s) for s in sf.iterShapeRecords()]
    egy = [shape(s.shape.__geo_interface__) for r, s in rec if r.get("ADM0_A3") == CC][0]
    geod = Geod(ellps="WGS84")
    egy_area = abs(sum(geod.geometry_area_perimeter(p)[0] for p in (egy.geoms if hasattr(egy, "geoms") else [egy]))) / 1e6
    # --- stats
    stats = {"generated": datetime.date.today().isoformat(), "grid": {"cells_per_degree": N, "size": [W, H], "note": "الشبكة 1/432 درجة (نحو 257 م شمال-جنوب)، العرض يقل مع خط العرض؛ المساحات تحسب لكل صف بإسقاط متساوي المساحة على WGS84 (مكافئ EPSG:6933)"},
             f"{NAME}_reference_area_km2": round(egy_area), f"{NAME}_reference_source": f"Natural Earth 1:10m admin-0 v5.1.1 (ADM0_A3={CC})",
             f"{NAME}_cells_area_km2_from_grid": round(float((inside * row_area[:, None]).sum())), "classes": []}
    names = {1: 3, 2: 5, 3: 10}; accn = {1: 10, 2: 25, 3: None}
    for s in (1, 2, 3):
        for a in (1, 2, 3):
            m = (sc > 0) & (sc <= s) & (ac <= a)
            km2 = float((m * row_area[:, None]).sum())
            stats["classes"].append({"slope_max_deg": names[s], "access_max_km": accn[a], "area_km2": round(km2), f"pct_of_{NAME}": round(100 * km2 / egy_area, 2)})
    stats["thresholds"] = {"landcover": "ESA WorldCover 2021 v200: 20 shrubland, 30 grassland, 60 bare/sparse؛ نسبة الخلية ≥50% (غير موثق)", "slope": "متوسط الخلية من GLO-90؛ 3/5/10° (غير موثق)", "access": "مسافة إقليدية إلى أقرب طريق (motorway..secondary) أو خط كهرباء من OSM؛ 10/25 كم (غير موثق)", "dunes": "استبعاد OSM natural=sand/dune فقط؛ فلتر الخشونة مغلق لعدم قدرته على الفصل (انظر calibration_roughness.json)", "min_polygon_km2": MIN_AREA_KM2, "min_hole_km2": MIN_AREA_KM2, "simplify_deg": SIMPLIFY_DEG}
    stats["sources"] = [
        {"name": "Natural Earth admin-0 countries 1:10m v5.1.1", "url": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"},
        {"name": "Copernicus DEM GLO-90", "url": "https://registry.opendata.aws/copernicus-dem/"},
        {"name": "ESA WorldCover 2021 v200", "url": "https://esa-worldcover.org/"},
        {"name": "OpenStreetMap via Geofabrik egypt-latest.osm.pbf (27/11/2026)", "url": "https://download.geofabrik.de/africa/egypt.html"}]
    stats["notes"] = ["المساحات من شبكة 250 م، والشكل المعروض مبسّط ومحذوف منه الأجزاء الصغيرة", "لا توجد بيانات ملكية أو كادسترال ولا سعة شبكة الكهرباء"]
    # --- polygons: لكل كود
    feats = []
    for c in (11, 12, 13, 21, 22, 23, 31, 32, 33):
        mask = code == c
        if not mask.any(): continue
        polys = []
        for g, v in features.shapes(code, mask=mask, transform=TR, connectivity=8):
            p = shape(g)
            if p.area * 111.0 * 111.0 * 0.88 < MIN_AREA_KM2: continue   # تقريب أولي للمساحة قبل التبسيط
            p = Polygon(p.exterior, [h for h in p.interiors if Polygon(h).area * 111.0 * 111.0 * 0.88 >= MIN_AREA_KM2])   # حذف الثقوب الصغيرة
            p = p.simplify(SIMPLIFY_DEG, preserve_topology=True)
            if p.is_empty: continue
            polys.append(p)
        if not polys: continue
        mp = unary_union(polys)
        feats.append({"type": "Feature", "properties": {"s": c // 10, "a": c % 10}, "geometry": mapping(mp)})
        print("code", c, len(polys), "polygons", flush=True)
    def rnd(o):
        if isinstance(o, (list, tuple)): return [rnd(x) for x in o]
        return round(o, 4)
    for f in feats: f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
    os.makedirs(OUT, exist_ok=True)
    gj = f"{OUT}/suitable_{NAME}.geojson"
    with open(gj, "w") as f: json.dump({"type": "FeatureCollection", "features": feats}, f, separators=(",", ":"))
    sp = f"{OUT}/stats.json"
    if CC == "EGY":
        old = json.load(open(sp)) if os.path.exists(sp) else {}
        if "libya" in old: stats["libya"] = old["libya"]
        json.dump(stats, open(sp, "w"), ensure_ascii=False, indent=1)
    else:   # ليبيا: كائن متداخل داخل stats.json كي لا تتغير مفاتيح مصر التي يقرؤها egypt.html
        old = json.load(open(sp)); old[NAME] = stats
        json.dump(old, open(sp, "w"), ensure_ascii=False, indent=1)
    print("size MB", os.path.getsize(gj) / 1e6)
    print(json.dumps(stats["classes"], ensure_ascii=False)); print(NAME, "km2", stats[f"{NAME}_reference_area_km2"], "grid", stats[f"{NAME}_cells_area_km2_from_grid"])

if __name__ == "__main__":
    main()
