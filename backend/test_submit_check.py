#!/usr/bin/env python3
"""Check if submit comment is stored anywhere accessible."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.dataworks_client import resolve_project_id, query_task, _get_wrapper
from alibabacloud_dataworks_public20240518 import models as dw_models
import json

schema = "nemo_vidmate_sg_project"
table_name = "dwr_spock_test2_1d"

project_id = resolve_project_id(schema)
task = query_task(schema, table_name)
file_id = task.get("file_id")

wrapper = _get_wrapper()

# Try to get the latest committed file detail
print("=== Checking GetIDEEventDetail for commit info ===")
try:
    # This API might show commit details
    req = dw_models.GetIDEEventDetailRequest(
        project_id=project_id,
        file_id=file_id,
    )
    response = wrapper._call(wrapper.client.get_ide_event_detail, req)
    data = response.to_map().get("body", {})
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str)[:3000])
except Exception as e:
    print(f"GetIDEEventDetail failed: {e}")

# Also try GetDeploymentPackage to see if comment appears there
print("\n=== Checking recent deployments ===")
try:
    req = dw_models.ListDeploymentPackagesRequest(
        project_id=project_id,
        page_number=1,
        page_size=10,
    )
    response = wrapper._call(wrapper.client.list_deployment_packages, req)
    data = response.to_map().get("body", {})
    pkgs = data.get("Data", {}).get("DeploymentPackages", []) if isinstance(data, dict) else []
    for pkg in pkgs[:3]:
        print(f"  Package: {pkg.get('PackageName')}, Status: {pkg.get('Status')}, "
              f"Comment: {pkg.get('Comment')}")
except Exception as e:
    print(f"ListDeploymentPackages failed: {e}")
