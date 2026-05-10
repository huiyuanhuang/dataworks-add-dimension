"""BI platform client — refactored to use queryDatasetById + chartColumnList flow.

Uses requests library to call FBI (FlatInc BI) APIs for dimension sync.
"""

import os
import json
import logging
import time
import requests
from typing import Optional, Dict, List, Any

logger = logging.getLogger("bi_client")

BI_BASE_URL = "https://fbi.flatincbr.com"
BI_USERNAME = os.environ.get("BI_USERNAME", "")
BI_PASSWORD = os.environ.get("BI_PASSWORD", "")


class BIClient:
    def __init__(self, user_name: str = None, password_salt: str = None):
        self.user_name = user_name or BI_USERNAME
        self.password_salt = password_salt or BI_PASSWORD
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Redirect-Url": "https://fbi.flatincbr.com/",
            "User-Agent": "dataworks-web/1.0",
        })
        self._logged_in = False

    def _url(self, path: str) -> str:
        return f"{BI_BASE_URL}{path}"

    def login(self):
        if self._logged_in:
            return
        if not self.user_name or not self.password_salt:
            raise RuntimeError("BI credentials not configured. Please set BI_USERNAME and BI_PASSWORD environment variables.")
        resp = self.session.post(
            self._url("/api/login/pwdLogin/"),
            json={"userName": self.user_name, "passwordSalt": self.password_salt},
        )
        data = resp.json()
        if not data.get("isSuccess") and data.get("code") != 200:
            raise RuntimeError(f"BI login failed: {data.get('msg', 'Unknown')}")
        self._logged_in = True
        logger.info("BI login successful")

    def _call(self, method: str, path: str, body=None, params=None) -> dict:
        self.login()
        if method == "GET":
            resp = self.session.get(self._url(path), params=params)
        else:
            resp = self.session.post(self._url(path), json=body, params=params)

        # Check HTTP status before parsing JSON
        if resp.status_code >= 400:
            try:
                err_data = resp.json()
                err_msg = err_data.get("msg", err_data.get("message", ""))
            except Exception:
                err_msg = resp.text[:500]
            raise RuntimeError(
                f"BI API HTTP {resp.status_code}: {err_msg or resp.reason}"
            )

        return resp.json()

    # ── Dataset operations ──

    def find_dataset(self, table_name: str) -> Optional[dict]:
        """Find BI dataset matching table_name. Returns dataset dict or None."""
        resp = self._call("GET", "/api/dataset/queryDatasetByName", params={"datasetName": table_name})
        if not resp.get("isSuccess"):
            raise RuntimeError(f"Query dataset failed: {resp.get('msg')}")
        data = resp.get("data")
        if not data:
            return None
        # Handle both single object and list responses
        if isinstance(data, list):
            if not data:
                return None
            data = data[0]
        return data

    def query_dataset_by_id(self, dataset_id: int) -> dict:
        """Get dataset detail including chartDTOList via queryDatasetById.

        Returns full dataset dict with chartDTOList (all charts associated).
        """
        resp = self._call("GET", "/api/dataset/queryDatasetById", params={"id": dataset_id})
        if not resp.get("isSuccess"):
            raise RuntimeError(f"Query dataset by ID failed: {resp.get('msg')}")
        return resp.get("data", {})

    def get_dataset_columns(self, dataset_code: str) -> list:
        """Get dataset column list."""
        resp = self._call("GET", "/api/dataset/queryDatasetByCode", params={"datasetCode": dataset_code})
        if not resp.get("isSuccess"):
            raise RuntimeError(f"Query dataset detail failed: {resp.get('msg')}")
        return resp.get("data", {}).get("datasetColumnDTOList") or resp.get("data", {}).get("datasetColumnList", [])

    def refresh_metadata(self, dataset_code: str, datasource_name: str = "",
                         datasource_table_name: str = "") -> bool:
        """Refresh dataset metadata (sync ODPS schema changes to BI)."""
        body = {"datasetCode": dataset_code}
        if datasource_name:
            body["datasourceName"] = datasource_name
        if datasource_table_name:
            body["datasourceTableName"] = datasource_table_name
        resp = self._call("POST", "/api/dataset/refreshMetaData", body=body)
        if not resp.get("isSuccess"):
            logger.error(f"Refresh metadata failed: {resp.get('msg')}")
            return False
        logger.info(f"Metadata refresh requested for {dataset_code}")
        return True

    # ── Chart operations ──

    def get_chart_detail(self, chart_code: str) -> dict:
        """Get chart detail including chartColumnList and metadataJson."""
        resp = self._call("GET", "/api/chart/queryChartByCode", params={"chartCode": chart_code})
        if not resp.get("isSuccess"):
            raise RuntimeError(f"Get chart detail failed: {resp.get('msg')}")
        return resp.get("data", {})

    def update_chart(self, chart_code: str, chart_detail: dict, app_code: str,
                     chart_column_list: list = None,
                     metadata_json: str = None) -> bool:
        """Update a chart using the full chartColumnList format.

        chart_column_list: updated chartColumnList to send in the request body.
        metadata_json: updated metadataJson (only needed for filtration charts).
        """
        body = {
            "orderIndex": chart_detail.get("orderIndex", 1),
            "chartType": chart_detail.get("chartType", "filtration"),
            "applicationCode": app_code,
            "chartChineseName": chart_detail.get("chartChineseName", ""),
            "dashboardCode": chart_detail.get("dashboardCode"),
            "datasetCode": chart_detail.get("datasetCode"),
            "pageShow": chart_detail.get("pageShow", 0),
            "pageSize": chart_detail.get("pageSize", 10000),
            "chartWidth": chart_detail.get("chartWidth", 1),
            "chartHeight": chart_detail.get("chartHeight", 300),
            "filterSql": chart_detail.get("filterSql") or "",
            "filterColumnList": chart_detail.get("filterColumnList") or [],
            "description": chart_detail.get("description") or "",
            "smartAnalysis": chart_detail.get("smartAnalysis", 0),
            "coloumSizeStyle": chart_detail.get("coloumSizeStyle") or "",
            "dicDuration": chart_detail.get("dicDuration", 3),
            "docLink": chart_detail.get("docLink") or "",
            "summary": chart_detail.get("summary", 0),
            "chartCode": chart_code,
        }
        if chart_column_list is not None:
            body["chartColumnList"] = chart_column_list
        if metadata_json is not None:
            body["metadataJson"] = metadata_json

        resp = self._call("POST", "/api/chart/updateChart", body=body)
        if not resp.get("isSuccess"):
            logger.error(f"Update chart failed: {resp.get('msg')}")
            return False
        logger.info(f"Chart '{chart_code}' updated successfully")
        return True

    # ── Default values logic ──

    def _determine_default_values(self, expansion_type: str,
                                   existing_columns: list,
                                   dimension_name: str) -> dict:
        """Determine defaultValues/defaultValueList/optionList for the new dimension.

        Rules:
        - cube or lateral_view -> defaultValues="ALL" (SQL produces ALL rows via CUBE/EXPLODE)
        - group_by -> empty lists (plain aggregation, no ALL rows)
        - unknown -> fall back to checking existing columns in chart
        """
        ALL_DEFAULTS = {
            "defaultValues": "ALL",
            "defaultValueList": ["ALL"],
            "optionList": [{"text": "ALL", "value": "ALL"}],
        }
        NO_ALL_DEFAULTS = {
            "defaultValues": None,
            "defaultValueList": [],
            "optionList": [],
        }

        if expansion_type in ("cube", "lateral_view"):
            return ALL_DEFAULTS

        if expansion_type == "group_by":
            return NO_ALL_DEFAULTS

        # expansion_type is "unknown" — fall back to existing column pattern
        similar_dims = [c for c in existing_columns
                        if c.get("dimensionOrMeasure") == "dimension"
                        and c.get("column") != dimension_name]
        all_dims_with_all = [c for c in similar_dims if c.get("defaultValues") == "ALL"]
        if similar_dims and len(all_dims_with_all) >= len(similar_dims) / 2:
            return ALL_DEFAULTS

        return NO_ALL_DEFAULTS

    # ── Full dimension sync workflow ──

    def sync_dimension(self, table_name: str, dimension_name: str,
                       dimension_chinese_name: str = "",
                       app_code: str = None,
                       expansion_type: str = "unknown") -> dict:
        """Full BI dimension sync using the new API flow.

        Steps:
        1. find_dataset -> get datasetCode + id
        2. refresh_metadata -> refresh ODPS schema + verify column exists
        3. query_dataset_by_id -> get chartDTOList (all charts for dataset)
        4. For each chart: update dimension column in chartColumnList + metadataJson

        expansion_type determines whether defaultValues should be "ALL":
        - cube/lateral_view -> ALL defaults
        - group_by -> empty defaults
        - unknown -> reference existing columns

        Returns {success, steps_detail, message}.
        """
        steps = {}

        # Step 1: Find dataset
        ds = self.find_dataset(table_name)
        if ds is None:
            return {"success": False, "steps_detail": steps,
                    "message": f"未在 BI 中找到与表 '{table_name}' 匹配的数据集"}
        ds_code = ds.get("datasetCode")
        ds_id = ds.get("id")
        ds_datasource_code = ds.get("datasourceCode", "")
        ds_datasource_table_name = ds.get("datasourceTableName", "")

        # Resolve datasourceName
        ds_datasource_name = ""
        if ds_datasource_code:
            ds_list = self._call("GET", "/api/datasource/queryDatasourceList")
            for d in ds_list.get("data", []):
                if d.get("datasourceCode") == ds_datasource_code:
                    ds_datasource_name = d.get("datasourceName", "")
                    break
        if not ds_datasource_table_name:
            ds_datasource_table_name = table_name

        steps["step1_find_dataset"] = {
            "ok": True, "dataset_name": ds.get("datasetName"), "dataset_code": ds_code,
            "datasource_name": ds_datasource_name,
            "datasource_table_name": ds_datasource_table_name,
        }

        # Step 2: Refresh metadata
        if not self.refresh_metadata(ds_code, ds_datasource_name, ds_datasource_table_name):
            steps["step2_refresh_metadata"] = {"ok": False, "message": "元数据刷新失败"}
            return {"success": False, "steps_detail": steps, "message": "元数据刷新失败"}

        logger.info("Waiting 3s for metadata sync...")
        time.sleep(3)

        # Verify column exists
        cols = self.get_dataset_columns(ds_code)
        col_names = [c.get("column", "") for c in cols]
        if dimension_name not in col_names:
            steps["step2_refresh_metadata"] = {
                "ok": False,
                "message": f"刷新后仍未发现维度 '{dimension_name}'",
                "available_columns": col_names,
            }
            return {"success": False, "steps_detail": steps,
                    "message": f"维度 '{dimension_name}' 在数据集列中不存在（已刷新元数据）"}
        steps["step2_refresh_metadata"] = {"ok": True, "dimension_found": True}

        # Step 3: Get charts via queryDatasetById
        ds_detail = self.query_dataset_by_id(ds_id)
        chart_list = ds_detail.get("chartDTOList") or []

        # Filter by app_code if specified
        if app_code:
            chart_list = [c for c in chart_list if c.get("applicationCode") == app_code]

        steps["step3_find_charts"] = {"ok": True, "chart_count": len(chart_list)}

        # Step 4: Update charts
        col_meta = next((c for c in cols if c.get("column") == dimension_name), None)

        updated = 0
        failed = 0
        for chart in chart_list:
            chart_code = chart.get("chartCode")
            chart_type = chart.get("chartType")
            chart_app_code = chart.get("applicationCode")

            try:
                detail = self.get_chart_detail(chart_code)
            except Exception as e:
                logger.error(f"Failed to get chart detail for {chart_code}: {e}")
                failed += 1
                continue

            col_list = detail.get("chartColumnList") or []

            # Determine defaultValues based on expansion_type + existing columns in this chart
            defaults = self._determine_default_values(expansion_type, col_list, dimension_name)

            # Check if dimension already exists in chartColumnList
            dim_in_chart = next(
                (c for c in col_list if c.get("column") == dimension_name), None
            )

            if dim_in_chart:
                # Update existing: set showPanel=1 and filtration-specific fields
                dim_in_chart["showPanel"] = 1
                if chart_type == "filtration":
                    dim_in_chart["showSpread"] = 1
                    dim_in_chart["componentType"] = "multipleSelect"
                    dim_in_chart["operator"] = "in"
                    dim_in_chart["defaultValues"] = defaults["defaultValues"]
                    dim_in_chart["defaultValueList"] = defaults["defaultValueList"]
                    dim_in_chart["optionList"] = defaults["optionList"]
            else:
                # Add new column to chartColumnList
                new_col = {
                    "checked": 1,
                    "column": dimension_name,
                    "columnChineseName": (
                        dimension_chinese_name
                        or (col_meta.get("columnChineseName", dimension_name) if col_meta else dimension_name)
                    ),
                    "dataType": col_meta.get("dataType", "string") if col_meta else "string",
                    "dimensionOrMeasure": "dimension",
                    "showPanel": 1,
                    "showSpread": 1 if chart_type == "filtration" else 0,
                    "spreadType": 0,
                    "status": 1,
                    "componentType": "multipleSelect" if chart_type == "filtration" else None,
                    "operator": "in" if chart_type == "filtration" else None,
                    "defaultValues": defaults["defaultValues"] if chart_type == "filtration" else None,
                    "defaultValueList": defaults["defaultValueList"] if chart_type == "filtration" else [],
                    "optionList": defaults["optionList"] if chart_type == "filtration" else [],
                    "isNotAll": 0,
                    "isSummarize": 0,
                    "disable": 0,
                    "original": 0,
                    "selected": 0,
                    "showMustSelect": 0,
                    "orderIndex": len(col_list) + 1,
                    "orderShow": 1,
                    "showName": (
                        dimension_chinese_name
                        or (col_meta.get("columnChineseName", dimension_name) if col_meta else dimension_name)
                    ),
                    "showDisabled": 0,
                    "showCustom": 0,
                    "timeDimension": 0,
                    "rankMark": None,
                    "axisType": None,
                    "formatting": None,
                    "order": None,
                    "columnType": None,
                    "parentId": None,
                    "nodeType": None,
                    "children": None,
                    "sortColumn": None,
                    "sortColumnName": None,
                    "dicDatasetCode": None,
                    "dicColumnKey": None,
                    "dicColumnShow": None,
                }
                col_list.append(new_col)

            # For filtration charts, also update metadataJson
            metadata_json = None
            if chart_type == "filtration":
                try:
                    meta = json.loads(detail.get("metadataJson") or "[]")
                except json.JSONDecodeError:
                    meta = []

                meta_exists = False
                for m in meta:
                    if m.get("column") == dimension_name:
                        m["showPanel"] = 1
                        m["showSpread"] = 1
                        m["componentType"] = "multipleSelect"
                        m["operator"] = "in"
                        m["defaultValues"] = defaults["defaultValues"]
                        m["defaultValueList"] = defaults["defaultValueList"]
                        m["optionList"] = defaults["optionList"]
                        m["isNotAll"] = 0
                        meta_exists = True
                        break

                if not meta_exists:
                    meta.append({
                        "checked": 1,
                        "column": dimension_name,
                        "columnChineseName": (
                            dimension_chinese_name
                            or (col_meta.get("columnChineseName", dimension_name) if col_meta else dimension_name)
                        ),
                        "dataType": col_meta.get("dataType", "string") if col_meta else "string",
                        "dimensionOrMeasure": "dimension",
                        "showPanel": 1,
                        "showSpread": 1,
                        "spreadType": 0,
                        "status": 1,
                        "componentType": "multipleSelect",
                        "operator": "in",
                        "defaultValues": defaults["defaultValues"],
                        "defaultValueList": defaults["defaultValueList"],
                        "optionList": defaults["optionList"],
                        "isNotAll": 0,
                        "isSummarize": 0,
                        "disable": 0,
                        "original": 0,
                        "selected": 0,
                        "showMustSelect": 0,
                    })
                metadata_json = json.dumps(meta, ensure_ascii=False)

            try:
                ok = self.update_chart(chart_code, detail, chart_app_code,
                                       chart_column_list=col_list,
                                       metadata_json=metadata_json)
                if ok:
                    updated += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Failed to update chart {chart_code}: {e}")
                failed += 1

        steps["step4_update_charts"] = {"ok": True, "updated": updated, "failed": failed}
        return {
            "success": failed == 0,
            "steps_detail": steps,
            "message": f"BI 同步完成: {updated} 个图表已更新, {failed} 个失败",
        }
