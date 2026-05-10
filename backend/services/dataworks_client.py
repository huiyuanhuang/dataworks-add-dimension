"""DataWorks SDK client — proper API integration with rate limiting, retry, and fuzzy matching."""

import json
import logging
import os
import re
import time
import threading
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

from alibabacloud_dataworks_public20240518 import models as dw_models
from alibabacloud_dataworks_public20240518.client import Client as DataWorksClient
from alibabacloud_tea_openapi import models as openapi_models

logger = logging.getLogger("dataworks_client")

# ── Config file support ───────────────────────────────────────

def _load_config_from_file() -> dict:
    """Load config from .env file (KEY=value format).
    
    Priority:
    1. Current working directory (CWD) .env
    2. Project root directory (relative to this file) .env
    3. Production /opt path .env
    4. User home directory .dataworks-add-dimension.env
    """
    config = {}
    import os
    
    # Try multiple locations in priority order
    config_paths = [
        # 1. Current working directory (highest priority - where user runs from)
        Path(os.getcwd()) / ".env",
        # 2. Project root directory (where the code lives)
        Path(__file__).parent.parent.parent / ".env",
        # 3. Production path
        Path("/opt/dataworks-add-dimension/.env"),
        # 4. User home directory
        Path.home() / ".dataworks-add-dimension.env",
    ]
    
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, val = line.split('=', 1)
                            config[key.strip()] = val.strip().strip('"').strip("'")
                logger.info(f"Loaded config from {config_path}")
                break
            except Exception:
                pass
    return config

# ── Environment config ──────────────────────────────────────────
_config_file = _load_config_from_file()

ACCESS_ID = os.environ.get("DATAWORK_ACCESS_ID") or os.environ.get("ACCESS_ID") or _config_file.get("DATAWORK_ACCESS_ID") or ""
ACCESS_KEY = os.environ.get("DATAWORK_ACCESS_KEY") or os.environ.get("ACCESS_KEY") or _config_file.get("DATAWORK_ACCESS_KEY") or ""
REGION_ID = os.environ.get("DATAWORK_REGION_ID") or os.environ.get("ALIBABA_CLOUD_REGION_ID") or _config_file.get("DATAWORK_REGION_ID") or "ap-southeast-1"

# ── Schema project map config ───────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_MAP_PATH = SCRIPT_DIR.parent / "references" / "schema_project_map.json"


# ── QPS Limiter ─────────────────────────────────────────────────
class QPSLimiter:
    """Sliding-window rate limiter to avoid DataWorks API throttling.
    
    Ensures:
    1. No more than max_qps requests per second
    2. Minimum gap of 0.5s between consecutive requests
    3. Thread-safe with global lock
    """

    def __init__(self, max_qps: int = 1):
        self.max_qps = max_qps
        self.window_seconds = 1.0
        self.min_gap = 0.5  # Minimum seconds between requests
        self._request_times: deque = deque()
        self._lock = threading.Lock()
        self._last_request_time = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.time()
            
            # Enforce minimum gap between requests
            time_since_last = now - self._last_request_time
            if time_since_last < self.min_gap and self._last_request_time > 0:
                wait = self.min_gap - time_since_last + 0.05
                if wait > 0:
                    time.sleep(wait)
                    now = time.time()
            
            # Remove timestamps outside the sliding window
            while self._request_times and now - self._request_times[0] >= self.window_seconds:
                self._request_times.popleft()
            
            if len(self._request_times) >= self.max_qps:
                # Wait until the oldest request is outside the window
                wait = self._request_times[0] + self.window_seconds - now + 0.05
                if wait > 0:
                    time.sleep(wait)
                    now = time.time()
                    while self._request_times and now - self._request_times[0] >= self.window_seconds:
                        self._request_times.popleft()
            
            self._last_request_time = time.time()
            self._request_times.append(self._last_request_time)


