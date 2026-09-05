#!/usr/bin/env python3
"""Generate the exhibition SVG outline from Tianditu administrative GeoJSON."""

import argparse
import json
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union


WIDTH = 1600
HEIGHT = 1000


def project(longitude, latitude):
    east = -3313821.05089796 + ((longitude - 72) / 68) * 6020641.180897959
    north = 1841646.983099264 + ((latitude - 18) / 36) * 4059657.334200998
    return (
        ((east + 3413821.05089796) / 6220641.180897959) * WIDTH,
        ((6001304.317300262 - north) / 4259657.334200998) * HEIGHT,
    )


def inset_project(longitude, latitude):
    left, top, right, bottom = 1348.8, 691.8, 1574.2, 976.3
    return (
        left + ((longitude - 105) / 20) * (right - left),
        top + ((25.5 - latitude) / 22.5) * (bottom - top),
    )


def ring_path(coords, projector):
    points = [projector(float(lon), float(lat)) for lon, lat, *_ in coords]
    if len(points) < 2:
        return ""
    head, *tail = points
    commands = [f"M{head[0]:.2f},{head[1]:.2f}"]
    commands.extend(f"L{x:.2f},{y:.2f}" for x, y in tail)
    commands.append("Z")
    return "".join(commands)


def line_path(coords, projector):
    points = [projector(float(lon), float(lat)) for lon, lat, *_ in coords]
    if len(points) < 2:
        return ""
    head, *tail = points
    commands = [f"M{head[0]:.2f},{head[1]:.2f}"]
    commands.extend(f"L{x:.2f},{y:.2f}" for x, y in tail)
    return "".join(commands)


def polygons(geometry):
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type == "MultiPolygon":
        return list(geometry.geoms)
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    collection = json.loads(args.input.read_text(encoding="utf-8"))
    province_features = [
        feature
        for feature in collection["features"]
        if feature["geometry"]["type"] in {"Polygon", "MultiPolygon"}
    ]
    country = unary_union([shape(feature["geometry"]) for feature in province_features])

    main_paths = []
    inset_paths = []
    for polygon in polygons(country):
        min_x, min_y, max_x, max_y = polygon.bounds
        if min_y >= 18 and max_x >= 72 and min_x <= 140:
            path = ring_path(polygon.exterior.coords, project)
            if path:
                main_paths.append(path)
        if max_x >= 105 and min_x <= 125 and max_y >= 3 and min_y <= 25.5:
            path = ring_path(polygon.exterior.coords, inset_project)
            if path:
                inset_paths.append(path)

    south_sea_paths = []
    for feature in collection["features"]:
        if feature["properties"].get("gb") != "156990000":
            continue
        for coords in feature["geometry"]["coordinates"]:
            path = line_path(coords, inset_project)
            if path:
                south_sea_paths.append(path)

    svg = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1000" role="img" aria-labelledby="map-title map-desc">',
        '  <title id="map-title">中华人民共和国标准矢量轮廓</title>',
        '  <desc id="map-desc">由国家地理信息公共服务平台天地图行政区划数据生成，审图号 GS（2024）0650号。</desc>',
        '  <defs>',
        '    <style>.outline{fill:none;stroke:#ffe15c;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.inset{stroke-width:1.5}</style>',
        '    <clipPath id="south-sea-inset"><rect x="1348.8" y="691.8" width="225.4" height="284.5"/></clipPath>',
        '  </defs>',
        '  <g id="official-mainland-outline" class="outline">',
    ]
    svg.extend(f'    <path d="{path}"/>' for path in main_paths)
    svg.extend([
        '  </g>',
        '  <g id="official-south-sea-inset" class="outline inset" clip-path="url(#south-sea-inset)">',
    ])
    svg.extend(f'    <path d="{path}"/>' for path in inset_paths)
    svg.extend(f'    <path d="{path}"/>' for path in south_sea_paths)
    svg.extend([
        '  </g>',
        '  <rect class="outline inset" x="1348.8" y="691.8" width="225.4" height="284.5"/>',
        '</svg>',
        '',
    ])
    args.output.write_text("\n".join(svg), encoding="utf-8")


if __name__ == "__main__":
    main()
