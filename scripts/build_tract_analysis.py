#!/usr/bin/env python3
"""Build a tract-level analysis table for the Greater Boston prototype."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GEOJSON = DATA / "geojson"
RAW = DATA / "raw"
ANALYSIS = DATA / "analysis"

TRACTS_PATH = GEOJSON / "greater_boston_tracts_acs_svi.geojson"
EV_PATH = GEOJSON / "greater_boston_ev_charging_stations.geojson"
SOLAR_PATH = GEOJSON / "greater_boston_solar_pts_by_municipality.geojson"
DOE_LEAD_PATH = RAW / "doe_lead_2022_tracts.csv"
OUT_PATH = ANALYSIS / "greater_boston_tract_analysis.csv"

BASE_FIELDS = [
    "GEOID",
    "tract_name",
    "county",
    "population",
    "median_household_income",
    "poverty_rate",
    "renter_rate",
    "no_vehicle_rate",
    "multifamily_share",
    "rent_burdened_share",
    "svi_rpl_themes",
    "svi_rpl_theme1",
    "svi_rpl_theme2",
    "svi_rpl_theme3",
    "svi_rpl_theme4",
    "public_ev_station_count",
    "public_dc_fast_station_count",
    "public_dc_fast_port_count",
    "nearest_public_ev_station_miles",
    "solar_proxy_municipality",
    "municipal_solar_project_count",
    "municipal_residential_solar_project_count",
    "municipal_solar_capacity_dc_mw",
    "doe_lead_join_status",
]


def main() -> int:
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    tracts = load_geojson(TRACTS_PATH)["features"]
    ev_stations = load_geojson(EV_PATH)["features"]
    solar_municipalities = load_geojson(SOLAR_PATH)["features"]

    rows = [base_row(feature) for feature in tracts]
    tract_indexes = [spatial_index(feature) for feature in tracts]
    solar_indexes = [spatial_index(feature) for feature in solar_municipalities]

    assign_municipal_solar(rows, tract_indexes, solar_municipalities, solar_indexes)
    public_points = assign_ev_access(rows, tract_indexes, ev_stations)
    assign_nearest_public_ev(rows, tract_indexes, public_points)

    doe_fields = join_doe_lead(rows)
    write_csv(rows, BASE_FIELDS + doe_fields, OUT_PATH)
    print(f"wrote   {OUT_PATH} ({len(rows):,} rows)")
    return 0


def load_geojson(path: Path) -> dict:
    return json.loads(path.read_text())


def base_row(feature: dict) -> dict:
    props = feature["properties"]
    return {
        "GEOID": props.get("GEOID"),
        "tract_name": props.get("NAMELSAD"),
        "county": props.get("greater_boston_county"),
        "population": props.get("population"),
        "median_household_income": props.get("median_household_income"),
        "poverty_rate": props.get("poverty_rate"),
        "renter_rate": props.get("renter_rate"),
        "no_vehicle_rate": props.get("no_vehicle_rate"),
        "multifamily_share": props.get("multifamily_share"),
        "rent_burdened_share": props.get("rent_burdened_share"),
        "svi_rpl_themes": props.get("svi_rpl_themes"),
        "svi_rpl_theme1": props.get("svi_rpl_theme1"),
        "svi_rpl_theme2": props.get("svi_rpl_theme2"),
        "svi_rpl_theme3": props.get("svi_rpl_theme3"),
        "svi_rpl_theme4": props.get("svi_rpl_theme4"),
        "public_ev_station_count": 0,
        "public_dc_fast_station_count": 0,
        "public_dc_fast_port_count": 0,
        "nearest_public_ev_station_miles": "",
        "solar_proxy_municipality": "",
        "municipal_solar_project_count": 0,
        "municipal_residential_solar_project_count": 0,
        "municipal_solar_capacity_dc_mw": 0,
        "doe_lead_join_status": "not_available",
    }


def spatial_index(feature: dict) -> dict:
    geometry = feature["geometry"]
    coords = list(iter_points(geometry["coordinates"]))
    return {
        "feature": feature,
        "bbox": bbox(coords),
        "centroid": centroid(coords),
    }


def iter_points(coords):
    if not coords:
        return
    first = coords[0]
    if isinstance(first, (int, float)):
        yield (float(coords[0]), float(coords[1]))
        return
    for item in coords:
        yield from iter_points(item)


def bbox(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def assign_municipal_solar(
    rows: list[dict],
    tract_indexes: list[dict],
    solar_features: list[dict],
    solar_indexes: list[dict],
) -> None:
    for row, tract_index in zip(rows, tract_indexes):
        point = tract_index["centroid"]
        match = next(
            (
                feature
                for feature, index in zip(solar_features, solar_indexes)
                if bbox_contains(index["bbox"], point)
                and geometry_contains_point(feature["geometry"], point)
            ),
            None,
        )
        if not match:
            continue
        props = match["properties"]
        row["solar_proxy_municipality"] = props.get("TOWN") or ""
        row["municipal_solar_project_count"] = props.get("solar_project_count") or 0
        row["municipal_residential_solar_project_count"] = (
            props.get("residential_solar_project_count") or 0
        )
        row["municipal_solar_capacity_dc_mw"] = props.get("solar_capacity_dc_mw") or 0


def assign_ev_access(
    rows: list[dict],
    tract_indexes: list[dict],
    ev_stations: list[dict],
) -> list[tuple[float, float]]:
    public_points = []
    for station in ev_stations:
        props = station.get("properties", {})
        geometry = station.get("geometry") or {}
        if geometry.get("type") != "Point" or not is_public_station(props):
            continue
        point = tuple(geometry["coordinates"])
        public_points.append(point)
        dc_ports = int_or_zero(props.get("ev_dc_fast_num"))

        for row, tract_index in zip(rows, tract_indexes):
            if not bbox_contains(tract_index["bbox"], point):
                continue
            if geometry_contains_point(tract_index["feature"]["geometry"], point):
                row["public_ev_station_count"] += 1
                if dc_ports > 0:
                    row["public_dc_fast_station_count"] += 1
                    row["public_dc_fast_port_count"] += dc_ports
                break
    return public_points


def assign_nearest_public_ev(
    rows: list[dict],
    tract_indexes: list[dict],
    public_points: list[tuple[float, float]],
) -> None:
    for row, tract_index in zip(rows, tract_indexes):
        lon, lat = tract_index["centroid"]
        if not public_points:
            continue
        row["nearest_public_ev_station_miles"] = round(
            min(haversine_miles(lon, lat, point[0], point[1]) for point in public_points),
            3,
        )


def is_public_station(props: dict) -> bool:
    access = str(props.get("groups_with_access_code") or props.get("access_code") or "")
    status = str(props.get("status_code") or "").upper()
    return "PUBLIC" in access.upper() and status in {"", "E", "OPEN"}


def int_or_zero(value) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def bbox_contains(bounds: tuple[float, float, float, float], point: tuple[float, float]) -> bool:
    min_x, min_y, max_x, max_y = bounds
    x, y = point
    return min_x <= x <= max_x and min_y <= y <= max_y


def geometry_contains_point(geometry: dict, point: tuple[float, float]) -> bool:
    coords = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        return polygon_contains_point(coords, point)
    if geometry["type"] == "MultiPolygon":
        return any(polygon_contains_point(poly, point) for poly in coords)
    return False


def polygon_contains_point(polygon: list, point: tuple[float, float]) -> bool:
    if not polygon or not ring_contains_point(polygon[0], point):
        return False
    return not any(ring_contains_point(hole, point) for hole in polygon[1:])


def ring_contains_point(ring: list, point: tuple[float, float]) -> bool:
    x, y = point
    inside = False
    j = len(ring) - 1
    for i, current in enumerate(ring):
        xi, yi = current
        xj, yj = ring[j]
        intersects = (yi > y) != (yj > y) and x < ((xj - xi) * (y - yi) / (yj - yi) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


def haversine_miles(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius_miles = 3958.7613
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius_miles * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def join_doe_lead(rows: list[dict]) -> list[str]:
    if not DOE_LEAD_PATH.exists():
        return []

    with DOE_LEAD_PATH.open(newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        geoid_field = find_geoid_field(reader.fieldnames)
        if not geoid_field:
            return []
        lead_rows = {normalize_geoid(row[geoid_field]): row for row in reader}

    lead_fields = [
        f"doe_lead_{field}"
        for field in reader.fieldnames
        if field != geoid_field
    ]
    for row in rows:
        lead = lead_rows.get(normalize_geoid(row["GEOID"]))
        if not lead:
            continue
        row["doe_lead_join_status"] = "joined"
        for source_field, out_field in zip(
            [field for field in reader.fieldnames if field != geoid_field], lead_fields
        ):
            row[out_field] = lead.get(source_field, "")
    return lead_fields


def find_geoid_field(fields: list[str]) -> str | None:
    normalized = {field.lower().replace("_", ""): field for field in fields}
    for candidate in ("geoid", "tractgeoid", "censustract", "fips"):
        if candidate in normalized:
            return normalized[candidate]
    return None


def normalize_geoid(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(11)


def write_csv(rows: list[dict], fields: list[str], path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