# ── DataWorks client ────────────────────────────────────────────
class DataWorksClientWrapper:
    """Wraps the Alibaba Cloud DataWorks SDK client with rate limiting and retry."""

    def __init__(self, access_key_id: str, access_key_secret: str, region_id: str, max_qps: int = 1):
        config = openapi_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region_id=region_id,
            endpoint=f"dataworks.{region_id}.aliyuncs.com",
        )
        self.client = DataWorksClient(config)
        self.qps = QPSLimiter(max_qps=max_qps)
        self._last_call_time = 0

    def _call(self, func, *args, max_retries: int = 5, **kwargs):
        """Call a DataWorks API method with rate limiting and exponential backoff retry."""
        import random
        for attempt in range(max_retries):
            self.qps.acquire()
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                msg = str(exc)
                if ("Throttling" in msg or "timed out" in msg.lower() or "too frequent" in msg.lower()) and attempt < max_retries - 1:
                    # Exponential backoff with jitter: 2, 4, 8, 16, 32 seconds + 0-3s random
                    wait = min(2 ** (attempt + 1), 60) + random.uniform(0, 3)
                    logger.warning("请求异常（%s），第 %d 次重试，等待 %.1fs", msg[:80], attempt + 1, wait)
                    time.sleep(wait)
                    continue
                raise

    # ── 数仓表名匹配规则 ───────────────────────────────────────
    _TABLE_PREFIX_RE = re.compile(r'^(ods|dwd|dwr|dws|dim)_')
    _TABLE_SUFFIX_RE = re.compile(r'_(\d+[dmh])$')

    @staticmethod
    def _extract_biz_keyword(table_name: str) -> str:
        """提取表名中的业务关键词（第二段），如 dwr_spock_xxx_1d → spock。"""
        parts = table_name.split("_")
        if len(parts) >= 3:
            return parts[1]
        return ""

    # ── List projects ────────────────────────────────────────────
    def list_projects(self) -> List[Dict]:
        """列出所有 DataWorks 项目空间，支持多种 API 响应格式。"""
        all_projects: List[Dict] = []
        page_number = 1
        page_size = 100

        while True:
            request = dw_models.ListProjectsRequest(page_number=page_number, page_size=page_size)
            response = self._call(self.client.list_projects, request)
            body = response.to_map().get("body", {})

            # DataWorks API 响应格式可能不同，尝试多种路径
            page_projects = (
                body.get("PagingInfo", {}).get("Projects", [])
                or body.get("PageResult", {}).get("ProjectList", [])
                or body.get("Data", {}).get("ProjectList", [])
                or body.get("Projects", [])
            )

            if not page_projects:
                break
            all_projects.extend(page_projects)
            if len(page_projects) < page_size:
                break
            page_number += 1

        logger.info(f"Listed {len(all_projects)} DataWorks projects")
        return all_projects

    # ── Find files ───────────────────────────────────────────────
    def list_files_by_keyword(self, project_id: int, keyword: str,
                              exact_page_count: Optional[int] = None) -> List[Dict]:
        """按关键字分页查询 DataWorks 任务文件。"""
        all_files: List[Dict] = []
        page_number = 1
        page_size = 100

        while True:
            request = dw_models.ListFilesRequest(
                project_id=project_id,
                page_number=page_number,
                page_size=page_size,
            )
            request.keyword = keyword
            response = self._call(self.client.list_files, request)
            data = response.to_map().get("body", {}).get("Data", {})
            page_files = data.get("Files", [])

            if not page_files:
                break
            all_files.extend(page_files)
            if exact_page_count is not None and page_number >= exact_page_count:
                break
            if len(page_files) < page_size:
                break
            page_number += 1

        return all_files

    def find_file_by_name(self, project_id: int, file_name: str) -> Optional[Dict]:
        """按文件名搜索 DataWorks 任务。精确匹配优先，模糊匹配需前缀、业务关键词和后缀一致。"""
        files = self.list_files_by_keyword(project_id, file_name, exact_page_count=1)

        # 精确匹配优先
        exact = [f for f in files if f.get("FileName") == file_name]
        if exact:
            return exact[0]

        # 模糊兜底：候选必须和目标共享数仓前缀、业务关键词和时间后缀
        if files:
            target_prefix = self._TABLE_PREFIX_RE.match(file_name)
            target_suffix = self._TABLE_SUFFIX_RE.search(file_name)
            target_biz = self._extract_biz_keyword(file_name)
            if target_prefix and target_suffix:
                tp, ts = target_prefix.group(1), target_suffix.group(1)
                for f in files:
                    fn = f.get("FileName", "")
                    fp = self._TABLE_PREFIX_RE.match(fn)
                    fs = self._TABLE_SUFFIX_RE.search(fn)
                    fb = self._extract_biz_keyword(fn)
                    if (fp and fs and fp.group(1) == tp and fs.group(1) == ts and fb == target_biz):
                        logger.info("模糊匹配: %s → %s", file_name, fn)
                        return f

        logger.debug("未匹配到任务: %s (候选 %d 个)", file_name, len(files))
        return None

    def query_files_by_prefix(self, project_id: int, prefix: str) -> List[Dict]:
        """按前缀查询 DataWorks 任务。"""
        files = self.list_files_by_keyword(project_id, prefix)
        matched = [f for f in files if (f.get("FileName") or "").startswith(prefix)]
        matched.sort(key=lambda item: item.get("FileName", ""))
        return matched

    # ── Get file code ────────────────────────────────────────────
    def get_file_code(self, project_id: int, file_id: int) -> str:
        """获取文件 SQL 代码，兼容 Content/FileCode 两种字段名。"""
        try:
            request = dw_models.GetFileRequest(file_id=file_id, project_id=project_id)
            response = self._call(self.client.get_file, request)
            body = response.to_map().get("body", {})
            data = body.get("Data", {})
            file_info = data.get("File", data)
            return (
                file_info.get("Content")
                or file_info.get("FileCode")
                or data.get("FileCode")
                or data.get("Content")
                or ""
            )
        except Exception:
            return ""

    def get_file_detail(self, project_id: int, file_id: int) -> Dict:
        """获取文件详情。"""
        request = dw_models.GetFileRequest(file_id=file_id, project_id=project_id)
        response = self._call(self.client.get_file, request)
        data = response.to_map().get("body", {}).get("Data", {})
        return data.get("File", {})

    # ── Lineage operations ─────────────────────────────────────

    def list_tables(self, name: str = None, page_number: int = 1,
                    page_size: int = 100) -> List[Dict]:
        """List tables in DataWorks metadata, optionally filtered by name."""
        request = dw_models.ListTablesRequest(
            name=name,
            page_number=page_number,
            page_size=page_size,
        )
        response = self._call(self.client.list_tables, request)
        data = response.to_map().get("body", {})
        logger.info(f"list_tables response: {data}")

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            result = (
                data.get("PagingInfo", {}).get("Tables", [])
                or data.get("PageResult", {}).get("Tables", [])
                or data.get("Data", {}).get("Tables", [])
                or data.get("Tables", [])
            )
            if result:
                return result
        body = response.to_map().get("body", {})
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            return body.get("Tables", [])
        return []

    def list_lineages(self, src_entity_name: str = None, src_entity_id: str = None,
                      page_number: int = 1, page_size: int = 100) -> List[Dict]:
        """按上游实体名称查询血缘关系，返回下游节点列表。"""
        request = dw_models.ListLineagesRequest(
            src_entity_name=src_entity_name,
            page_number=page_number,
            page_size=page_size,
        )
        response = self._call(self.client.list_lineages, request)
        data = response.to_map().get("body", {})
        logger.info(f"list_lineages response: {data}")

        # Try multiple response structures
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # May be wrapped in PagingInfo or Data
            result = (
                data.get("PagingInfo", {}).get("Lineages", [])
                or data.get("PageResult", {}).get("Lineages", [])
                or data.get("Data", {}).get("Lineages", [])
                or data.get("Lineages", [])
            )
            if result:
                return result
        # Direct response body may contain lineages
        body = response.to_map().get("body", {})
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            return body.get("Lineages", [])
        return []


