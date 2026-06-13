# Research Data Outputs

This folder is for downloaded and converted datasets used to visualize
renewable energy access, energy burden, and socioeconomic conditions in Greater
Boston.

Run the downloader:

```bash
python3 scripts/download_research_data.py
```

The script writes GeoJSON files to `data/geojson/` and source downloads or CSV
tables to `data/raw/`.

## GeoJSON Outputs

- `geojson/greater_boston_tracts.geojson` - Census tract boundaries.
- `geojson/greater_boston_tracts_acs.geojson` - Tracts joined with ACS
  socioeconomic variables.
- `geojson/greater_boston_tracts_acs_svi.geojson` - Tracts joined with ACS and
  CDC Social Vulnerability Index variables.
- `geojson/greater_boston_ej_blockgroups.geojson` - MassGIS 2020
  Environmental Justice block groups.
- `geojson/greater_boston_municipalities.geojson` - Municipality boundaries for
  the county-based Greater Boston study area.
- `geojson/greater_boston_ev_charging_stations.geojson` - EV charging stations
  in Greater Boston.
- `geojson/massachusetts_ev_charging_stations.geojson` - Statewide
  Massachusetts EV charging stations.
- `geojson/greater_boston_solar_pts_by_municipality.geojson` - MassCEC PTS solar
  adoption summarized by municipality.

## Study Area

The script currently uses a county-based Greater Boston approximation:

- Essex County
- Middlesex County
- Norfolk County
- Plymouth County
- Suffolk County

This is broader than the MAPC region, but it is easy to filter with county FIPS
codes and works well for an initial exploratory map.

## Important Notes

- DOE LEAD 2022 is not downloaded automatically because the official archive is
  about 7.8 GB.
- MassCEC PTS solar data are downloaded as the official Excel file. A GeoJSON is
  created only if the workbook contains obvious latitude and longitude columns.
- MOR-EV and Mass Save are not included in this first pipeline because their
  public data are usually ZIP/town-level rather than census-tract GeoJSON.
- ACS tract socioeconomic variables are accessed through Census Reporter because
  the Census API required a key in this environment.
