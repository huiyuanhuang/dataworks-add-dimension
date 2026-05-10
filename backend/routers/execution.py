from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from services.dataworks_client import commit_node, _get_project_id
from services.odps_client import execute_sql, get_table_columns
from services.bi_client import BIClient

router = APIRouter()


# ── Save Draft ────────────────────────────────────────────────

class SaveDraftRequest(BaseModel):
    project_id: str
    file_id: int
    node_id: Optional[str] = None
    sql_content: str
    commit_message: Optional[str] = "通过 Web 工具保存草稿"

class SaveDraftResponse(BaseModel):
    success: bool
    message: str
    node_id: Optional[str] = None

@router.post("/save-draft", response_model=SaveDraftResponse)
def save_draft(req: SaveDraftRequest):
    project_id_int = _get_project_id(req.project_id)
    if not project_id_int:
        return SaveDraftResponse(
            success=False,
            message=f"无法获取项目 '{req.project_id}' 的 DataWorks project_id",
            node_id=req.node_id,
        )

    result = commit_node(project_id_int, req.file_id, req.sql_content, req.commit_message)
    if result["success"]:
        return SaveDraftResponse(
            success=True,
            message=f"草稿保存成功 (project_id={project_id_int}, file_id={req.file_id})",
            node_id=req.node_id,
        )
    else:
        return SaveDraftResponse(
            success=False,
            message=f"保存草稿失败: {result['error'][:500]}",
            node_id=req.node_id,
        )


# ── Alter Table ───────────────────────────────────────────────

class AlterTableRequest(BaseModel):
    project_id: str
    table_name: str
    dimension_name: str
    dimension_chinese_name: Optional[str] = ""
    dimension_type: str = "STRING"

class AlterTableResponse(BaseModel):
    success: bool
    message: str
    sql: str
    output: Optional[str] = None

@router.post("/alter-table", response_model=AlterTableResponse)
def alter_table(req: AlterTableRequest):
    dim_comment = f" COMMENT '{req.dimension_chinese_name}'" if req.dimension_chinese_name else ""
    sql = f"ALTER TABLE {req.table_name} ADD COLUMNS ({req.dimension_name} {req.dimension_type}{dim_comment});"

    result = execute_sql(req.project_id, sql)

    if result["success"]:
        return AlterTableResponse(
            success=True,
            message="ALTER TABLE 执行成功",
            sql=sql,
            output=result.get("output", "")[:500],
        )
    else:
        return AlterTableResponse(
            success=False,
            message=f"ALTER TABLE 执行失败: {result['error'][:500]}",
            sql=sql,
            output=result.get("error", "")[:500],
        )


# ── Generate Backfill ────────────────────────────────────────

class BackfillRequest(BaseModel):
    project_id: str
    table_name: str
    dimension_name: str
    start_dt: str
    end_dt: Optional[str] = None

class BackfillResponse(BaseModel):
    sql: str
    estimated_partitions: int
    message: str

def _format_date(dt_str: str) -> str:
    """Convert 'YYYY-MM-DD' or 'YYYYMMDD' to 'YYYYMMDD'."""
    s = dt_str.strip()
    if len(s) == 8 and s.isdigit():
        return s
    if len(s) == 10 and s[4] == '-' and s[7] == '-':
        return s[:4] + s[5:7] + s[8:10]
    return s

def _calculate_partitions(start_dt: str, end_dt: str) -> int:
    """Calculate number of days between two dates (YYYYMMDD, inclusive)."""
    try:
        start = datetime.strptime(start_dt, "%Y%m%d")
        end_date = datetime.strptime(end_dt, "%Y%m%d")
        return max((end_date - start).days + 1, 0)
    except ValueError:
        return 0