# ── Singleton wrapper instance ──────────────────────────────────
_dw_wrapper: Optional[DataWorksClientWrapper] = None


def _get_wrapper() -> DataWorksClientWrapper:
    """Get or create the singleton DataWorksClientWrapper instance."""
    global _dw_wrapper
    if _dw_wrapper is None:
        if not ACCESS_ID or not ACCESS_KEY:
            raise RuntimeError("缺少环境变量: DATAWORK_ACCESS_ID / DATAWORK_ACCESS_KEY")
        _dw_wrapper = DataWorksClientWrapper(ACCESS_ID, ACCESS_KEY, REGION_ID, max_qps=1)
    return _dw_wrapper


# ── Schema project map ──────────────────────────────────────────
def load_schema_project_map() -> Dict[str, int]:
    """从配置文件加载 schema → project_id 映射。"""
    if SCHEMA_MAP_PATH.exists():
        return json.loads(SCHEMA_MAP_PATH.read_text(encoding="utf-8"))
    return {}


def save_schema_project_map(mapping: Dict[str, int]) -> None:
    """保存 schema → project_id 映射到配置文件。"""
    SCHEMA_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_MAP_PATH.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"映射已保存: {SCHEMA_MAP_PATH} ({len(mapping)} 条)")


def scan_and_save_schema_project_map() -> Dict[str, int]:
    """扫描所有项目空间，构建并保存 schema(ProjectIdentifier) → project_id 映射。"""
    wrapper = _get_wrapper()
    projects = wrapper.list_projects()
    mapping: Dict[str, int] = {}
    for p in projects:
        # API 返回的 dict 可能使用不同 key 名称
        identifier = p.get("Name") or p.get("ProjectIdentifier") or p.get("ProjectName") or ""
        pid = p.get("Id") or p.get("ProjectId")
        if identifier and pid:
            mapping[identifier] = int(pid)
    save_schema_project_map(mapping)
    return mapping


