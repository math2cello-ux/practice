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
MAP_DATA = DATA / "map"

TRACTS_PATH = GEOJSON / "greater_boston_tracts_acs_svi.geojson"
EV_PATH = GEOJSON / "greater_boston_ev_charging_stations.geojson"
EJ_PATH = GEOJSON / "greater_boston_ej_blockgroups.geojson"
SOLAR_PATH = GEOJSON / "greater_boston_solar_pts_by_municipality.geojson"
DOE_LEAD_PATH = RAW / "doe_lead_2022_tracts.csv"
OUT_PATH = ANALYSIS / "greater_boston_tract_analysis.csv"
MAP_MANIFEST_PATH = MAP_DATA / "manifest.json"

DOE_LEAD_FIELDS = [
    "doe_lead_energy_burden",
    "doe_lead_electricity_energy_burden",
    "doe_lead_gas_energy_burden",
    "doe_lead_other_energy_burden",
    "doe_lead_avg_annual_energy_cost",
    "doe_lead_electricity_annual_energy_cost",
    "doe_lead_gas_annual_energy_cost",
    "doe_lead_other_annual_energy_cost",
    "doe_lead_total_households",
    "doe_lead_household_income",
]

DOE_LEAD_FIELD_MAP = {
    "energyburden%income": "doe_lead_energy_burden",
    "energyburden%incomeelectricity": "doe_lead_electricity_energy_burden",
    "energyburden%incomegas": "doe_lead_gas_energy_burden",
    "energyburden%incomeother": "doe_lead_other_energy_burden",
    "avgannualenergycost$": "doe_lead_avg_annual_energy_cost",
    "avgannualenergycost$electricity": "doe_lead_electricity_annual_energy_cost",
    "avgannualenergycost$gas": "doe_lead_gas_annual_energy_cost",
    "avgannualenergycost$other": "doe_lead_other_annual_energy_cost",
    "totalhouseholds": "doe_lead_total_households",
    "householdincome": "doe_lead_household_income",
}

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
    *DOE_LEAD_FIELDS,
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
    MAP_DATA.mkdir(parents=True, exist_ok=True)
    tracts = load_geojson(TRACTS_PATH)["features"]
    ev_stations = load_geojson(EV_PATH)["features"]
    ej_blockgroups = load_geojson(EJ_PATH)["features"]
    solar_municipalities = load_geojson(SOLAR_PATH)["features"]

    rows = [base_row(feature) for feature in tracts]
    tract_indexes = [spatial_index(feature) for feature in tracts]
    solar_indexes = [spatial_index(feature) for feature in solar_municipalities]

    assign_municipal_solar(rows, tract_indexes, solar_municipalities, solar_indexes)
    public_points = assign_ev_access(rows, tract_indexes, ev_stations)
    assign_nearest_public_ev(rows, tract_indexes, public_points)

    join_doe_lead(rows)
    write_csv(rows, BASE_FIELDS, OUT_PATH)
    print(f"wrote   {OUT_PATH} ({len(rows):,} rows)")
    write_map_outputs(rows, tracts, ev_stations, ej_blockgroups, solar_municipalities)
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
        **{field: "" for field in DOE_LEAD_FIELDS},
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

    lead_source_rows, fieldnames = open_lead_reader(DOE_LEAD_PATH)
    if not fieldnames:
        return []
    geoid_field = find_geoid_field(fieldnames)
    if not geoid_field:
        return []

    lead_rows = {}
    for row in lead_source_rows:
        geoid = normalize_geoid(row.get(geoid_field))
        if geoid and geoid != "00000000000":
            lead_rows[geoid] = row

    for row in rows:
        lead = lead_rows.get(normalize_geoid(row["GEOID"]))
        if not lead:
            row["doe_lead_join_status"] = "missing_geoid"
            continue
        row["doe_lead_join_status"] = "joined"
        for source_field in fieldnames:
            out_field = DOE_LEAD_FIELD_MAP.get(normalize_field_name(source_field))
            if out_field:
                row[out_field] = clean_lead_value(lead.get(source_field))
    return DOE_LEAD_FIELDS


def open_lead_reader(path: Path) -> tuple[list[dict], list[str]]:
    with path.open(newline="") as f:
        rows = list(csv.reader(f))

    header_index = next(
        (
            index
            for index, row in enumerate(rows)
            if find_geoid_field(row) and any("energy burden" in col.lower() for col in row)
        ),
        None,
    )
    if header_index is None:
        return [], []
    fieldnames = rows[header_index]
    data_rows = [dict(zip(fieldnames, row)) for row in rows[header_index + 1 :] if row]
    return data_rows, fieldnames


def find_geoid_field(fields: list[str]) -> str | None:
    normalized = {normalize_field_name(field): field for field in fields}
    for candidate in ("geoid", "tractgeoid", "censustract", "fips", "geographyid"):
        if candidate in normalized:
            return normalized[candidate]
    return None


