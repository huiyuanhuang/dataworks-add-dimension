#!/usr/bin/env python3
"""Test script for DataWorks submit_file functionality."""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.dataworks_client import (
    resolve_project_id,
    query_task,
    submit_file,
)

def main():
    schema = "nemo_vidmate_sg_project"
    table_name = "dwr_spock_test2_1d"
    comment = "测试提交"

    print(f"🔍 Looking up project_id for schema: {schema}")
    project_id = resolve_project_id(schema)
    if not project_id:
        print(f"❌ Failed to resolve project_id for '{schema}'")
        return
    print(f"✅ project_id = {project_id}")

    print(f"\n🔍 Querying file for table: {table_name}")
    task = query_task(schema, table_name)
    if not task.get("found"):
        print(f"❌ Failed to find file: {task.get('error')}")
        return

    file_id = task.get("file_id")
    node_id = task.get("node_id")
    print(f"✅ file_id = {file_id}")
    print(f"✅ node_id = {node_id}")

    print(f"\n📤 Submitting file with comment: '{comment}'")
    result = submit_file(
        project_id=project_id,
        file_id=file_id,
        comment=comment,
    )

    print(f"\n📋 Result:")
    print(f"  success: {result['success']}")
    if result.get('error'):
        print(f"  error: {result['error']}")
    else:
        print(f"  ✅ Submitted successfully!")

if __name__ == "__main__":
    main()