def resolve_project_id(schema: str) -> Optional[int]:
    """根据 schema 查找对应的 DataWorks project_id，先查缓存再查 API。"""
    # 1. 先查本地缓存
    mapping = load_schema_project_map()
    if schema in mapping:
        return mapping[schema]

    # 2. 缓存为空则扫描构建缓存
    if not mapping:
        mapping = scan_and_save_schema_project_map()
        if schema in mapping:
            return mapping[schema]

    # 3. 直接用 API 查询
    wrapper = _get_wrapper()
    projects = wrapper.list_projects()
    for p in projects:
        identifier = p.get("Name") or p.get("ProjectIdentifier") or p.get("ProjectName") or ""
        pid = p.get("Id") or p.get("ProjectId")
        if identifier == schema and pid:
            # 更新缓存
            mapping[identifier] = int(pid)
            save_schema_project_map(mapping)
            return int(pid)

    return None


# ── Public API functions ────────────────────────────────────────
def list_projects() -> list:
    """List all DataWorks projects. Returns [{id, name, project_id}]."""
    wrapper = _get_wrapper()
    raw_projects = wrapper.list_projects()
    result = []

    for p in raw_projects:
        identifier = p.get("Name") or p.get("ProjectIdentifier") or p.get("ProjectName") or ""
        pid = p.get("Id") or p.get("ProjectId")
        if identifier and pid:
            result.append({
                "id": identifier,
                "name": identifier,
                "project_id": int(pid),
            })

    logger.info(f"Listed {len(result)} DataWorks projects")
    return result


