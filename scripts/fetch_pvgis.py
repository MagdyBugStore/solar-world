#!/usr/bin/env python3
"""بلال: إشعاع PVGIS على شبكة 1° داخل حدود مصر -> data/pvgis_egypt.json (طبقة اختيارية في egypt.html).
PVGIS v5.3 (SARAH3)، PVcalc: 1 كيلوواط ذروة، فقد 14%، ميل 25° جنوبا (الإعدادات افتراضات غير موثقة)."""
import json, os, time, urllib.request
import shapefile
from shapely.geometry import shape, Point
RAW = os.environ.get("RAW_DIR", "work/raw")
sf = shapefile.Reader(f"{RAW}/ne/ne_10m_admin_0_countries"); nm = [f[0] for f in sf.fields[1:]]
egy = [shape(s.shape.__geo_interface__) for s in sf.iterShapeRecords() if dict(zip(nm, s.record)).get("ADM0_A3") == "EGY"][0]
out = []
for la in range(22, 32):
    for lo in range(25, 37):
        c = (lo + 0.5, la + 0.5)
        if not egy.contains(Point(*c)): continue
        u = f"https://re.jrc.ec.europa.eu/api/v5_3/PVcalc?lat={c[1]}&lon={c[0]}&peakpower=1&loss=14&angle=25&aspect=0&raddatabase=PVGIS-SARAH3&outputformat=json"
        try:
            t = json.load(urllib.request.urlopen(u, timeout=30))["outputs"]["totals"]["fixed"]
            out.append({"lat": c[1], "lon": c[0], "E_y": t["E_y"], "H_y": t["H(i)_y"]})
        except Exception as e:
            print("skip", c, e)
        time.sleep(0.2)
json.dump({"source": "PVGIS v5.3 PVcalc, PVGIS-SARAH3", "url": "https://re.jrc.ec.europa.eu/pvg_tools/en/", "settings": "1 kWp، فقد 14%، ميل 25° جنوبا (افتراضات غير موثقة)", "units": {"E_y": "kWh/kWp/سنة", "H_y": "kWh/م²/سنة على المستوى المائل"}, "points": out}, open("data/pvgis_egypt.json", "w"), ensure_ascii=False)
print(len(out), "points")
