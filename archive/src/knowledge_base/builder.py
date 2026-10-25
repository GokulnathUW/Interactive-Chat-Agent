"""
Knowledge base builder — orchestrates chunking of all enabled metadata sources
into the Cortex Search staging table and creates the search service.

Entry point: scripts/build_kb.py
This module is safe to re-run; all objects are created with CREATE OR REPLACE.
"""
import os
from snowflake.snowpark import Session
from src.session.snowflake_session import (
    ensure_session_context,
    quotes_identifier,
    SNOWFLAKE_DATA_DATABASE,
    SNOWFLAKE_DATA_SCHEMA,
    SNOWFLAKE_KB_DATABASE,
    SNOWFLAKE_KB_SCHEMA,
)
from src.knowledge_base.sources import METADATA_SOURCES

# Staging table in the KB database; Cortex Search indexes this
CHUNKS_TABLE = "CBG_FIELD_CHUNKS"

CORTEX_SEARCH_SERVICE = os.getenv("CORTEX_SEARCH_SERVICE", "CBG_FIELD_SEARCH")
SNOWFLAKE_WAREHOUSE   = os.getenv("SNOWFLAKE_WAREHOUSE", "")


# ---------------------------------------------------------------------------
# Handler: field_descriptions
# ---------------------------------------------------------------------------

def _format_field_description_row(row: dict, dataset: str) -> tuple:
    """Format one field-description row into (chunk_text, column_name, snowflake_table).

    Example input:
        row     = {"TABLE_ID": "B19013e1", "TABLE_NUMBER": "B19013",
                   "TABLE_TITLE": "Median Household Income In The Past 12 Months",
                   "FIELD_LEVEL_1": "Estimate",
                   "FIELD_LEVEL_2": "Median household income in the past 12 months", ...}
        dataset = "ACS_2020"

    Example output:
        (
          "Column: B19013e1 | Snowflake table: 2020_CBG_B19 | "
          "Topic: Median Household Income In The Past 12 Months | "
          "Estimate > Median household income in the past 12 months",
          "B19013e1",
          "2020_CBG_B19",
        )
    """
    column_name  = row.get("TABLE_ID", "")
    table_number = str(row.get("TABLE_NUMBER", ""))

    snowflake_table = f"2020_CBG_{table_number[:3].upper()}"

    levels = [
        str(row[f"FIELD_LEVEL_{i}"]).strip()
        for i in range(1, 11)
        if row.get(f"FIELD_LEVEL_{i}") and str(row[f"FIELD_LEVEL_{i}"]).strip()
    ]

    chunk_text = (
        f"Column: {column_name} | "
        f"Snowflake table: {snowflake_table} | "
        f"Topic: {row.get('TABLE_TITLE', '')} | "
        f"{' > '.join(levels)}"
    )
    return chunk_text, column_name, snowflake_table


def chunk_field_descriptions(rows: list, dataset: str) -> list:
    chunks = []
    for row in rows:
        chunk_text, column_name, snowflake_table = _format_field_description_row(
            row.as_dict(), dataset
        )
        chunks.append({
            "CHUNK_TEXT":      chunk_text,
            "COLUMN_NAME":     column_name,
            "SNOWFLAKE_TABLE": snowflake_table,
            "DATASET":         dataset,
            "SOURCE_TYPE":     "field_descriptions",
        })
    return chunks


# ---------------------------------------------------------------------------
# Handlers: schema-only chunks (no rows loaded from Snowflake)
# ---------------------------------------------------------------------------

