#!/usr/bin/env python3
"""Detailed test of submit_file with full response inspection."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.dataworks_client import resolve_project_id, query_task, _get_wrapper
from alibabacloud_dataworks_public20240518 import models as dw_models

schema = "nemo_vidmate_sg_project"
table_name = "dwr_spock_test2_1d"
comment = "测试提交备注2025"

project_id = resolve_project_id(schema)
task = query_task(schema, table_name)
file_id = task.get("file_id")

print(f"project_id: {project_id}")
print(f"file_id: {file_id}")

wrapper = _get_wrapper()

# Check the raw request being built
req = dw_models.SubmitFileRequest(
    project_id=project_id,
    file_id=file_id,
    comment=comment,
)

print(f"\n=== Request object attributes ===")
print(f"  comment: '{req.comment}'")
print(f"  file_id: {req.file_id}")
print(f"  project_id: {req.project_id}")

# Now make the actual call and inspect response
print(f"\n📤 Submitting with comment: '{comment}'")
try:
    response = wrapper._call(wrapper.client.submit_file, req)
    full_data = response.to_map()
    print(f"\n=== Full Response ===")
    import json
    print(json.dumps(full_data, indent=2, ensure_ascii=False, default=str))
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
