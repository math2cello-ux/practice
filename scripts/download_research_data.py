#!/usr/bin/env python3
"""Download Greater Boston research datasets and write GeoJSON outputs."""

from __future__ import annotations

import csv
import json
import math
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
import shapefile
from pyproj import CRS, Transformer


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
GEOJSON = DATA / "geojson"

GREATER_BOSTON_COUNTIES = {
    "009": "Essex",
    "017": "Middlesex",
    "021": "Norfolk",
    "023": "Plymouth",
    "025": "Suffolk",
}

ACS_TABLES = [
    "B01003",
    "B03002",
    "B17001",
    "B19013",
    "B25003",
    "B25024",
    "B25044",
    "B25070",
]

SOURCES = {
    "tracts": "https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_25_tract_500k.zip",
    "svi": "https://svi.cdc.gov/Documents/Data/2022/csv/states/Massachusetts.csv",
    "ej": "https://s3.us-east-1.amazonaws.com/download.massgis.digital.mass.gov/shapefiles/census2020/ej2020.zip",
    "municipalities": "https://s3.us-east-1.amazonaws.com/download.massgis.digital.mass.gov/shapefiles/state/townssurvey_shp.zip",
    "masscec_pts_page": "https://www.masscec.com/production-tracking-system-pts",
    "ev_arcgis": "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/Alternative_Fueling_Stations/FeatureServer/0/query",
    "census_reporter": "https://api.censusreporter.org/1.0/data/show/latest",
    "lead_archive": "https://zenodo.org/records/14758685",
}


def ensure_dirs() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    GEOJSON.mkdir(parents=True, exist_ok=True)


def request_get(url: str, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", "greater-boston-energy-equity-research/1.0")
    response = requests.get(url, headers=headers, timeout=kwargs.pop("timeout", 60), **kwargs)
    response.raise_for_status()
    return response


def download(url: str, path: Path) -> Path:
    if path.exists() and path.stat().st_size > 0:
        print(f"exists  {path}")
        return path
    print(f"download {url}")
    with request_get(url, stream=True, timeout=120) as response:
        with path.open("wb") as out:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    out.write(chunk)
    print(f"wrote   {path} ({path.stat().st_size:,} bytes)")
    return path


def unzip(zip_path: Path, out_dir: Path) -> Path:
    marker = out_dir / ".unzipped"
    if marker.exists():
        return out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out_dir)
    marker.write_text("ok\n")
    return out_dir


def find_shp(folder: Path, pattern: str | None = None) -> Path:
    matches = sorted(folder.rglob("*.shp"))
    if pattern:
        matches = [p for p in matches if re.search(pattern, p.name, re.I)]
    if not matches:
        raise FileNotFoundError(f"No shapefile found in {folder}")
    return matches[0]


def geometry_transformer(shp_path: Path) -> Transformer | None:
    prj = shp_path.with_suffix(".prj")
    if not prj.exists():
        return None
    text = prj.read_text(errors="ignore")
    try:
        source = CRS.from_wkt(text)
        target = CRS.from_epsg(4326)
        if source.equals(target):
            return None
        return Transformer.from_crs(source, target, always_xy=True)
    except Exception:
        return None


def transform_coords(coords, transformer: Transformer | None):
    if transformer is None:
        return coords
    if not coords:
        return coords
    first = coords[0]
    if isinstance(first, (float, int)):
        x, y = transformer.transform(coords[0], coords[1])
        return [x, y]
    return [transform_coords(item, transformer) for item in coords]


def read_shapefile_features(shp_path: Path, keep_fn=None) -> list[dict]:
    reader = shapefile.Reader(str(shp_path))
    fields = [field[0] for field in reader.fields[1:]]
    transformer = geometry_transformer(shp_path)
    features = []
    for shape_record in reader.iterShapeRecords():
        props = dict(zip(fields, shape_record.record))
        if keep_fn and not keep_fn(props):
            continue
        geom = shape_record.shape.__geo_interface__
        geom = dict(geom)
        geom["coordinates"] = transform_coords(geom["coordinates"], transformer)
        features.append({"type": "Feature", "properties": props, "geometry": geom})
    return features