def chunk_fips_codes(table: str, dataset: str) -> list:
    """Create a single schema-description chunk for a FIPS codes table.

    FIPS lookups are done at query time via a SQL JOIN using FIPS prefix
    extraction from CENSUS_BLOCK_GROUP — see SQL_GENERATION_PROMPT for the
    exact join pattern. The KB chunk only advertises the table's existence
    and accurate column semantics for geographic filtering.

    Confirmed schema (5 columns — NO census_block_group column):
        STATE       — 2-char uppercase state abbreviation (e.g. 'TX', 'CA')
        STATE_FIPS  — 2-digit zero-padded string (e.g. '48', '06')
        COUNTY      — county name with "County" suffix (e.g. 'Travis County')
        COUNTY_FIPS — 3-digit zero-padded string (e.g. '453', '037')
        CLASS_CODE  — county class code
    """
    chunk_text = (
        f"Table: {table} | "
        "FIPS geographic lookup table — join to filter by state or county | "
        "STATE: 2-character uppercase state abbreviation (e.g. 'TX', 'CA', 'NY') | "
        "STATE_FIPS: 2-digit zero-padded state FIPS code (e.g. '48', '06') | "
        "COUNTY: county name including 'County' suffix (e.g. 'Travis County', 'Los Angeles County') | "
        "COUNTY_FIPS: 3-digit zero-padded county FIPS code (e.g. '453', '037') | "
        "CLASS_CODE: Census county class code | "
        "NOTE: this table has NO census_block_group column — join via FIPS prefix extraction"
    )
    return [{
        "CHUNK_TEXT":      chunk_text,
        "SNOWFLAKE_TABLE": table,
        "DATASET":         dataset,
        "SOURCE_TYPE":     "fips",
    }]


def chunk_geographic_data(dataset: str) -> list:
    """Create a single schema-description chunk for the CBG geographic reference table.

    Both ACS and redistricting CBGs share the same geographic columns; we always
    point to 2020_METADATA_CBG_GEOGRAPHIC_DATA as the canonical source.

    Columns (from SafeGraph docs): census_block_group, amount_land, amount_water,
    latitude, longitude.
    """
    canonical_table = "2020_METADATA_CBG_GEOGRAPHIC_DATA"
    chunk_text = (
        f"Table: {canonical_table} | "
        "Geographic reference data per Census Block Group | "
        "census_block_group: 12-digit FIPS code (primary key, joins all CBG tables) | "
        "amount_land: land area in square meters | "
        "amount_water: water area in square meters | "
        "latitude: interpolated centroid latitude coordinate | "
        "longitude: interpolated centroid longitude coordinate"
    )
    return [{
        "CHUNK_TEXT":      chunk_text,
        "SNOWFLAKE_TABLE": canonical_table,
        "DATASET":         dataset,
        "SOURCE_TYPE":     "geographic",
    }]


def chunk_geometry(table: str, dataset: str) -> list:
    """Create a single schema-description chunk for a CBG geometry table.

    Geometry tables contain 100k+ rows with large polygon strings — we never
    load them. The SQL generator only needs to know the table exists, its columns,
    and how to join it.

    Confirmed schema for 2020_CBG_GEOMETRY_WKT (9 columns):
        state_fips         — 2-digit state FIPS code
        county_fips        — 5-digit county FIPS code
        tract_code         — census tract code
        block_group        — single-digit block group number within the tract
        census_block_group — 12-digit FIPS code (primary key, joins all CBG tables)
        state              — state name
        county             — county name
        mtfcc              — MAF/TIGER Feature Class Code (Census geographic entity type)
        geometry           — polygon boundary in WKT (Well-Known Text) format
    """
    chunk_text = (
        f"Table: {table} | "
        "CBG polygon boundary geometries in WKT format | "
        "census_block_group: 12-digit FIPS code (primary key, joins all CBG tables) | "
        "state_fips: 2-digit state FIPS | "
        "county_fips: 5-digit county FIPS | "
        "tract_code: census tract code | "
        "block_group: block group digit within tract | "
        "state: state name | "
        "county: county name | "
        "mtfcc: MAF/TIGER Feature Class Code | "
        "geometry: polygon boundary string in WKT format for spatial queries and mapping"
    )
    return [{
        "CHUNK_TEXT":      chunk_text,
        "SNOWFLAKE_TABLE": table,
        "DATASET":         dataset,
        "SOURCE_TYPE":     "geometry",
    }]