def normalize_field_name(value: str) -> str:
    return (
        str(value or "")
        .lower()
        .replace("_", "")
        .replace(" ", "")
        .replace(".", "")
        .replace("(", "")
        .replace(")", "")
    )


def normalize_geoid(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(11)


def clean_lead_value(value):
    if value in (None, "", "-"):
        return ""
    text = str(value).replace(",", "").strip()
    try:
        number = float(text)
    except ValueError:
        return value
    if number.is_integer():
        return int(number)
    return number


def write_map_outputs(
    rows: list[dict],
    tracts: list[dict],
    ev_stations: list[dict],
    ej_blockgroups: list[dict],
    solar_municipalities: list[dict],
) -> None:
    row_lookup = {row["GEOID"]: row for row in rows}
    outputs = [
        write_map_geojson(
            "tracts",
            [
                {
                    "type": "Feature",
                    "properties": map_tract_properties(row_lookup[tract_geoid_from_feature(feature)]),
                    "geometry": round_geometry(feature["geometry"]),
                }
                for feature in tracts
                if tract_geoid_from_feature(feature) in row_lookup
            ],
            "tracts_energy_access.geojson",
            default=True,
        ),
        write_map_geojson(
            "ev",
            [compact_ev_feature(feature) for feature in ev_stations],
            "ev_stations.geojson",
            default=True,
        ),
        write_map_geojson(
            "solar",
            [compact_solar_feature(feature) for feature in solar_municipalities],
            "solar_municipalities.geojson",
            default=False,
        ),
        write_map_geojson(
            "ej",
            [compact_ej_feature(feature) for feature in ej_blockgroups],
            "ej_blockgroups.geojson",
            default=False,
        ),
    ]
    manifest = {
        "generated_by": "scripts/build_tract_analysis.py",
        "primary_metric": "doe_lead_energy_burden",
        "fallback_metric": "svi_rpl_themes",
        "layers": outputs,
    }
    MAP_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"wrote   {MAP_MANIFEST_PATH}")


def write_map_geojson(
    layer_id: str,
    features: list[dict],
    filename: str,
    default: bool,
) -> dict:
    path = MAP_DATA / filename
    collection = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(collection, separators=(",", ":"), allow_nan=False))
    print(f"wrote   {path} ({len(features):,} features)")
    return {
        "id": layer_id,
        "path": str(path.relative_to(ROOT)),
        "default": default,
        "features": len(features),
        "bytes": path.stat().st_size,
    }


def map_tract_properties(row: dict) -> dict:
    fields = [
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
        *DOE_LEAD_FIELDS,
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
    return {field: row.get(field, "") for field in fields}


def compact_ev_feature(feature: dict) -> dict:
    props = feature.get("properties", {})
    keep = [
        "station_name",
        "street_address",
        "city",
        "zip",
        "ev_network",
        "ev_level2_evse_num",
        "ev_dc_fast_num",
        "groups_with_access_code",
        "status_code",
    ]
    return {
        "type": "Feature",
        "properties": {field: props.get(field, "") for field in keep},
        "geometry": round_geometry(feature["geometry"]),
    }


def compact_solar_feature(feature: dict) -> dict:
    props = feature.get("properties", {})
    keep = [
        "TOWN",
        "COUNTY",
        "solar_project_count",
        "residential_solar_project_count",
        "solar_capacity_dc_mw",
        "estimated_annual_production_kwh",
    ]
    return {
        "type": "Feature",
        "properties": {field: props.get(field, "") for field in keep},
        "geometry": round_geometry(feature["geometry"]),
    }


def compact_ej_feature(feature: dict) -> dict:
    props = feature.get("properties", {})
    keep = [
        "GEOGRAPHIC",
        "GEOID",
        "MUNICIPALI",
        "EJ",
        "EJ_CRIT_DE",
        "PCT_MINORI",
        "BG_MHHI",
    ]
    return {
        "type": "Feature",
        "properties": {field: props.get(field, "") for field in keep},
        "geometry": round_geometry(feature["geometry"]),
    }


def round_geometry(geometry: dict) -> dict:
    return {
        "type": geometry["type"],
        "coordinates": round_coords(geometry["coordinates"]),
    }


def round_coords(coords):
    if not coords:
        return coords
    first = coords[0]
    if isinstance(first, (int, float)):
        return [round(float(coords[0]), 5), round(float(coords[1]), 5)]
    return [round_coords(item) for item in coords]


def tract_geoid_from_feature(feature: dict) -> str:
    props = feature["properties"]
    return str(props.get("GEOID") or props.get("GEOID20") or props.get("geoid"))


def write_csv(rows: list[dict], fields: list[str], path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
