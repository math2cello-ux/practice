# Boston Energy Burden and Clean Energy Access

This repository contains a GitHub Pages-ready website for an environmental
research project on household energy burden and clean energy access in the
Boston area.

## Website

Run a local server from the repository root, then open the research page or map:

```bash
python3 -m http.server 8000
```

- Research page: <http://localhost:8000/index.html>
- Interactive MapLibre map: <http://localhost:8000/map.html>

The local server is required for `map.html` and the D3 analysis because they
load local GeoJSON and CSV files with `fetch`.

## Project Focus

The project asks whether high-energy-burden communities in Greater Boston
receive fewer clean energy infrastructure and adoption benefits after accounting
for income, housing tenure, building type, vehicle access, and neighborhood
characteristics.

## Files

- `index.html` - Main website content.
- `map.html` - Interactive MapLibre map with lazy-loaded research layers.
- `styles.css` - Responsive visual design.
- `scripts/download_research_data.py` - Downloads and converts public research
  datasets to GeoJSON.
- `scripts/build_tract_analysis.py` - Builds the tract analysis CSV and
  optimized map-facing GeoJSON.
- `data/geojson/` - Full generated GeoJSON files used as source data.
- `data/map/` - Smaller GeoJSON files and a manifest used by `map.html`.
- `data/analysis/greater_boston_tract_analysis.csv` - Derived tract analysis
  table used by the D3 chart.
- `README.md` - Project and deployment notes.

## Data Workflow

Download or refresh the public map layers:

```bash
python3 scripts/download_research_data.py
```

Build the tract-level analysis table and map-ready data:

```bash
python3 scripts/build_tract_analysis.py
```

DOE LEAD 2022 is not downloaded automatically because the official archive is
large. Export tract-level Massachusetts data from the DOE LEAD tool or archive,
place it at `data/raw/doe_lead_2022_tracts.csv`, and rerun the analysis script.
The script accepts the LEAD web-tool export where the real header starts after
the metadata rows and joins `Geography ID` to tract `GEOID`.

## GitHub Pages Deployment

1. Push this repository to GitHub.
2. Open the repository settings.
3. Go to **Pages**.
4. Set the source to deploy from the main branch.
5. Choose the root folder and save.