def chunk_patterns(table: str, dataset: str) -> list:
    """Create a single schema-description chunk for a CBG foot-traffic patterns table.

    Patterns tables have millions of rows with Variant (JSON) columns — we never
    load them. Source: SafeGraph CBG-level aggregated mobility data.

    Confirmed schema for 2019_CBG_PATTERNS (13 columns):
        census_block_group    — 12-digit FIPS code (primary key, joins all CBG tables)
        date_range_start      — start of the measurement period (monthly)
        date_range_end        — end of the measurement period (monthly)
        raw_visit_count       — total visits to all POIs in this CBG during the period
        raw_visitor_count     — unique visitors to all POIs in this CBG during the period
        visitor_home_cbgs     — JSON {cbg_fips: visitor_count} home origins of visitors
        visitor_work_cbgs     — JSON {cbg_fips: visitor_count} work origins of visitors
        distance_from_home    — median distance (metres) from visitor home to this CBG
        related_same_day_brand  — JSON {brand: count} other brands visited same day
        related_same_month_brand — JSON {brand: count} other brands visited same month
        top_brands            — JSON {brand: count} most-visited brands/POIs in this CBG
        popularity_by_hour    — JSON array[24] visit counts by hour of day (0–23)
        popularity_by_day     — JSON array[7] visit counts by day of week (0=Mon … 6=Sun)
    """
    chunk_text = (
        f"Table: {table} | "
        "SafeGraph CBG-level monthly foot-traffic and mobility data | "
        "census_block_group: 12-digit FIPS code (primary key, joins all CBG tables) | "
        "date_range_start/date_range_end: monthly measurement window | "
        "raw_visit_count: total visits to all POIs in CBG | "
        "raw_visitor_count: unique visitors to all POIs in CBG | "
        "visitor_home_cbgs: JSON map of visitor home CBG FIPS to visitor count | "
        "visitor_work_cbgs: JSON map of visitor work CBG FIPS to visitor count | "
        "distance_from_home: median distance in metres from visitor home to this CBG | "
        "related_same_day_brand: JSON map of brands also visited on same day | "
        "related_same_month_brand: JSON map of brands also visited in same month | "
        "top_brands: JSON map of most-visited brands or POIs within the CBG | "
        "popularity_by_hour: JSON array[24] of visit counts by hour (index 0 = midnight) | "
        "popularity_by_day: JSON array[7] of visit counts by day of week (index 0 = Monday)"
    )
    return [{
        "CHUNK_TEXT":      chunk_text,
        "SNOWFLAKE_TABLE": table,
        "DATASET":         dataset,
        "SOURCE_TYPE":     "patterns",
    }]


def chunk_redistricting_descriptions(rows: list, dataset: str) -> list:
    """Build chunk dicts for 2020_REDISTRICTING_METADATA_CBG_FIELD_DESCRIPTIONS.

    Known schema (4 columns):
        COLUMN_ID       — P/H table code, e.g. P0010001  (→ COLUMN_NAME)
        COLUMN_TOPIC    — high-level topic, e.g. "Race"
        FIELD_NAME      — human-readable label, e.g. "Total"
        COLUMN_UNIVERSE — always "Total Population"; omitted (adds no search signal)

    Example chunk_text:
        "Column: P0010001 | Topic: Race | Total"
    """
    chunks = []
    for row in rows:
        r = row.as_dict()
        column_id    = r.get("COLUMN_ID", "")
        column_topic = r.get("COLUMN_TOPIC", "")
        field_name   = r.get("FIELD_NAME", "")

        chunk_text = (
            f"Column: {column_id} | "
            f"Topic: {column_topic} | "
            f"{field_name}"
        )
        chunks.append({
            "CHUNK_TEXT":      chunk_text,
            "COLUMN_NAME":     column_id,
            "SNOWFLAKE_TABLE": "2020_REDISTRICTING_CBG_DATA",
            "DATASET":         dataset,
            "SOURCE_TYPE":     "redistricting_descriptions",
        })
    return chunks


# ---------------------------------------------------------------------------
# Dispatcher and orchestrator
# ---------------------------------------------------------------------------

ROW_HANDLERS = {
    "field_descriptions":         chunk_field_descriptions,
    "redistricting_descriptions": chunk_redistricting_descriptions,
}


