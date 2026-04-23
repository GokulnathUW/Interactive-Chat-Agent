"""
Registry of all SafeGraph/Census source tables for the knowledge base.

Each entry declares:
  table   — Snowflake table name in the data database
  handler — which chunk builder to use (see builder.py)
  dataset — label attached to every chunk so the LLM knows provenance
  enabled — whether to include in the current KB build

Set enabled=False to exclude a table without removing it from the registry.
Handler types:
  field_descriptions          — ACS column-name → description mapping (TABLE_ID, TABLE_NUMBER, FIELD_LEVEL_*)
  redistricting_descriptions  — Redistricting column descriptions (different schema from ACS)
  fips                        — state/county name → FIPS code lookup
  geographic                  — per-CBG land area, water area, lat/long (reference data, not schema)
  geometry                    — polygon geometry (WKT/GeoJSON)
  patterns                    — SafeGraph foot-traffic mobility data
"""

METADATA_SOURCES = [
    # ------------------------------------------------------------------ ACS 2020
    {
        "table":   "2020_METADATA_CBG_FIELD_DESCRIPTIONS",
        "handler": "field_descriptions",
        "dataset": "ACS_2020",
        "enabled": True,
    },
    {
        "table":   "2020_METADATA_CBG_FIPS_CODES",
        "handler": "fips",
        "dataset": "FIPS_2020",
        "enabled": True,
    },
    {
        "table":   "2020_METADATA_CBG_GEOGRAPHIC_DATA",
        "handler": "geographic",
        "dataset": "GEO_2020",
        "enabled": True,
    },

    # ------------------------------------------------------------------ ACS 2019
    {
        "table":   "2019_METADATA_CBG_FIELD_DESCRIPTIONS",
        "handler": "field_descriptions",
        "dataset": "ACS_2019",
        "enabled": False,
    },
    {
        "table":   "2019_METADATA_CBG_FIPS_CODES",
        "handler": "fips",
        "dataset": "FIPS_2019",
        "enabled": False,  # FIPS codes do not change year-to-year; 2020 is sufficient
    },
    {
        "table":   "2019_METADATA_CBG_GEOGRAPHIC_DATA",
        "handler": "geographic",
        "dataset": "GEO_2019",
        "enabled": False,  # Redundant with 2020 geographic data
    },

    # ------------------------------------------------------- Redistricting 2020
    {
        "table":   "2020_REDISTRICTING_METADATA_CBG_FIELD_DESCRIPTIONS",
        "handler": "redistricting_descriptions",
        "dataset": "REDISTRICTING_2020",
        "enabled": True,
    },
    {
        "table":   "2020_REDISTRICTING_METADATA_CBG_GEOGRAPHIC_DATA",
        "handler": "data",
        "dataset": "REDISTRICTING_GEO_2020",
        "enabled": False,  # Reference data (land area, lat/lon), not a schema description
    },

    # ----------------------------------------------------------------- Geometry
    {
        "table":   "2019_CBG_GEOMETRY",
        "handler": "geometry",
        "dataset": "GEOMETRY_2019",
        "enabled": False,  # Older vintage; 2020_CBG_GEOMETRY_WKT aligns with all 2020 datasets
    },
    {
        "table":   "2019_CBG_GEOMETRY_WKT",
        "handler": "geometry",
        "dataset": "GEOMETRY_WKT_2019",
        "enabled": False,  # Redundant with 2019_CBG_GEOMETRY; WKT and GeoJSON cover same shapes
    },
    {
        "table":   "2020_CBG_GEOMETRY_WKT",
        "handler": "geometry",
        "dataset": "GEOMETRY_WKT_2020",
        "enabled": True,
    },

    # ----------------------------------------------------------------- Patterns
    {
        "table":   "2019_CBG_PATTERNS",
        "handler": "patterns",
        "dataset": "PATTERNS_2019",
        "enabled": True,
    },
]
