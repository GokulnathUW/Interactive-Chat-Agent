#!/usr/bin/env python3
"""
Builds or rebuilds the Cortex Search knowledge base.

Run from the project root:
    python scripts/build_kb.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.session.snowflake_session import get_session
from src.knowledge_base.builder import build_knowledge_base
from src.knowledge_base.sources import METADATA_SOURCES

# Show enabled sources so you can confirm before anything writes to Snowflake
active = [s for s in METADATA_SOURCES if s["enabled"]]
skipped = [s for s in METADATA_SOURCES if not s["enabled"]]

print("Enabled sources:")
for s in active:
    print(f"  + [{s['handler']:30s}]  {s['table']}")

if skipped:
    print(f"\nSkipped ({len(skipped)}):")
    for s in skipped:
        print(f"  - {s['table']}")

print(f"\n{len(active)} sources will be built. Connecting to Snowflake...\n")

session = get_session()
try:
    build_knowledge_base(session)
    print("\nKnowledge base build complete.")
except Exception as e:
    print(f"\nKnowledge base build failed: {e}")
    raise
finally:
    session.close()