def write_geojson(features: list[dict], path: Path) -> None:
    collection = clean_json_value({"type": "FeatureCollection", "features": features})
    path.write_text(json.dumps(collection, separators=(",", ":"), allow_nan=False))
    print(f"wrote   {path} ({len(features):,} features)")


def load_geojson(path: Path) -> dict:
    return json.loads(path.read_text())


def county_from_geoid(geoid: str) -> str:
    return geoid[2:5]


def tract_geoid_from_feature(feature: dict) -> str:
    props = feature["properties"]
    return str(props.get("GEOID") or props.get("GEOID20") or props.get("geoid"))


def download_tract_boundaries() -> Path:
    zip_path = download(SOURCES["tracts"], RAW / "cb_2022_25_tract_500k.zip")
    folder = unzip(zip_path, RAW / "cb_2022_25_tract_500k")
    shp = find_shp(folder)

    features = read_shapefile_features(
        shp,
        keep_fn=lambda p: str(p.get("COUNTYFP")) in GREATER_BOSTON_COUNTIES,
    )
    for feature in features:
        geoid = str(feature["properties"].get("GEOID"))
        county = county_from_geoid(geoid)
        feature["properties"]["greater_boston_county"] = GREATER_BOSTON_COUNTIES[county]
        feature["properties"]["greater_boston_county_definition"] = (
            "Essex, Middlesex, Norfolk, Plymouth, and Suffolk counties"
        )
    out = GEOJSON / "greater_boston_tracts.geojson"
    write_geojson(features, out)
    return out


def flatten_census_reporter(data: dict) -> dict[str, dict]:
    rows = {}
    for geo_id, table_data in data["data"].items():
        if not geo_id.startswith("14000US"):
            continue
        geoid = geo_id.replace("14000US", "")
        row = rows.setdefault(geoid, {"GEOID": geoid})
        for table_id, payload in table_data.items():
            estimates = payload.get("estimate", {})
            for variable, value in estimates.items():
                row[variable] = value
    return rows


def download_acs() -> Path:
    rows: dict[str, dict] = {}
    for county in GREATER_BOSTON_COUNTIES:
        params = {
            "table_ids": ",".join(ACS_TABLES),
            "geo_ids": f"140|05000US25{county}",
        }
        data = request_get(SOURCES["census_reporter"], params=params, timeout=120).json()
        rows.update(flatten_census_reporter(data))

    for row in rows.values():
        total_pop = safe_num(row.get("B01003001"))
        poverty_total = safe_num(row.get("B17001001"))
        poverty = safe_num(row.get("B17001002"))
        tenure_total = safe_num(row.get("B25003001"))
        owner = safe_num(row.get("B25003002"))
        renter = safe_num(row.get("B25003003"))
        vehicle_total = safe_num(row.get("B25044001"))
        no_vehicle = safe_num(row.get("B25044003")) + safe_num(row.get("B25044010"))
        housing_total = safe_num(row.get("B25024001"))
        single_family = safe_num(row.get("B25024002")) + safe_num(row.get("B25024003"))
        multifamily = sum(safe_num(row.get(f"B250240{i:02d}")) for i in range(4, 11))
        rent_total = safe_num(row.get("B25070001"))
        rent_burdened = sum(safe_num(row.get(f"B250700{i:02d}")) for i in range(7, 11))
        race_total = safe_num(row.get("B03002001"))

        row.update(
            {
                "population": total_pop,
                "median_household_income": safe_num(row.get("B19013001")),
                "poverty_rate": pct(poverty, poverty_total),
                "renter_rate": pct(renter, tenure_total),
                "owner_occupied_rate": pct(owner, tenure_total),
                "no_vehicle_rate": pct(no_vehicle, vehicle_total),
                "single_family_share": pct(single_family, housing_total),
                "multifamily_share": pct(multifamily, housing_total),
                "rent_burdened_share": pct(rent_burdened, rent_total),
                "hispanic_or_latino_share": pct(safe_num(row.get("B03002012")), race_total),
                "non_hispanic_white_share": pct(safe_num(row.get("B03002003")), race_total),
                "non_hispanic_black_share": pct(safe_num(row.get("B03002004")), race_total),
                "non_hispanic_asian_share": pct(safe_num(row.get("B03002006")), race_total),
            }
        )

    path = RAW / "greater_boston_acs_census_reporter.csv"
    fieldnames = sorted({key for row in rows.values() for key in row})
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows.values())
    print(f"wrote   {path} ({len(rows):,} rows)")
    return path


