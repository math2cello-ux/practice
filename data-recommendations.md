# Greater Boston Renewable Energy Equity Dataset Recommendations

This note summarizes recommended datasets for studying the inequitable
distribution of renewable energy resources in Greater Boston and how that
distribution relates to socioeconomic factors.

## Research Focus

The main research question is whether census tracts with higher energy burden
or greater socioeconomic vulnerability have lower access to renewable energy
resources and clean energy adoption benefits.

Recommended primary geography: **Greater Boston census tracts**, preferably
using the MAPC region as the study boundary.

## Core Dataset Stack

### 1. DOE LEAD 2022: Energy Burden

Use this as the main energy affordability dataset. It provides tract-level
estimates for household energy burden, energy costs, income groups, housing
type, heating fuel, and related variables.

Sources:

- DOE LEAD archive: <https://zenodo.org/records/14758685>
- DOE LEAD tool: <https://www.energy.gov/cmei/scep/low-income-energy-affordability-data-lead-tool>

Recommended variables:

- Average household energy burden
- Low-income household energy burden
- Annual household energy cost
- Heating fuel type
- Housing type
- Income category

### 2. ACS 5-Year Census Tract Data: Socioeconomic Controls

Use ACS 5-year data as the main source for census-tract socioeconomic,
demographic, housing, and transportation variables.

Source:

- Census ACS 5-year data: <https://www.census.gov/data/developers/data-sets/acs-5year.html>

Recommended variables:

- Median household income: `B19013`
- Poverty rate: `B17001`
- Race and ethnicity: `B03002`
- Rentership and ownership: `B25003`
- Housing units in structure: `B25024`
- Year structure built: `B25034`
- Vehicle availability: `B25044`
- Gross rent burden: `B25070`
- Homeowner cost burden: `B25091`
- Educational attainment: `B15003`
- Commute mode: `B08301`
- Limited English or language isolation: `B16004`

Use ACS 2018-2022 to align closely with DOE LEAD 2022, or use the newest ACS
5-year release for a current descriptive snapshot.

### 3. NREL AFDC EV Charging Stations

Use this for point-level EV charging infrastructure. Filter to Massachusetts,
public access, open status, Level 2 chargers, and DC fast chargers. Then
spatially join charger points to census tracts.

Source:

- NREL Alternative Fuel Stations API: <https://developer.nrel.gov/docs/transportation/alt-fuel-stations-v1/>

Recommended tract outcomes:

- Public charging stations per tract
- Charging ports per 1,000 households
- DC fast chargers per tract
- Distance from tract centroid to nearest public charger
- Indicator for whether a tract has any public charger

### 4. MassCEC Production Tracking System: Solar PV

Use this for solar adoption in Massachusetts. It includes solar PV systems
registered in the Production Tracking System, with project location and
capacity information.

Source:

- MassCEC Production Tracking System: <https://www.masscec.com/production-tracking-system-pts>

Recommended tract outcomes:

- Solar installations per tract
- Residential solar installations per 1,000 owner-occupied households
- Installed solar capacity per household
- Solar capacity per owner-occupied housing unit

### 5. MassGIS Environmental Justice Populations

Use this for environmental justice context. The data are at the block group
level, so they can be used as an overlay or aggregated/intersected to census
tracts.

Source:

- MassGIS 2020 Environmental Justice Populations: <https://www.mass.gov/info-details/massgis-data-2020-environmental-justice-populations>

Recommended variables:

- Environmental justice designation
- Income-based EJ status
- Minority population EJ status
- English isolation EJ status

### 6. CDC/ATSDR Social Vulnerability Index

Use this as an optional tract-level socioeconomic vulnerability index. It
combines ACS variables into broader vulnerability themes.

Source:

- CDC/ATSDR Social Vulnerability Index: <https://www.atsdr.cdc.gov/place-health/php/svi/index.html>

Recommended variables:

- Overall SVI percentile
- Socioeconomic vulnerability
- Household characteristics
- Minority status and language
- Housing type and transportation vulnerability

## Supplemental Datasets

### 7. MOR-EV Rebate Statistics

Use this as a supplemental EV adoption dataset. Its geography is often ZIP,
county, or municipality rather than census tract, so it should not be the main
tract-level outcome unless a careful crosswalk is used.

Source:

- MOR-EV statistics: <https://mor-ev.org/statistics>

Potential use:

- Compare EV rebate uptake across municipalities or ZIP codes
- Use as supporting evidence for inequitable EV adoption patterns

### 8. Mass Save Data

Use this for heat pump, weatherization, and energy-efficiency program uptake.
This is useful for comparing affordability-oriented programs with EV and solar
adoption.

Source:

- Mass Save Data: <https://www.masssavedata.com/>

Potential use:

- Heat pump adoption
- Weatherization projects
- Energy-efficiency program participation
- Comparison of program uptake in high-burden and low-burden communities

### 9. MassGIS Building Structures and Land Use

Use these datasets to help explain why solar is unequally distributed. They can
capture roof area, building density, multifamily housing patterns, and land-use
constraints.

Sources:

- MassGIS Building Structures: <https://www.mass.gov/info-details/massgis-data-building-structures-2-d>
- MassGIS Land Cover/Land Use: <https://www.mass.gov/info-details/massgis-data-2016-land-coverland-use>

Potential use:

- Estimate rooftop solar suitability
- Identify dense multifamily areas
- Control for land-use and building-form constraints

## Recommended Study Design

Create one Greater Boston census tract dataset with the following structure:

- `GEOID`
- DOE LEAD energy burden variables
- ACS socioeconomic and housing controls
- EV charger counts and nearest-charger distance
- Solar installation count and installed solar capacity
- Environmental justice or SVI indicators

Suggested baseline model:

```text
clean_energy_access =
  energy_burden
  + income
  + rentership
  + multifamily_share
  + vehicle_access
  + race_ethnicity
  + population_density
  + EJ_status
  + municipality_controls
  + error
```

## Best First Analysis

The strongest first version of the project would:

1. Use census tracts as the main geography.
2. Use EV chargers and solar PV as the main clean energy outcomes.
3. Use DOE LEAD and ACS as the main socioeconomic and energy-burden context.
4. Use environmental justice or SVI indicators for equity framing.
5. Treat ZIP-level or town-level datasets such as MOR-EV and Mass Save as
   supplemental evidence rather than forcing them into the tract-level model.

