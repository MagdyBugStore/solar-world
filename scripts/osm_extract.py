#!/usr/bin/env python3
"""بلال: استخراج طبقات OSM لمصر (issue #4) إلى ملفات GeoJSON-lines في work/osm/ (خارج الريبو).
الطبقات: roads, power, protected, sand, water, landuse. كل سطر: {"type":"Feature","properties":{...},"geometry":{...}}
الذاكرة: يستخدم فهرس مواقع على القرص (dense_file_array) ويكتب مباشرة بلا تجميع في الذاكرة.
"""
import json, os, sys
import osmium
from osmium import filter as F

PBF = os.environ.get("PBF", "work/raw/egypt-latest.osm.pbf")
OUT = os.environ.get("OSM_OUT", "work/osm")
ROAD = {"motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link", "primary_link", "secondary_link"}
LANDUSE = {"residential", "industrial", "commercial", "military", "farmland", "quarry", "retail", "construction",
           "landfill", "railway", "cemetery", "farmyard", "orchard", "vineyard", "greenhouse_horticulture", "basin", "reservoir",
           # إضافات (التحقق من الاستبعاد): أراضٍ مشغولة أخرى
           "brownfield", "salt_pond", "religious", "education", "garages", "mining", "allotments", "depot", "port", "harbour", "plant_nursery", "meadow_farm"}
# place=region/state/district... مناطق إدارية كبيرة (فزان، تيبستي) مش أرض مشغولة، فنحصر في المستوطنات
SETTLEMENT = {"city", "town", "village", "hamlet", "suburb", "neighbourhood", "quarter", "city_block", "isolated_dwelling", "farm", "allotments", "locality", "square", "plot", "subdivision", "borough", "islet", "island"}
MAN_MADE = {"works", "wastewater_plant", "water_works", "petroleum_well", "mineshaft", "storage_tank", "silo", "pier"}

def classify(t, is_area):
    """returns list of layer names for tag dict t"""
    L = []
    if not is_area and t.get("highway") in ROAD: L.append("roads")
    if not is_area and t.get("power") in ("line", "minor_line", "cable"): L.append("power")
    if t.get("power") == "substation": L.append("power")
    if t.get("boundary") in ("protected_area", "national_park") or t.get("leisure") == "nature_reserve": L.append("protected")
    if t.get("natural") in ("sand", "dune"): L.append("sand")
    if t.get("natural") in ("water", "wetland") or t.get("waterway") == "riverbank" or t.get("landuse") == "reservoir": L.append("water")
    if t.get("man_made") in MAN_MADE or t.get("military") or t.get("power") in ("plant", "generator") or t.get("landuse") in LANDUSE or t.get("aeroway") in ("aerodrome", "runway") and is_area or (t.get("place") in SETTLEMENT and is_area): L.append("landuse")
    return L

def main():
    os.makedirs(OUT, exist_ok=True)
    files = {n: open(f"{OUT}/{n}.geojsonl", "w") for n in ("roads", "power", "protected", "sand", "water", "landuse")}
    counts = {n: 0 for n in files}; bad = 0
    fab = osmium.geom.GeoJSONFactory()
    keep = ("highway", "power", "boundary", "leisure", "natural", "waterway", "landuse", "aeroway", "place", "name", "protect_class", "water", "man_made", "military")
    fp = osmium.FileProcessor(PBF, osmium.osm.NODE | osmium.osm.WAY | osmium.osm.AREA) \
        .with_locations("dense_file_array," + OUT + "/nodes.idx").with_areas(
            F.KeyFilter("boundary", "leisure", "natural", "landuse", "aeroway", "place", "waterway", "highway", "power", "man_made", "military"))
    for o in fp:
        if o.is_node(): continue
        if o.is_way():
            if o.tags.get("highway") is None and o.tags.get("power") is None and o.tags.get("waterway") != "riverbank": continue
            tags = {t.k: t.v for t in o.tags}; layers = classify(tags, False)
            if o.tags.get("waterway") == "riverbank" or not layers: continue
            try: geom = fab.create_linestring(o)
            except RuntimeError: bad += 1; continue
        elif o.is_area():
            tags = {t.k: t.v for t in o.tags}; layers = classify(tags, True)
            if not layers: continue
            try: geom = fab.create_multipolygon(o)
            except RuntimeError: bad += 1; continue
        else:
            continue
        props = {k: tags[k] for k in keep if k in tags}
        line = '{"type":"Feature","properties":' + json.dumps(props, ensure_ascii=False) + ',"geometry":' + geom + "}\n"
        for n in layers:
            files[n].write(line); counts[n] += 1
    for f in files.values(): f.close()
    os.remove(f"{OUT}/nodes.idx") if os.path.exists(f"{OUT}/nodes.idx") else None
    counts['skipped_invalid_geometry'] = bad
    json.dump(counts, open(f"{OUT}/counts.json", "w"), indent=1)
    print(counts)

if __name__ == "__main__":
    main()
