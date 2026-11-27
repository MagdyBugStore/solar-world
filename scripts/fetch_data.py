#!/usr/bin/env python3
"""بلال: تحميل البيانات المفتوحة لمصر فقط (issue #3). يكتب في RAW_DIR (افتراضي ./work/raw) ولا يُرفع للريبو.
المصادر (كلها مفتوحة، بلا مفتاح):
- حدود: Natural Earth 1:10m admin-0 v5.1.1 (public domain)
- ارتفاع: Copernicus DEM GLO-90 (s3://copernicus-dem-90m)
- غطاء أرضي: ESA WorldCover 2021 v200 (s3://esa-worldcover)
- OSM: Geofabrik egypt-latest.osm.pbf (ODbL)
الاستخدام: python3 scripts/fetch_data.py [dem|wc|osm|borders|all]
"""
import io, math, os, subprocess, sys, zipfile
import shapefile
from shapely.geometry import shape, box
from shapely.ops import unary_union

RAW = os.environ.get("RAW_DIR", "work/raw")
NE = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"
DEM = "https://copernicus-dem-90m.s3.amazonaws.com/Copernicus_DSM_COG_30_{ns}_00_{ew}_00_DEM/Copernicus_DSM_COG_30_{ns}_00_{ew}_00_DEM.tif"
WC = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{t}_Map.tif"
CC = os.environ.get("COUNTRY", "EGY")   # EGY أو LBY
OSM = {"EGY": "https://download.geofabrik.de/africa/egypt-latest.osm.pbf", "LBY": "https://download.geofabrik.de/africa/libya-latest.osm.pbf"}[CC]

def get(url, out):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out) and os.path.getsize(out) > 0 and not os.path.exists(out + ".part"):
        return True
    r = subprocess.run(["curl", "-fsSL", "--retry", "3", "-C", "-", "-o", out + ".part", url])
    if r.returncode != 0:
        print("FAILED", url); return False
    os.replace(out + ".part", out); return True

def borders():
    zp = os.path.join(RAW, "ne_10m_admin_0_countries.zip"); get(NE, zp)
    d = os.path.join(RAW, "ne"); zipfile.ZipFile(zp).extractall(d)
    sf = shapefile.Reader(os.path.join(d, "ne_10m_admin_0_countries"))
    names = [f[0] for f in sf.fields[1:]]
    for sr in sf.iterShapeRecords():
        rec = dict(zip(names, sr.record))
        if rec.get("ADM0_A3") == CC:
            return shape(sr.shape.__geo_interface__)
    raise SystemExit(CC + " not found")

def tiles(poly, step):
    x0, y0, x1, y1 = poly.bounds
    for la in range(math.floor(y0 / step) * step, math.ceil(y1 / step) * step, step):
        for lo in range(math.floor(x0 / step) * step, math.ceil(x1 / step) * step, step):
            if poly.intersects(box(lo, la, lo + step, la + step)):
                yield la, lo

def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    poly = borders()
    print(CC, "bounds", poly.bounds)
    if what in ("dem", "all"):
        n = 0
        for la, lo in tiles(poly, 1):
            ns, ew = "N%02d" % la, "E%03d" % lo
            if get(DEM.format(ns=ns, ew=ew), f"{RAW}/dem/{ns}_{ew}.tif"): n += 1
        print("dem tiles", n)
    if what in ("wc", "all"):
        n = 0
        for la, lo in tiles(poly, 3):
            t = "N%02dE%03d" % (la, lo)
            if get(WC.format(t=t), f"{RAW}/wc/{t}.tif"): n += 1
        print("worldcover tiles", n)
    if what in ("osm", "all"):
        get(OSM, f"{RAW}/{OSM.rsplit('/', 1)[1]}")

if __name__ == "__main__":
    main()
