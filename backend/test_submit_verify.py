#!/usr/bin/env python3
"""Verify that the submit comment was actually saved."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.dataworks_client import resolve_project_id, query_task, _get_wrapper
from alibabacloud_dataworks_public20240518 import models as dw_models

schema = "nemo_vidmate_sg_project"
table_name = "dwr_spock_test2_1d"

project_id = resolve_project_id(schema)
task = query_task(schema, table_name)
file_id = task.get("file_id")

print(f"project_id: {project_id}")
print(f"file_id: {file_id}")

# List file versions to see if comment appears
wrapper = _get_wrapper()
try:
    req = dw_models.ListFileVersionsRequest(
        project_id=project_id,
        file_id=file_id,
        page_number=1,
        page_size=10,
    )
    response = wrapper._call(wrapper.client.list_file_versions, req)
    data = response.to_map().get("body", {})
    print(f"\n=== File Versions Response ===")
    print(f"Keys: {list(data.keys())}")
    
    # Try to extract version list
    versions = data.get("Data", {}).get("FileVersions", []) if isinstance(data, dict) else []
    if not versions:
        versions = data.get("PagingInfo", {}).get("FileVersions", []) if isinstance(data, dict) else []
    
    print(f"\nFound {len(versions)} versions:")
    for v in versions[:5]:
        print(f"  - Version: {v.get('Version')}, Comment: {v.get('Comment')}, "
              f"Creator: {v.get('Creator')}, Time: {v.get('CommitTime')}")
        
except Exception as e:
    print(f"Error listing versions: {e}")
    import traceback
    traceback.print_exc()
