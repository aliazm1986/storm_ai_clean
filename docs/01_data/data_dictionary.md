# Data Dictionary

This file will be updated step by step.

## Required Identity Fields

- `File ID`: official STORM-AI sample identifier.
- `id`: internal row-level identifier created during preprocessing.
- `satellite`: satellite/platform name if available or inferable.
- `datetime`: Canonical timestamp value; source timezone is not confirmed.
- `time`: Canonical time representation derived after timestamp review.

Timezone status: `UTC assumed; source confirmation pending`. Do not convert
timezone-naive source values or label them UTC without source documentation.

## Required Density / Geospatial Fields

- `Orbit Mean Density (kg/m^3)`: official orbit-mean thermospheric density target.
- `longitude`: geodetic longitude; source not yet identified.
- `latitude`: geodetic latitude; source not yet identified.
- `altitude`: satellite altitude; source not yet identified.

These geospatial fields must not be fabricated or inferred from filenames.

## Space Weather Fields

To be added after density + geospatial validation:
- OMNI2 fields
- GOES fields
- geomagnetic indices
- solar indices
