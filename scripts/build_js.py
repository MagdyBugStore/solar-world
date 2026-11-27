#!/usr/bin/env python3
"""يحوّل data/*.json/geojson إلى data/*.js (متغيرات window) كي يعمل index.html بفتح الملف مباشرة (file://) بدون خادم."""
import json
for src, var, dst in (("data/suitable_egypt.geojson", "SUITABLE_EGYPT", "data/suitable_egypt.js"), ("data/stats.json", "SOLAR_STATS", "data/stats.js"), ("data/pvgis_egypt.json", "PVGIS_EGYPT", "data/pvgis_egypt.js")):
    open(dst, "w").write(f"window.{var}=" + json.dumps(json.load(open(src)), ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(dst)