def safe_num(value) -> float:
    if value is None or value == "":
        return math.nan
    try:
        return float(value)
    except Exception:
        return math.nan


def pct(numerator: float, denominator: float) -> float | None:
    if denominator is None or denominator == 0 or math.isnan(denominator):
        return None
    if numerator is None or math.isnan(numerator):
        return None
    return numerator / denominator


def join_acs_to_tracts(tracts_path: Path, acs_path: Path) -> Path:
    tracts = load_geojson(tracts_path)
    acs = pd.read_csv(acs_path, dtype={"GEOID": str}).set_index("GEOID").to_dict("index")
    for feature in tracts["features"]:
        geoid = tract_geoid_from_feature(feature)
        feature["properties"].update(acs.get(geoid, {}))
    out = GEOJSON / "greater_boston_tracts_acs.geojson"
    tracts = clean_json_value(tracts)
    out.write_text(json.dumps(tracts, separators=(",", ":"), allow_nan=False))
    print(f"wrote   {out} ({len(tracts['features']):,} features)")
    return out


def download_svi_and_join(tracts_path: Path) -> Path:
    csv_path = download(SOURCES["svi"], RAW / "cdc_svi_2022_massachusetts.csv")
    svi = pd.read_csv(csv_path, dtype={"FIPS": str})
    svi = svi[svi["FIPS"].str[2:5].isin(GREATER_BOSTON_COUNTIES)]
    selected = [
        "FIPS",
        "RPL_THEMES",
        "RPL_THEME1",
        "RPL_THEME2",
        "RPL_THEME3",
        "RPL_THEME4",
        "E_TOTPOP",
        "EP_POV150",
        "EP_UNEMP",
        "EP_NOHSDP",
        "EP_UNINSUR",
        "EP_AGE65",
        "EP_LIMENG",
        "EP_MINRTY",
        "EP_MUNIT",
        "EP_MOBILE",
        "EP_NOVEH",
        "EP_GROUPQ",
    ]
    selected = [col for col in selected if col in svi.columns]
    svi = svi[selected].rename(columns={col: f"svi_{col.lower()}" for col in selected if col != "FIPS"})

    tracts = load_geojson(tracts_path)
    lookup = svi.set_index("FIPS").to_dict("index")
    for feature in tracts["features"]:
        geoid = tract_geoid_from_feature(feature)
        feature["properties"].update(lookup.get(geoid, {}))

    svi_csv = RAW / "greater_boston_svi_2022.csv"
    svi.to_csv(svi_csv, index=False)
    print(f"wrote   {svi_csv} ({len(svi):,} rows)")

    out = GEOJSON / "greater_boston_tracts_acs_svi.geojson"
    tracts = clean_json_value(tracts)
    out.write_text(json.dumps(tracts, separators=(",", ":"), allow_nan=False))
    print(f"wrote   {out} ({len(tracts['features']):,} features)")
    return out


def download_ej() -> Path:
    zip_path = download(SOURCES["ej"], RAW / "massgis_ej2020.zip")
    folder = unzip(zip_path, RAW / "massgis_ej2020")
    shp = find_shp(folder)

    def keep(props: dict) -> bool:
        geoid = str(
            props.get("GEOID20")
            or props.get("GEOID")
            or props.get("BG_ID")
            or props.get("BLKGRP")
            or ""
        )
        return len(geoid) >= 5 and geoid[2:5] in GREATER_BOSTON_COUNTIES

    features = read_shapefile_features(shp, keep_fn=keep)
    out = GEOJSON / "greater_boston_ej_blockgroups.geojson"
    write_geojson(features, out)
    return out