def query_task(schema: str, table_name: str) -> dict:
    """Query a DataWorks task/node by schema (project_identifier) and table name.

    Returns {found, code, file_id, node_id, task_name, folder_path, error}.
    """
    import time as _time
    _t0 = _time.time()
    logger.info(f"[query_task] START schema={schema} table={table_name}")

    # Step 1: Find the project_id for this schema
    project_id = resolve_project_id(schema)
    if project_id is None:
        logger.warning(f"[query_task] resolve_project_id FAILED for schema={schema}")
        return {"found": False, "error": f"项目 '{schema}' 未在 DataWorks 中找到"}
    logger.info(f"[query_task] resolve_project_id OK project_id={project_id}")

    wrapper = _get_wrapper()

    # Step 2: Find file by name with smart fuzzy matching
    file_info = wrapper.find_file_by_name(project_id, table_name)
    if not file_info:
        logger.warning(f"[query_task] find_file_by_name FAILED schema={schema} table={table_name}")
        return {"found": False, "error": f"未在 DataWorks 项目 '{schema}' 中找到与 '{table_name}' 相关的文件"}
    logger.info(f"[query_task] find_file_by_name OK file_name={file_info.get('FileName')}")

    file_id = int(file_info.get("FileId") or file_info.get("Id") or 0)
    if not file_id:
        logger.warning(f"[query_task] missing FileId for {table_name}")
        return {"found": False, "error": f"文件 '{table_name}' 缺少 FileId"}

    # Step 3: Get file SQL code
    code = wrapper.get_file_code(project_id, file_id)
    detail = wrapper.get_file_detail(project_id, file_id)
    logger.info(f"[query_task] get_file_code OK file_id={file_id} code_len={len(code)}")

    node_id = detail.get("NodeId") or file_info.get("NodeId")
    elapsed = _time.time() - _t0
    logger.info(f"[query_task] END elapsed={elapsed:.2f}s file_id={file_id} node_id={node_id}")

    return {
        "found": True,
        "code": code,
        "file_id": file_id,
        "node_id": str(node_id) if node_id else None,
        "task_name": file_info.get("FileName", table_name),
        "folder_path": detail.get("FileFolderPath", ""),
        "error": None,
    }


def commit_node(project_id: int, file_id: int, sql_content: str, commit_message: str = "自动加维度") -> dict:
    """Update a DataWorks file's SQL content. Returns {success, error}."""
    wrapper = _get_wrapper()
    try:
        req = dw_models.UpdateFileRequest(
            file_id=file_id,
            project_id=project_id,
            content=sql_content,
            file_description=commit_message,
        )
        wrapper._call(wrapper.client.update_file, req)
        return {"success": True, "error": None}
    except Exception as e:
        error_msg = str(e)
        if "你的角色没有操作该业务的权限" in error_msg:
            return {"success": False, "error": f"项目 '{project_id}' 无 DataWorks 编辑权限"}
        return {"success": False, "error": f"保存失败: {error_msg[:300]}"}


def _get_project_id(schema: str) -> Optional[int]:
    """Get DataWorks integer project_id from schema name. Alias for resolve_project_id."""
    return resolve_project_id(schema)