def dispatch_chunks(session: Session, source: dict) -> list:
    """Route a source entry to the correct chunk handler."""
    table   = source["table"]
    dataset = source["dataset"]
    handler = source["handler"]

    print(f"  [{handler}] {table} ...")

    if handler == "data":
        print(f"    Skipped (raw data table, not metadata).")
        return []

    if handler == "fips":
        # No rows needed — LLM JOINs the table at query time; only schema description required
        return chunk_fips_codes(table, dataset)

    if handler == "geographic":
        # No rows needed — static schema chunk from known column definitions
        return chunk_geographic_data(dataset)

    if handler == "geometry":
        # No rows needed — polygon tables are huge; only schema description required
        return chunk_geometry(table, dataset)

    if handler == "patterns":
        # No rows needed — millions of rows with Variant JSON columns; schema only
        return chunk_patterns(table, dataset)

    # Row-based handlers: load all rows then dispatch
    ensure_session_context(session, use_kb=False)
    fqn = (
        f"{quotes_identifier(SNOWFLAKE_DATA_DATABASE)}."
        f"{quotes_identifier(SNOWFLAKE_DATA_SCHEMA)}."
        f"{quotes_identifier(table)}"
    )
    rows = session.sql(f"SELECT * FROM {fqn}").collect()
    print(f"    {len(rows)} rows loaded.")
    return ROW_HANDLERS[handler](rows, dataset)


def _ensure_kb_database_and_schema(session: Session) -> None:
    """Create the KB database and schema if they do not already exist"""

    db_id     = quotes_identifier(SNOWFLAKE_KB_DATABASE)
    schema_id = quotes_identifier(SNOWFLAKE_KB_SCHEMA)

    session.sql(f"CREATE DATABASE IF NOT EXISTS {db_id}").collect()
    session.sql(f"CREATE SCHEMA IF NOT EXISTS {db_id}.{schema_id}").collect()
    print(f"  KB target: {SNOWFLAKE_KB_DATABASE}.{SNOWFLAKE_KB_SCHEMA} (created if absent)")


def build_knowledge_base(session: Session) -> None:
    active = [s for s in METADATA_SOURCES if s["enabled"]]
    print(f"Building knowledge base from {len(active)} enabled sources...\n")

    # --- Step 0: Ensure the KB database and schema exist ---
    _ensure_kb_database_and_schema(session)

    # --- Step 1: Collect chunks from all enabled sources ---
    all_chunks = []
    for source in active:
        chunks = dispatch_chunks(session, source)
        all_chunks.extend(chunks)
    print(f"\n{len(all_chunks)} total chunks built.")

    # Normalize: all dicts must share the same keys before creating a DataFrame.
    # Handlers only set their own columns; missing keys from other handlers become None.
    all_keys = {k for chunk in all_chunks for k in chunk}
    all_chunks = [{k: chunk.get(k) for k in all_keys} for chunk in all_chunks]

    # --- Step 2: Write staging table to KB database ---
    print(f"Writing to {CHUNKS_TABLE}...")
    ensure_session_context(session, use_kb=True)

    chunks_fqn = (
        f"{quotes_identifier(SNOWFLAKE_KB_DATABASE)}."
        f"{quotes_identifier(SNOWFLAKE_KB_SCHEMA)}."
        f"{quotes_identifier(CHUNKS_TABLE)}"
    )
    session.create_dataframe(all_chunks).write.mode("overwrite").save_as_table(chunks_fqn)
    print("  Staging table written.")

    # --- Step 3: Create (or replace) the Cortex Search service ---
    print(f"Creating Cortex Search service '{CORTEX_SEARCH_SERVICE}'...")
    service_fqn = (
        f"{quotes_identifier(SNOWFLAKE_KB_DATABASE)}."
        f"{quotes_identifier(SNOWFLAKE_KB_SCHEMA)}."
        f"{quotes_identifier(CORTEX_SEARCH_SERVICE)}"
    )
    session.sql(f"""
        CREATE OR REPLACE CORTEX SEARCH SERVICE {service_fqn}
          ON CHUNK_TEXT
          WAREHOUSE = {quotes_identifier(SNOWFLAKE_WAREHOUSE)}
          TARGET_LAG = '30 days'
          EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
        AS (
          SELECT CHUNK_TEXT, COLUMN_NAME, SNOWFLAKE_TABLE, DATASET, SOURCE_TYPE
          FROM {chunks_fqn}
        )
    """).collect()
    print(f"  Cortex Search service '{CORTEX_SEARCH_SERVICE}' created.")
