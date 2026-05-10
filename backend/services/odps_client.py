"""ODPS (MaxCompute) client — replaces subprocess calls to run_odps_sql.py"""

import json
import os
import logging
import re
from pathlib import Path

try:
    from odps import ODPS
    _PYODPS_AVAILABLE = True
except ImportError:
    _PYODPS_AVAILABLE = False
    ODPS = None

logger = logging.getLogger("odps_client")

ACCESS_ID = os.environ.get("DATAWORK_ACCESS_ID", "")
ACCESS_KEY = os.environ.get("DATAWORK_ACCESS_KEY", "")

# Regional ODPS endpoints — keyed by Alibaba Cloud region ID.
# Use ODPS_ENDPOINT env var to override, or ODPS_REGION to pick from this map.
REGION_ENDPOINTS = {
    "cn-hangzhou": "http://service.cn-hangzhou.maxcompute.aliyun.com/api",
    "cn-shanghai": "http://service.cn-shanghai.maxcompute.aliyun.com/api",
    "cn-beijing": "http://service.cn-beijing.maxcompute.aliyun.com/api",
    "cn-shenzhen": "http://service.cn-shenzhen.maxcompute.aliyun.com/api",
    "ap-southeast-1": "https://service.ap-southeast-1.maxcompute.aliyun.com/api",
    "ap-southeast-5": "http://service.ap-southeast-5.maxcompute.aliyun.com/api",
    "us-west-1": "http://service.us-west-1.maxcompute.aliyun.com/api",
}

# Derive ODPS endpoint: explicit env var > region-based lookup > fallback
DATAWORKS_REGION = os.environ.get("DATAWORK_REGION_ID", os.environ.get("ALIBABA_CLOUD_REGION_ID", ""))
ODPS_ENDPOINT = (
    os.environ.get("ODPS_ENDPOINT", "")
    or REGION_ENDPOINTS.get(DATAWORKS_REGION, "")
    or REGION_ENDPOINTS["ap-southeast-1"]  # default matches DataWorks region in this project
)


def create_odps_connection(project: str) -> ODPS:
    logger.info(f"Connecting to ODPS project '{project}' at endpoint '{ODPS_ENDPOINT}'")
    return ODPS(ACCESS_ID, ACCESS_KEY, project, ODPS_ENDPOINT)


# ── Upstream table project resolution ──────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_MAP_PATH = SCRIPT_DIR.parent / "references" / "schema_project_map.json"

# Pattern to extract the business keyword from a table name
# e.g., dwd_spock_install_sd_1d → spock, dwr_vidmate_test2_1d → vidmate
_TABLE_BIZ_RE = re.compile(r'^(?:ods|dwd|dwr|dws|dim)_([a-z]+)_')


def _load_schema_map() -> dict:
    """Load the schema → project_id mapping from config."""
    if SCHEMA_MAP_PATH.exists():
        return json.loads(SCHEMA_MAP_PATH.read_text(encoding="utf-8"))
    return {}


def resolve_odps_project_for_table(table_name: str, default_project: str = "") -> str:
    """Resolve the correct ODPS project for an upstream table.

    Upstream tables may be in different ODPS projects than the target table.
    For example, dwd_spock_install_sd_1d is in nemo_spock_sg_project,
    not in nemo_vidmate_sg_project (the target table's project).

    Resolution strategy:
    1. If table_name includes a project prefix (project.table), use it.
    2. Extract the business keyword (e.g., "spock" from dwd_spock_xxx_1d)
       and find the matching project name in schema_project_map.json
       (e.g., "spock" → nemo_spock_sg_project).
    3. Fall back to default_project.
    """
    # 1. Explicit project prefix
    project_part, pure_table = _parse_table_reference(table_name)
    if project_part:
        return project_part

    # 2. Business keyword lookup
    biz_match = _TABLE_BIZ_RE.match(pure_table)
    if biz_match:
        biz_keyword = biz_match.group(1)
        schema_map = _load_schema_map()
        # Find the project name containing this business keyword
        # e.g., biz="spock" → match "nemo_spock_sg_project"
        for schema_name in schema_map:
            if biz_keyword in schema_name:
                logger.info(
                    f"Resolved ODPS project for table '{table_name}': "
                    f"'{schema_name}' (matched biz keyword '{biz_keyword}')"
                )
                return schema_name

    # 3. Fallback
    logger.info(
        f"Could not resolve ODPS project for table '{table_name}', "
        f"using default '{default_project}'"
    )
    return default_project