# ── Downstream nodes lookup ────────────────────────────────────
def find_downstream_nodes(schema: str, table_name: str, sql_content: str = None, node_id: str = None) -> list:
    """Find downstream nodes for a given table using DataWorks downstream task API.

    Uses list_downstream_tasks(node_id) API to get downstream scheduling dependencies.

    Args:
        schema: DataWorks project identifier
        table_name: Target table name
        sql_content: Current SQL content (optional)
        node_id: Current node ID (required for list_downstream_tasks)

    Returns:
        List of dicts with {node_id, node_name, project_env, needs_filter}
    """
    import time as _time
    _t0 = _time.time()

    # Extract target table from SQL
    target_table = None
    if sql_content:
        m = re.search(r'INSERT\s+OVERWRITE\s+TABLE\s+(\S+)', sql_content, re.IGNORECASE)
        if m:
            target_table = m.group(1).strip('\`')

    if not target_table:
        target_table = table_name

    logger.info(f"[find_downstream_nodes] target_table={target_table}, schema={schema}, node_id={node_id}")

    # Must have node_id to call list_downstream_tasks
    if not node_id:
        logger.warning(f"[find_downstream_nodes] No node_id provided, falling back to file search")
        return _find_downstream_by_file_search(schema, target_table)

    try:
        wrapper = _get_wrapper()
        downstream_nodes = []

        # Strategy 1: list_downstream_tasks API
        try:
            logger.info(f"[find_downstream_nodes] Strategy 1: list_downstream_tasks(node_id={node_id})")
            import alibabacloud_dataworks_public20240518.models as dw_models
            request = dw_models.ListDownstreamTasksRequest(
                id=node_id,
                page_number=1,
                page_size=100,
            )
            response = wrapper._call(wrapper.client.list_downstream_tasks, request)
            data = response.to_map().get("body", {})
            logger.info(f"[find_downstream_nodes] Strategy 1 raw response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")

            paging_info = data.get("PagingInfo", {})
            downstream_tasks = paging_info.get("DownstreamTasks", [])
            tasks = paging_info.get("Tasks", [])

            logger.info(f"[find_downstream_nodes] Strategy 1 found {len(downstream_tasks)} downstream_tasks, {len(tasks)} tasks")

            for task_info in downstream_tasks:
                task = task_info.get("Task", {})
                if task:
                    downstream_nodes.append({
                        "node_id": str(task.get("Id", "")),
                        "node_name": task.get("Name", ""),
                        "project_env": task.get("EnvType", "Prod").lower(),
                        "needs_filter": False,
                    })

            # Also add from Tasks list
            for task in tasks:
                task_id = task.get("Id")
                # Avoid duplicates
                if task_id and not any(n["node_id"] == str(task_id) for n in downstream_nodes):
                    downstream_nodes.append({
                        "node_id": str(task_id),
                        "node_name": task.get("Name", ""),
                        "project_env": task.get("EnvType", "Prod").lower(),
                        "needs_filter": False,
                    })

            if downstream_nodes:
                logger.info(f"[find_downstream_nodes] Strategy 1 success: {len(downstream_nodes)} nodes")
                return downstream_nodes
            else:
                logger.info(f"[find_downstream_nodes] Strategy 1: no downstream tasks found")
        except Exception as e:
            logger.warning(f"[find_downstream_nodes] Strategy 1 failed: {e}")

        # Strategy 2: fallback to file search
        return _find_downstream_by_file_search(schema, target_table)

    except Exception as e:
        logger.error(f"[find_downstream_nodes] Fatal error: {e}")
        return []
    finally:
        elapsed = _time.time() - _t0
        logger.info(f"[find_downstream_nodes] END elapsed={elapsed:.2f}s nodes={len(downstream_nodes)}")


def _find_downstream_by_file_search(schema: str, target_table: str) -> list:
    """Fallback: search files that reference the target table."""
    downstream_nodes = []
    try:
        project_id = resolve_project_id(schema)
        if not project_id:
            return []

        wrapper = _get_wrapper()
        logger.info(f"[find_downstream_nodes] Fallback: file keyword search for {target_table}")
        files = wrapper.list_files_by_keyword(project_id, target_table)
        logger.info(f"[find_downstream_nodes] Fallback returned {len(files)} files")

        for f in files:
            file_name = f.get("FileName", "")
            file_id = f.get("FileId") or f.get("Id")
            file_node_id = f.get("NodeId")
            if file_name == target_table:
                continue
            downstream_nodes.append({
                "node_id": str(file_node_id or file_id or ""),
                "node_name": file_name,
                "project_env": "dev",
                "needs_filter": False,
            })
    except Exception as e:
        logger.warning(f"[find_downstream_nodes] Fallback failed: {e}")
    return downstream_nodes

