"""Downstream node handling — filter condition and dimension addition."""

import re
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List

from services.dataworks_client import query_task, commit_node, _get_project_id, resolve_project_id, _get_wrapper

logger = logging.getLogger("downstream")
router = APIRouter()


# ── Diff line model ───────────────────────────────────────────

class DiffLine(BaseModel):
    type: str  # "added", "removed", "unchanged"
    line_num: int
    content: str


# ── Modify downstream filter ────────────────────────────────

class ModifyDownstreamFilterRequest(BaseModel):
    project_id: str
    node_id: str
    dimension_name: str


class ModifyDownstreamFilterResponse(BaseModel):
    success: bool
    message: str
    modified_sql: Optional[str] = None
    original_sql: Optional[str] = None
    diff_lines: Optional[List[dict]] = None


@router.post("/modify-downstream-filter", response_model=ModifyDownstreamFilterResponse)
def modify_downstream_filter(req: ModifyDownstreamFilterRequest):
    """Add a WHERE filter to downstream SQL to exclude ALL dimension rows."""
    try:
        # Step 1: Get the downstream node's SQL via node_id
        task_data = _query_task_by_node_id(req.project_id, req.node_id)
        if not task_data.get("found"):
            return ModifyDownstreamFilterResponse(
                success=False,
                message=task_data.get("error", "无法获取下游节点 SQL"),
            )

        original_sql = task_data["code"]
        file_id = task_data.get("file_id")
        project_id_int = _get_project_id(req.project_id)

        # Step 2: Modify the SQL to add filter condition
        modified_sql = _add_where_filter(original_sql, req.dimension_name)
        if modified_sql == original_sql:
            return ModifyDownstreamFilterResponse(
                success=False,
                message="无法在 SQL 中添加过滤条件（可能已存在或结构不支持）",
                original_sql=original_sql,
            )

        # Step 3: Save to DataWorks
        if file_id and project_id_int:
            result = commit_node(
                project_id_int,
                file_id,
                modified_sql,
                f"自动加维度: 下游过滤 {req.dimension_name}='ALL'"
            )
            if not result["success"]:
                return ModifyDownstreamFilterResponse(
                    success=False,
                    message=f"保存下游节点失败: {result['error'][:300]}",
                    original_sql=original_sql,
                    modified_sql=modified_sql,
                )

        # Generate diff
        diff_lines = _compute_diff_lines(original_sql, modified_sql)

        return ModifyDownstreamFilterResponse(
            success=True,
            message="过滤条件已添加并保存",
            original_sql=original_sql,
            modified_sql=modified_sql,
            diff_lines=diff_lines,
        )

    except Exception as e:
        logger.error(f"modify_downstream_filter failed: {e}")
        return ModifyDownstreamFilterResponse(
            success=False,
            message=f"处理失败: {str(e)}",
        )


def _query_task_by_node_id(schema: str, node_id: str) -> dict:
    """Query a DataWorks task by node_id."""
    try:
        pid = resolve_project_id(schema)
        if not pid:
            return {"found": False, "error": f"项目 '{schema}' 未找到"}

        wrapper = _get_wrapper()

        # Strategy 1: Search files by node_id keyword
        files = wrapper.list_files_by_keyword(pid, node_id)

        for f in files:
            file_node_id = f.get("NodeId")
            if file_node_id and str(file_node_id) == str(node_id):
                file_id = int(f.get("FileId") or f.get("Id") or 0)
                if file_id:
                    code = wrapper.get_file_code(pid, file_id)
                    return {
                        "found": True,
                        "code": code,
                        "file_id": file_id,
                        "node_id": node_id,
                        "task_name": f.get("FileName", ""),
                        "error": None,
                    }

        # Strategy 2: Fallback - list all files and search
        all_files = wrapper.list_files_by_keyword(pid, "")
        for f in all_files:
            for key in ["NodeId", "nodeId", "node_id", "NodeID"]:
                val = f.get(key)
                if val and str(val) == str(node_id):
                    file_id = int(f.get("FileId") or f.get("Id") or 0)
                    if file_id:
                        code = wrapper.get_file_code(pid, file_id)
                        return {
                            "found": True,
                            "code": code,
                            "file_id": file_id,
                            "node_id": node_id,
                            "task_name": f.get("FileName", ""),
                            "error": None,
                        }

        return {"found": False, "error": f"未找到 node_id={node_id} 的任务"}
    except Exception as e:
        logger.error(f"_query_task_by_node_id failed: {e}")
        return {"found": False, "error": str(e)}