def normalize_town(value) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def download_municipalities() -> tuple[Path, set[str]]:
    zip_path = download(SOURCES["municipalities"], RAW / "townssurvey_shp.zip")
    folder = unzip(zip_path, RAW / "townssurvey_shp")
    shp = find_shp(folder, pattern=r"POLYM_GENCOAST")
    county_names = {name.upper() for name in GREATER_BOSTON_COUNTIES.values()}
    features = read_shapefile_features(
        shp,
        keep_fn=lambda p: str(p.get("COUNTY", "")).upper() in county_names,
    )
    towns = {normalize_town(feature["properties"].get("TOWN")) for feature in features}
    out = GEOJSON / "greater_boston_municipalities.geojson"
    write_geojson(features, out)
    return out, towns


def download_ev_chargers(greater_boston_towns: set[str] | None = None) -> Path:
    features = []
    offset = 0
    page_size = 2000
    while True:
        params = {
            "where": "State='MA' AND Fuel_Type_Code='ELEC'",
            "outFields": "*",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        }
        data = request_get(SOURCES["ev_arcgis"], params=params, timeout=120).json()
        page = data.get("features", [])
        features.extend(page)
        if len(page) < page_size:
            break
        offset += page_size

    out = GEOJSON / "massachusetts_ev_charging_stations.geojson"
    write_geojson(features, out)

    gb_features = []
    if greater_boston_towns:
        gb_features = [
            feature
            for feature in features
            if normalize_town(feature.get("properties", {}).get("city")) in greater_boston_towns
        ]
    if gb_features:
        gb_out = GEOJSON / "greater_boston_ev_charging_stations.geojson"
        write_geojson(gb_features, gb_out)
        return gb_out
    return out


def find_masscec_solar_download() -> str | None:
    html = request_get(SOURCES["masscec_pts_page"], timeout=60).text
    match = re.search(r'href="([^"]*Solar-PV-Systems[^"]*\.xlsx)"', html)
    if not match:
        return None
    return urljoin(SOURCES["masscec_pts_page"], match.group(1))


def download_solar_pts() -> Path | None:
    url = find_masscec_solar_download()
    if not url:
        print("warn    MassCEC PTS Excel link was not found")
        return None
    xlsx = download(url, RAW / Path(url).name)
    sheets = pd.ExcelFile(xlsx).sheet_names
    preview = pd.read_excel(xlsx, sheet_name=sheets[0], header=10, nrows=5)
    (RAW / "masscec_pts_columns.txt").write_text(
        "Workbook: " + str(xlsx.name) + "\n"
        + "First sheet: " + str(sheets[0]) + "\n\n"
        + "\n".join(map(str, preview.columns))
        + "\n"
    )

    coord_cols = find_coordinate_columns(list(preview.columns))
    if not coord_cols:
        print("warn    MassCEC PTS file has no obvious latitude/longitude columns in first sheet")
        return None

    lat_col, lon_col = coord_cols
    chunks = pd.read_excel(xlsx, sheet_name=sheets[0])
    chunks = chunks.dropna(subset=[lat_col, lon_col])
    features = []
    for _, row in chunks.iterrows():
        lat = safe_num(row[lat_col])
        lon = safe_num(row[lon_col])
        if math.isnan(lat) or math.isnan(lon):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        props = {str(k): clean_value(v) for k, v in row.items()}
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        )
    out = GEOJSON / "masscec_solar_pts_projects.geojson"
    write_geojson(features, out)
    return out