def _parse_lineage_records(lineages: list) -> list:
    """Parse lineage records and extract downstream node info."""
    downstream_nodes = []
    for lineage in lineages:
        # Try both camelCase and PascalCase keys
        dst_name = (lineage.get("DstEntityName") or lineage.get("dstEntityName", ""))
        dst_id = (lineage.get("DstEntityId") or lineage.get("dstEntityId", ""))
        rel_type = (lineage.get("RelationshipType") or lineage.get("relationshipType", ""))
        
        # Also try other possible field names
        if not dst_name:
            dst_name = lineage.get("entityName", "") or lineage.get("EntityName", "")
        if not dst_id:
            dst_id = lineage.get("entityId", "") or lineage.get("EntityId", "")

        if dst_name:
            downstream_nodes.append({
                "node_id": str(dst_id or ""),
                "node_name": dst_name,
                "project_env": "DEV",
                "needs_filter": False,
            })
    return downstream_nodes


def _find_downstream_nodes_fallback(schema: str, target_table: str, project_id: int) -> list:
    """Fallback: search files that reference the target table."""
    pass  # placeholder, not used

# ── Deploy file ───────────────────────────────────────────────

def deploy_file(project_id: int, file_id: int, comment: str, node_id: int = None) -> dict:
    """Deploy (commit) a DataWorks file to production.

    Args:
        project_id: DataWorks project ID (integer)
        file_id: File ID to deploy
        comment: Commit comment/note
        node_id: Optional node ID

    Returns:
        {"success": bool, "error": str|None, "deployment_id": str|None}
    """
    wrapper = _get_wrapper()
    try:
        req = dw_models.DeployFileRequest(
            project_id=project_id,
            file_id=file_id,
            comment=comment,
        )
        # node_id is optional; only pass if provided
        if node_id is not None:
            req.node_id = node_id

        response = wrapper._call(wrapper.client.deploy_file, req)
        data = response.to_map().get("body", {})
        
        # Try to extract deployment info from response
        deployment_id = None
        if isinstance(data, dict):
            deployment_id = (
                data.get("Data", {}).get("DeploymentId")
                or data.get("DeploymentId")
                or data.get("data", {}).get("deploymentId")
            )
        
        logger.info(f"File {file_id} deployed successfully, deployment_id={deployment_id}")
        return {
            "success": True,
            "error": None,
            "deployment_id": deployment_id,
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Deploy file {file_id} failed: {error_msg[:200]}")
        return {
            "success": False,
            "error": f"提交失败: {error_msg[:300]}",
            "deployment_id": None,
        }

# ── Submit file (commit code to DataWorks) ─────────────────────

def submit_file(project_id: int, file_id: int, comment: str, 
                project_identifier: str = None,
                skip_all_deploy_file_extensions: bool = False) -> dict:
    """Submit (commit) a DataWorks file to the repository.

    This is the correct API for committing code changes to DataWorks,
    before deploying to production.

    Args:
        project_id: DataWorks project ID (integer)
        file_id: File ID to submit
        comment: Commit comment/note
        project_identifier: Optional project identifier string
        skip_all_deploy_file_extensions: Whether to skip deploy extensions

    Returns:
        {"success": bool, "error": str|None, "file_id": int}
    """
    wrapper = _get_wrapper()
    try:
        req = dw_models.SubmitFileRequest(
            project_id=project_id,
            file_id=file_id,
            comment=comment,
        )
        if project_identifier:
            req.project_identifier = project_identifier
        if skip_all_deploy_file_extensions:
            req.skip_all_deploy_file_extensions = skip_all_deploy_file_extensions

        response = wrapper._call(wrapper.client.submit_file, req)
        data = response.to_map().get("body", {})
        
        logger.info(f"File {file_id} submitted successfully")
        return {
            "success": True,
            "error": None,
            "file_id": file_id,
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Submit file {file_id} failed: {error_msg[:200]}")
        return {
            "success": False,
            "error": f"提交失败: {error_msg[:300]}",
            "file_id": file_id,
        }
