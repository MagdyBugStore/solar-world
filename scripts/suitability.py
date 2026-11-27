#!/usr/bin/env python3
"""بلال: حساب صلاحية الأرض لمصر على شبكة 1/432 درجة (issue #5). الاستخدام:
  python3 scripts/suitability.py blocks   # يحسب بلاطة بلاطة (1 درجة) ويحفظ في work/grid/blocks (قابل للاستئناف)
  python3 scripts/suitability.py osm      # يرسم طبقات OSM على الشبكة العامة
  python3 scripts/suitability.py combine  # يدمج كل شيء في work/grid/classes.npz
كل العتبات «غير موثق» ما لم يُذكر مصدر؛ انظر docs/METHOD في data/README.md (issue #8).
"""
import json, os, sys
import numpy as np
import rasterio
from rasterio import features
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from scipy import ndimage as ndi
from shapely.geometry import shape

RAW = os.environ.get("RAW_DIR", "work/raw"); OSM = os.environ.get("OSM_OUT", "work/osm"); GRID = os.environ.get("GRID_DIR", "work/grid")
N = 432                      # خلايا لكل درجة
LON0, LAT1, LON1, LAT0 = 24.0, 32.0, 37.0, 22.0
W, H = (LON1 - LON0) * N, (LAT1 - LAT0) * N   # 5616 x 4320
W, H = int(W), int(H)
TR = from_origin(LON0, LAT1, 1 / N, 1 / N)
OK_LC = (20, 30, 60)         # shrubland, grassland, bare/sparse (ESA WorldCover)
LC_MIN = 0.5                 # غير موثق
ROUGH_WIN = 15               # بكسل DEM (3 قوس ثانية) = نحو 1.4 كم؛ المطلوب 1.3 كم تقريبا
BLK = f"{GRID}/blocks"

def reduce_to_cells(a, n_out=N):
    """متوسط مصفوفة (r,c) إلى (n_out,n_out) بحدود بكسل أقرب (لا يلزم قسمة صحيحة)."""
    r, c = a.shape; ri = np.round(np.linspace(0, r, n_out + 1)).astype(int); ci = np.round(np.linspace(0, c, n_out + 1)).astype(int)
    s = np.add.reduceat(np.add.reduceat(a, ri[:-1], axis=0), ci[:-1], axis=1)
    return s / np.outer(np.diff(ri), np.diff(ci))

def block(la, lo):
    out = f"{BLK}/{la}_{lo}.npz"
    if os.path.exists(out): return
    # --- DEM: انحدار وخشونة
    dp = f"{RAW}/dem/N{la:02d}_E{lo:03d}.tif"
    slope = np.full((N, N), 255, np.uint8); rough = np.full((N, N), 255, np.uint8)
    if os.path.exists(dp):
        with rasterio.open(dp) as ds:
            z = ds.read(1).astype("float32"); nd = ds.nodata
        if nd is not None: z[z == nd] = np.nan
        if np.isnan(z).all(): pass
        else:
            z = np.where(np.isnan(z), np.nanmean(z), z)
            dy = 3 / 3600 * 111_000; dx = dy * np.cos(np.radians(la + 0.5))
            gy, gx = np.gradient(z, dy, dx); sl = np.degrees(np.arctan(np.hypot(gx, gy)))
            m = ndi.uniform_filter(z, ROUGH_WIN); res = z - m; rg = np.sqrt(np.maximum(ndi.uniform_filter(res * res, ROUGH_WIN), 0))
            slope = np.clip(np.round(reduce_to_cells(sl) * 10), 0, 254).astype(np.uint8)   # عُشر درجة
            rough = np.clip(np.round(reduce_to_cells(rg)), 0, 254).astype(np.uint8)        # متر
    # --- WorldCover: نسبة الخلية الصالحة (عيّنة أقرب جار 4x4 لكل خلية = نحو 64 م)
    t = f"{RAW}/wc/N{(la // 3) * 3:02d}E{(lo // 3) * 3:03d}.tif"; lc = np.zeros((N, N), np.uint8)
    if os.path.exists(t):
        with rasterio.open(t) as ds:
            win = from_bounds(lo, la, lo + 1, la + 1, ds.transform)
            a = ds.read(1, window=win, out_shape=(N * 4, N * 4), resampling=rasterio.enums.Resampling.nearest)
        ok = np.isin(a, OK_LC).astype(np.float32)
        lc = np.round(ok.reshape(N, 4, N, 4).mean(axis=(1, 3)) * 100).astype(np.uint8)
    os.makedirs(BLK, exist_ok=True)
    np.savez_compressed(out, slope=slope, rough=rough, lc=lc)