def download_solar_pts_by_municipality(municipalities_path: Path) -> Path | None:
    url = find_masscec_solar_download()
    if not url:
        print("warn    MassCEC PTS Excel link was not found")
        return None
    xlsx = download(url, RAW / Path(url).name)
    df = pd.read_excel(xlsx, sheet_name="PvinPTSwebsite", header=10)
    df = df.dropna(subset=["City"])
    df["town_key"] = df["City"].map(normalize_town)
    df["capacity_dc_kw"] = pd.to_numeric(df["Capacity \n(DC, kW)"], errors="coerce")
    df["estimated_annual_production_kwh"] = pd.to_numeric(
        df["Estimated Annual Production (kWhr)"], errors="coerce"
    )
    df["is_residential"] = (
        df["Facility Type"].astype(str).str.contains("Residential", case=False, na=False)
    )

    municipalities = load_geojson(municipalities_path)
    town_keys = {
        normalize_town(feature["properties"].get("TOWN")) for feature in municipalities["features"]
    }
    gb = df[df["town_key"].isin(town_keys)]
    grouped = gb.groupby("town_key").agg(
        solar_project_count=("town_key", "size"),
        solar_capacity_dc_kw=("capacity_dc_kw", "sum"),
        estimated_annual_production_kwh=("estimated_annual_production_kwh", "sum"),
        residential_solar_project_count=("is_residential", "sum"),
    )
    grouped["solar_capacity_dc_mw"] = grouped["solar_capacity_dc_kw"] / 1000
    grouped = grouped.reset_index()

    csv_path = RAW / "greater_boston_solar_pts_by_municipality.csv"
    grouped.to_csv(csv_path, index=False)
    print(f"wrote   {csv_path} ({len(grouped):,} rows)")

    lookup = grouped.set_index("town_key").to_dict("index")
    for feature in municipalities["features"]:
        town_key = normalize_town(feature["properties"].get("TOWN"))
        feature["properties"].update(
            lookup.get(
                town_key,
                {
                    "solar_project_count": 0,
                    "solar_capacity_dc_kw": 0,
                    "estimated_annual_production_kwh": 0,
                    "residential_solar_project_count": 0,
                    "solar_capacity_dc_mw": 0,
                },
            )
        )

    out = GEOJSON / "greater_boston_solar_pts_by_municipality.geojson"
    municipalities = clean_json_value(municipalities)
    out.write_text(json.dumps(municipalities, separators=(",", ":"), allow_nan=False))
    print(f"wrote   {out} ({len(municipalities['features']):,} features)")
    return out


def find_coordinate_columns(columns: list[str]) -> tuple[str, str] | None:
    lower = {str(col).lower().strip(): col for col in columns}
    lat = next((lower[key] for key in lower if key in {"lat", "latitude", "y"}), None)
    lon = next((lower[key] for key in lower if key in {"lon", "long", "longitude", "x"}), None)
    if lat and lon:
        return lat, lon
    return None


def clean_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def clean_json_value(value):
    if isinstance(value, dict):
        return {key: clean_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [clean_json_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_manifest(outputs: list[Path]) -> None:
    manifest = {
        "study_area": "Greater Boston approximation: Essex, Middlesex, Norfolk, Plymouth, and Suffolk counties.",
        "created_outputs": [str(path.relative_to(ROOT)) for path in outputs if path],
        "sources": SOURCES,
        "notes": [
            "ACS variables were downloaded from Census Reporter because the Census API required a key in this environment.",
            "DOE LEAD 2022 is not downloaded by default because the official Zenodo archive is approximately 7.8 GB.",
            "MassCEC PTS is downloaded as the official Excel file. Because it does not include project coordinates, the script creates a municipality-level GeoJSON summary.",
            "MOR-EV and Mass Save are not included here because their public data are generally ZIP/town-level rather than tract-level GeoJSON.",
        ],
    }
    path = DATA / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    print(f"wrote   {path}")


def main() -> int:
    ensure_dirs()
    outputs = []
    tracts = download_tract_boundaries()
    outputs.append(tracts)
    acs = download_acs()
    tracts_acs = join_acs_to_tracts(tracts, acs)
    outputs.append(tracts_acs)
    outputs.append(download_svi_and_join(tracts_acs))
    outputs.append(download_ej())
    municipalities, greater_boston_towns = download_municipalities()
    outputs.append(municipalities)
    outputs.append(download_ev_chargers(greater_boston_towns))
    outputs.append(download_solar_pts())
    outputs.append(download_solar_pts_by_municipality(municipalities))
    write_manifest(outputs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