@router.post("/generate-backfill", response_model=BackfillResponse)
def generate_backfill(req: BackfillRequest):
    start_dt = _format_date(req.start_dt)
    end_dt = _format_date(req.end_dt or req.start_dt)

    # Get actual table columns from DDL
    columns_result = get_table_columns(req.table_name, default_project=req.project_id)
    if columns_result.get("error"):
        return BackfillResponse(
            sql="",
            estimated_partitions=0,
            message=f"无法获取表结构: {columns_result['error']}",
        )

    columns = columns_result.get("columns", [])
    if not columns:
        return BackfillResponse(
            sql="",
            estimated_partitions=0,
            message="无法获取表结构（列数为0）",
        )

    # Generate SELECT column list
    # For dynamic partition INSERT OVERWRITE TABLE ... PARTITION (dt),
    # the partition column 'dt' must be the LAST column in the SELECT list.
    # The new dimension column should be placed in the second-to-last position
    # (just before 'dt').
    other_cols = [c for c in columns if c.lower() != 'dt']
    dt_present = any(c.lower() == 'dt' for c in columns)

    select_columns = []
    for col in other_cols:
        select_columns.append(f"  {col}")

    # Add the new dimension column (if not already present) before dt
    if req.dimension_name not in columns:
        select_columns.append(f"  'ALL' AS {req.dimension_name}")

    # dt must be the last column for dynamic partition to work
    if dt_present:
        select_columns.append(f"  dt")

    # Build SQL
    col_sql = ",\n".join(select_columns)
    sql = f"""INSERT OVERWRITE TABLE {req.table_name} PARTITION (dt)
SELECT
{col_sql}
FROM {req.table_name}
WHERE dt >= '{start_dt}' AND dt <= '{end_dt}'"""

    estimated_partitions = _calculate_partitions(start_dt, end_dt)

    return BackfillResponse(
        sql=sql,
        estimated_partitions=estimated_partitions,
        message="回刷 SQL 已生成",
    )


# ── Execute Backfill ────────────────────────────────────────

class ExecuteBackfillRequest(BaseModel):
    project_id: str
    table_name: str
    dimension_name: str
    sql: str

class ExecuteBackfillResponse(BaseModel):
    success: bool
    message: str
    output: Optional[str] = None

@router.post("/execute-backfill", response_model=ExecuteBackfillResponse)
def execute_backfill(req: ExecuteBackfillRequest):
    result = execute_sql(req.project_id, req.sql)

    if result["success"]:
        return ExecuteBackfillResponse(
            success=True,
            message="回刷 SQL 执行成功",
            output=result.get("output", "")[:500],
        )
    else:
        return ExecuteBackfillResponse(
            success=False,
            message=f"回刷 SQL 执行失败: {result['error'][:500]}",
            output=result.get("error", "")[:500],
        )


# ── Sync BI ──────────────────────────────────────────────────

class SyncBIRequest(BaseModel):
    table_name: str
    dimension_name: str
    dimension_chinese_name: Optional[str] = ""
    application_code: Optional[str] = None
    expansion_type: Optional[str] = "unknown"

class SyncBIResponse(BaseModel):
    success: bool
    chart_code: Optional[str] = None
    message: str
    steps_detail: Optional[dict] = None

@router.post("/sync-bi", response_model=SyncBIResponse)
def sync_bi(req: SyncBIRequest):
    try:
        client = BIClient()
        result = client.sync_dimension(
            table_name=req.table_name,
            dimension_name=req.dimension_name,
            dimension_chinese_name=req.dimension_chinese_name,
            app_code=req.application_code,
            expansion_type=req.expansion_type,
        )
        return SyncBIResponse(
            success=result["success"],
            chart_code=None,
            message=result["message"],
            steps_detail=result.get("steps_detail"),
        )
    except Exception as e:
        return SyncBIResponse(
            success=False,
            chart_code=None,
            message=f"BI 同步异常: {str(e)}",
            steps_detail=None,
        )

# ── Submit File ───────────────────────────────────────────────

class SubmitFileRequest(BaseModel):
    project_id: str
    file_id: int
    comment: str = "自动提交"

class SubmitFileResponse(BaseModel):
    success: bool
    message: str
    file_id: Optional[int] = None

@router.post("/submit-file", response_model=SubmitFileResponse)
def submit_file_endpoint(req: SubmitFileRequest):
    from services.dataworks_client import submit_file, _get_project_id

    project_id_int = _get_project_id(req.project_id)
    if not project_id_int:
        return SubmitFileResponse(
            success=False,
            message=f"无法获取项目 '{req.project_id}' 的 DataWorks project_id",
        )

    result = submit_file(project_id_int, req.file_id, req.comment)
    if result["success"]:
        return SubmitFileResponse(
            success=True,
            message="代码提交成功",
            file_id=req.file_id,
        )
    else:
        return SubmitFileResponse(
            success=False,
            message=result["error"],
            file_id=req.file_id,
        )
