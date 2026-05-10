#!/usr/bin/env python3
"""Simple test to verify LLM API works."""

import os
import sys

# Load env from .env file
from pathlib import Path
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

# Now test
from services.llm_client import llm_analyze

try:
    result = llm_analyze(
        sql="SELECT cou, ver, cha FROM dwr_spock_test2_1d",
        dimension_name="gender",
        dimension_chinese_name="性别"
    )
    print("✅ LLM analyze success!")
    print(f"Expansion type: {result.get('expansion_type')}")
    print(f"Upstream tables: {len(result.get('upstream_tables', []))}")
    print(f"Issues: {result.get('issues', [])}")
except Exception as e:
    print(f"❌ LLM analyze failed: {e}")
    import traceback
    traceback.print_exc()