def _add_where_filter(sql: str, dimension_name: str) -> str:
    """Add WHERE filter to include ALL rows for a given dimension.
    
    When a dimension is added via CUBE, the dimension column contains
    real values and "ALL" for rollup totals. Downstream tables should
    filter with `dimension = "ALL"` to select rollup totals.
    """
    import re
    
    # Check if already filtered
    escaped = re.escape(dimension_name)
    if re.search(rf"{escaped}\s*=\s*'ALL'", sql, re.IGNORECASE):
        return sql
    
    # Strategy 1: Existing WHERE clause — append AND at the END
    where_match = re.search(r"\bWHERE\b", sql, re.IGNORECASE)
    if where_match:
        where_start = where_match.end()
        remaining = sql[where_start:]
        # Find end of WHERE clause
        end_match = re.search(r"\b(GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING|UNION)\b", remaining, re.IGNORECASE)
        if end_match:
            insert_pos = where_start + end_match.start()
            return sql[:insert_pos].rstrip() + f"\nAND     {dimension_name} = 'ALL'" + sql[insert_pos:]
        else:
            # No keyword after WHERE, append at end
            return sql.rstrip() + f"\nAND     {dimension_name} = 'ALL'"
    
    # Strategy 2: No WHERE — add after FROM clause
    from_matches = list(re.finditer(r"\bFROM\s+\S+", sql, re.IGNORECASE))
    if from_matches:
        last_from = from_matches[-1]
        from_end = last_from.end()
        remaining = sql[from_end:]
        next_kw = re.search(r"\b(WHERE|GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING|UNION)\b", remaining, re.IGNORECASE)
        if next_kw:
            insert_pos = from_end + next_kw.start()
            return sql[:insert_pos].rstrip() + f"\nWHERE   {dimension_name} = 'ALL'" + sql[insert_pos:]
        else:
            return sql.rstrip() + f"\nWHERE   {dimension_name} = 'ALL'"
    
    # Strategy 3: Fallback
    return sql.rstrip() + f"\nWHERE   {dimension_name} = 'ALL'"

def _compute_diff_lines(original: str, modified: str) -> list:
    """Compute line-by-line diff for SQL display."""
    import difflib
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)

    diff = difflib.SequenceMatcher(None, orig_lines, mod_lines)
    result = []
    line_num = 1

    for op, i1, i2, j1, j2 in diff.get_opcodes():
        if op == 'equal':
            for k in range(i1, i2):
                result.append({"type": "unchanged", "line_num": line_num, "content": orig_lines[k].rstrip('\n')})
                line_num += 1
        elif op == 'replace':
            for k in range(i1, i2):
                result.append({"type": "removed", "line_num": line_num, "content": orig_lines[k].rstrip('\n')})
                line_num += 1
            for k in range(j1, j2):
                result.append({"type": "added", "line_num": line_num, "content": mod_lines[k].rstrip('\n')})
                line_num += 1
        elif op == 'delete':
            for k in range(i1, i2):
                result.append({"type": "removed", "line_num": line_num, "content": orig_lines[k].rstrip('\n')})
                line_num += 1
        elif op == 'insert':
            for k in range(j1, j2):
                result.append({"type": "added", "line_num": line_num, "content": mod_lines[k].rstrip('\n')})
                line_num += 1

    return result