def execute_sql(project: str, sql: str) -> dict:
    """Execute ODPS SQL and return {success, output, error}."""
    try:
        o = create_odps_connection(project)
        instance = o.execute_sql(sql)
        instance.wait_for_success()

        # Get results
        results = []
        try:
            with instance.open_reader() as reader:
                for record in reader:
                    results.append(dict(record))
        except Exception:
            # Some SQL (like ALTER TABLE) may not produce readable results
            pass

        output = str(results[:10]) if results else "SQL executed successfully (no output rows)"
        logger.info(f"ODPS SQL executed successfully in project '{project}'")
        return {"success": True, "output": output, "error": None}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"ODPS SQL execution failed: {error_msg[:200]}")
        return {"success": False, "output": None, "error": error_msg[:500]}


def _parse_table_reference(table_name: str) -> tuple:
    """Parse an ODPS table reference into (project, table).

    Supports: 'table', 'project.table', 'project.schema.table'.
    Returns (project_or_None, pure_table_name).
    """
    parts = table_name.strip().replace('`', '').split('.')
    if len(parts) == 1:
        return (None, parts[0])
    if len(parts) == 2:
        return (parts[0], parts[1])
    # project.schema.table
    return (parts[0], parts[2])


def check_column_in_table(table_name: str, column_name: str,
                          default_project: str = "") -> dict:
    """Check whether a column exists in an ODPS table's DDL schema.

    Args:
        table_name: ODPS table reference (may include project prefix).
        column_name: Column name to look for.
        default_project: Project to use if table_name doesn't include one.

    Returns:
        {"exists": bool, "columns": [str], "project": str, "table": str, "error": str|None}
    """
    # Resolve project: try user's selected project FIRST, fallback to schema-mapped
    project_part, pure_table = _parse_table_reference(table_name)
    if project_part:
        projects_to_try = [project_part]
    else:
        # Default to user's selected project first
        mapped = resolve_odps_project_for_table(table_name, default_project)
        # deduplicate while preserving order
        if mapped == default_project:
            projects_to_try = [default_project]
        else:
            projects_to_try = [default_project, mapped]
    # Remove empty/None entries
    projects_to_try = [p for p in projects_to_try if p]

    for project in projects_to_try:
        if not project:
            continue
        try:
            o = create_odps_connection(project)
            odps_table = o.get_table(pure_table)
            # Load schema to ensure columns are fetched
            odps_table.schema.load()
            col_names = [c.name for c in odps_table.schema.columns]

            # Case-insensitive comparison (ODPS column names are lowercase)
            exists = column_name.lower() in [c.lower() for c in col_names]

            logger.info(
                f"DDL check: column '{column_name}' in table '{project}.{pure_table}' "
                f"→ exists={exists} (columns: {col_names[:20]}...)"
            )
            return {
                "exists": exists,
                "columns": col_names,
                "project": project,
                "table": pure_table,
                "error": None,
            }
        except Exception as e:
            error_msg = str(e)[:300]
            logger.warning(f"DDL check failed for '{project}.{pure_table}': {error_msg}")
            # If this is the fallback attempt (user's project), return the error
            if project == default_project or project == projects_to_try[-1]:
                return {
                    "exists": False,
                    "columns": [],
                    "project": project,
                    "table": pure_table,
                    "error": error_msg,
                }
            # Otherwise, continue trying the next project

    return {
        "exists": False,
        "columns": [],
        "project": "",
        "table": pure_table,
        "error": f"无法确定表 '{table_name}' 所属的项目，请提供 default_project",
    }

def get_table_columns(table_name: str, default_project: str = "") -> dict:
    """Get all column names from an ODPS table's DDL schema.

    Args:
        table_name: ODPS table reference (may include project prefix).
        default_project: Project to use if table_name doesn't include one.

    Returns:
        {"columns": [str], "project": str, "table": str, "error": str|None}
    """
    project_part, pure_table = _parse_table_reference(table_name)
    if project_part:
        projects_to_try = [project_part]
    else:
        mapped = resolve_odps_project_for_table(table_name, default_project)
        if mapped == default_project:
            projects_to_try = [default_project]
        else:
            projects_to_try = [default_project, mapped]
    projects_to_try = [p for p in projects_to_try if p]

    for project in projects_to_try:
        if not project:
            continue
        try:
            o = create_odps_connection(project)
            odps_table = o.get_table(pure_table)
            odps_table.schema.load()
            col_names = [c.name for c in odps_table.schema.columns]

            logger.info(
                f"Get columns: table '{project}.{pure_table}' → {len(col_names)} columns"
            )
            return {
                "columns": col_names,
                "project": project,
                "table": pure_table,
                "error": None,
            }
        except Exception as e:
            error_msg = str(e)[:300]
            logger.warning(f"Get columns failed for '{project}.{pure_table}': {error_msg}")
            if project == default_project or project == projects_to_try[-1]:
                return {
                    "columns": [],
                    "project": project,
                    "table": pure_table,
                    "error": error_msg,
                }

    return {
        "columns": [],
        "project": "",
        "table": pure_table,
        "error": f"无法确定表 '{table_name}' 所属的项目，请提供 default_project",
    }