def cmd_blocks():
    import time
    t0 = time.time()
    for la in range(22, 32):
        for lo in range(24, 37):
            block(la, lo)
        print("lat", la, "done", int(time.time() - t0), "s", flush=True)

def raster_layer(name, all_touched):
    out = np.zeros((H, W), np.uint8); batch = []
    def flush():
        if batch:
            features.rasterize(batch, out=out, transform=TR, default_value=1, all_touched=all_touched); batch.clear()
    with open(f"{OSM}/{name}.geojsonl") as f:
        for line in f:
            try: g = shape(json.loads(line)["geometry"])
            except Exception: continue
            if g.is_empty: continue
            batch.append((g, 1))
            if len(batch) >= 2000: flush()
    flush(); return out

def cmd_osm():
    os.makedirs(GRID, exist_ok=True)
    for name, at in (("protected", False), ("sand", False), ("water", False), ("landuse", False), ("roads", True), ("power", True)):
        a = raster_layer(name, at); np.save(f"{GRID}/osm_{name}.npy", np.packbits(a, axis=1)); print(name, int(a.sum()), "cells", flush=True)

def cmd_combine():
    import shapefile
    sl = np.full((H, W), 255, np.uint8); rg = np.full((H, W), 255, np.uint8); lc = np.zeros((H, W), np.uint8)
    for la in range(22, 32):
        for lo in range(24, 37):
            d = np.load(f"{BLK}/{la}_{lo}.npz"); r0 = int((LAT1 - (la + 1)) * N); c0 = int((lo - LON0) * N)
            sl[r0:r0 + N, c0:c0 + N] = d["slope"]; rg[r0:r0 + N, c0:c0 + N] = d["rough"]; lc[r0:r0 + N, c0:c0 + N] = d["lc"]
    L = lambda n: np.unpackbits(np.load(f"{GRID}/osm_{n}.npy"), axis=1)[:, :W].astype(bool)
    prot, sand, water, landuse, roads, power = (L(n) for n in ("protected", "sand", "water", "landuse", "roads", "power"))
    # داخل مصر (Natural Earth ADM0_A3 == EGY)
    sf = shapefile.Reader(f"{RAW}/ne/ne_10m_admin_0_countries")
    nm = [f[0] for f in sf.fields[1:]]
    geom = [shape(s.shape.__geo_interface__) for s in sf.iterShapeRecords() if dict(zip(nm, s.record)).get("ADM0_A3") == "EGY"][0]
    inside = features.rasterize([(geom, 1)], out_shape=(H, W), transform=TR, all_touched=False).astype(bool)
    rough_thr = float(os.environ.get("ROUGH_THR", "0"))
    base = inside & (lc >= LC_MIN * 100) & ~prot & ~sand & ~water & ~landuse & (sl != 255)
    if rough_thr: base &= rg < rough_thr
    sc = np.zeros((H, W), np.uint8)       # 0 غير صالح، 1: <=3°، 2: <=5°، 3: <=10°
    sc[base & (sl <= 100)] = 3; sc[base & (sl <= 50)] = 2; sc[base & (sl <= 30)] = 1
    # الوصول: مسافة بالخلايا إلى أقرب طريق أو خط كهرباء (عرض الخلية يتغير مع خط العرض؛ نستخدم 257 م شمال-جنوب و x cos(lat) شرق-غرب)
    infra = roads | power
    ac = np.zeros((H, W), np.uint8)       # 1: <=10 كم، 2: <=25 كم، 3: أبعد
    lat_c = LAT1 - (np.arange(H) + 0.5) / N
    sy = 111_000 / N; sx_mid = 111_000 / N * np.cos(np.radians(27))
    dist = np.zeros((H, W), np.float32)
    CH = 600; HALO = 120
    for r in range(0, H, CH):
        a = max(0, r - HALO); b = min(H, r + CH + HALO)
        d = ndi.distance_transform_edt(~infra[a:b], sampling=(sy, sx_mid)).astype(np.float32)
        dist[r:min(H, r + CH)] = d[r - a:r - a + min(CH, H - r)]
    ac[:] = 3; ac[dist <= 25_000] = 2; ac[dist <= 10_000] = 1
    np.savez_compressed(f"{GRID}/classes.npz", slope_class=sc, access_class=ac, slope_tenth=sl, rough=rg, lc=lc, inside=inside)
    print("suitable cells", {k: int((sc == k).sum()) for k in (1, 2, 3)}, "inside", int(inside.sum()))

if __name__ == "__main__":
    {"blocks": cmd_blocks, "osm": cmd_osm, "combine": cmd_combine}[sys.argv[1]]()
