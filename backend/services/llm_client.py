"""OpenAI API client for SQL analysis, rewriting, and self-checking."""

import json
import logging
import os
import re
import time
import hashlib
from typing import Optional

try:
    import openai
except ImportError:
    openai = None

logger = logging.getLogger("llm_client")

# ── Environment config ──────────────────────────────────────────
def _load_env():
    """Load .env file if exists."""
    from pathlib import Path
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key:
                        os.environ[key] = val

_load_env()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4")
OPENAI_TIMEOUT = int(os.environ.get("OPENAI_TIMEOUT", "60"))
OPENAI_MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "3"))

# ── Cache ────────────────────────────────────────────────────────
_cache = {}

# ── Tool definitions ─────────────────────────────────────────────

ANALYZE_TOOL = {
    "type": "json_schema",
    "json_schema": {
        "name": "sql_analysis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "expansion_type": {"type": "string"},
                "upstream_tables": {"type": "array", "items": {"type": "object"}},
                "issues": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["expansion_type", "upstream_tables", "issues"],
            "additionalProperties": False,
        }
    }
}

REWRITE_TOOL = {
    "type": "json_schema",
    "json_schema": {
        "name": "sql_rewrite",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "modified_sql": {"type": "string"},
                "alter_table_sql": {"type": "string"},
                "changes_made": {"type": "array", "items": {"type": "string"}},
                "issues": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["modified_sql", "alter_table_sql", "changes_made", "issues"],
            "additionalProperties": False,
        }
    }
}

SELF_CHECK_TOOL = {
    "type": "json_schema",
    "json_schema": {
        "name": "sql_self_check",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "checks": {"type": "object"},
            },
            "required": ["checks"],
            "additionalProperties": False,
        }
    }
}

# ── Prompts ─────────────────────────────────────────────────────

ANALYZE_SYSTEM_PROMPT = """You are an ODPS (MaxCompute) SQL analyst. Analyze SQL scripts to determine how they expand dimensions for reporting dashboards. ODPS SQL uses Alibaba Cloud MaxCompute dialect (similar to Hive SQL).

When given a SQL script and a new dimension name, you must:
1. Identify the expansion type: "cube" (GROUP BY CUBE), "lateral_view" (LATERAL VIEW EXPLODE), "group_by" (plain GROUP BY without CUBE or EXPLODE), or "unknown" if none found.
2. Parse all upstream source tables (tables referenced in FROM/JOIN clauses, excluding the INSERT OVERWRITE target table).
3. For each upstream table, determine how the dimension field relates to the current SQL output.
4. Identify any issues that would prevent adding the dimension.

Return a JSON object with:
- expansion_type: string ("cube", "lateral_view", "group_by", or "unknown")
- upstream_tables: array of objects with {table_name, alias, field_exists, via_select_star, suggested_source}
- issues: array of strings describing any problems"""

ANALYZE_USER_TEMPLATE = """Analyze this ODPS SQL for adding the dimension "{dimension_name}" (Chinese name: "{dimension_chinese_name}"):

```sql
{original_sql}
```"""

REWRITE_SYSTEM_PROMPT = """You are an ODPS (MaxCompute) SQL rewriting expert. Modify SQL scripts to add new dimension columns for reporting dashboards. ODPS SQL uses Alibaba Cloud MaxCompute dialect (similar to Hive SQL).

CRITICAL RULES for dimension addition:

1. For CUBE expansion (GROUP BY CUBE):
   - Add IF(grouping({dim}) = 0,{dim},'ALL') AS {dim} to the INNER SELECT that contains the GROUP BY CUBE clause, as the LAST item in the SELECT column list (after all existing columns, before FROM).
   - Add the plain column reference {dim} to the OUTERmost SELECT, as the LAST item (after all existing columns, before FROM).
   - Add {dim} to the GROUP BY CUBE(...) dimension list inside the parentheses.
   - Add {dim} to the OUTER GROUP BY clause.
   - Add {dim} STRING COMMENT '{chinese_name}' to the CREATE TABLE column definition as the LAST column (after all existing columns, before closing parenthesis).
   - PRESERVE all existing Chinese COMMENTs exactly as they appear in the original SQL. Do NOT modify, translate, or corrupt any existing COMMENT text.
   - Use the exact Chinese name provided for the new column's COMMENT. Do NOT use garbled or encoded text.

2. For LATERAL VIEW EXPLODE expansion:
   - Add the new dimension to the EXPLODE list in the LATERAL VIEW clause.
   - Add the dimension to the GROUP BY list.
   - Add the dimension to the SELECT column list.

3. For plain GROUP BY expansion:
   - Add {dim} AS {dim} to the SELECT column list as the LAST item (after all existing columns, including aggregate expressions, before FROM).
   - Add {dim} to the GROUP BY clause as the LAST item.
   - Add {dim} to the INSERT OVERWRITE TABLE column list if explicit columns are listed, as the LAST item.
   - Add {dim} STRING COMMENT '{chinese_name}' to the CREATE TABLE column definition as the LAST column.

BEFORE returning the modified_sql, VERIFY:
a) The new dimension column is the LAST item in EVERY SELECT list (inner AND outer)
b) The new dimension column is the LAST column in the CREATE TABLE definition
c) ALL existing Chinese COMMENTs are copied EXACTLY as-is from the original SQL
d) The new column's COMMENT uses the EXACT Chinese name provided: {chinese_name}
e) Do not invent, translate, encode, or repair Chinese COMMENT text yourself. The backend will enforce final COMMENT values after your rewrite.

Return a JSON object with:
- modified_sql: string (the complete rewritten SQL)
- alter_table_sql: string (ALTER TABLE ... ADD COLUMNS statement)
- changes_made: array of strings describing what was changed
- issues: array of strings describing any problems"""

REWRITE_USER_TEMPLATE = """Rewrite this ODPS SQL to add the dimension "{dimension_name}" (Chinese name: "{dimension_chinese_name}") with expansion_type="{expansion_type}":

```sql
{original_sql}
```"""

SELF_CHECK_SYSTEM_PROMPT = """You are an ODPS SQL correctness checker. Review the modified SQL to ensure it correctly adds the requested dimension without introducing errors.

Check for:
1. Correct dimension column added in all necessary places
2. GROUP BY CUBE or LATERAL VIEW EXPLODE properly updated
3. No missing commas or syntax errors
4. All referenced tables still properly joined
5. Column name conflicts avoided
6. All existing Chinese COMMENTs are PRESERVED exactly as in the original SQL (no corruption, no encoding issues)
7. The new column's COMMENT uses the correct Chinese name, not garbled text
8. New columns are placed at the END of SELECT lists and CREATE TABLE definitions, not inserted in the middle

Return a JSON object with:
- checks: object where each key is a check name and value is {pass: true/false, message: string}"""

SELF_CHECK_USER_TEMPLATE = """Check this modified SQL for correctness when adding dimension "{dimension_name}":

Original SQL:
```sql
{original_sql}
```

Modified SQL:
```sql
{modified_sql}
```

ALTER TABLE SQL:
```sql
{alter_sql}
```"""


# ── Helper functions ──────────────────────────────────────────────

def _parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response text."""
    try:
        # Try direct JSON parse
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from markdown code block
    match = re.search(r'```(?:json)?\n(.*?)\n```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Fallback: try to extract any JSON-like structure
    match = re.search(r'(\{.*\})', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"Could not parse JSON from response: {text[:200]}")


def _normalize_result(result) -> dict:
    """Normalize LLM result to dict."""
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        return _parse_json_response(result)
    raise ValueError(f"Unexpected result type: {type(result)}")


def _cache_key(sql: str, dimension_name: str, dimension_chinese_name: str = "") -> str:
    key_str = f"{sql}:{dimension_name}:{dimension_chinese_name}"
    return hashlib.md5(key_str.encode()).hexdigest()


def _extract_target_table(sql: str) -> str:
    match = re.search(r'INSERT\s+OVERWRITE\s+TABLE\s+(\S+)', sql, re.IGNORECASE)
    return match.group(1) if match else ""


# ── LLMClient ────────────────────────────────────────────────────

class LLMClient:
    def __init__(self, api_key: str, base_url: str = "",
                 analyze_model: str = OPENAI_MODEL,
                 rewrite_model: str = OPENAI_MODEL,
                 check_model: str = OPENAI_MODEL,
                 max_retries: int = OPENAI_MAX_RETRIES,
                 timeout: int = OPENAI_TIMEOUT):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.analyze_model = analyze_model
        self.rewrite_model = rewrite_model
        self.check_model = check_model
        self.max_retries = max_retries
        self.timeout = timeout

    def _call_openai(self, system_prompt: str, user_message: str,
                     model: str = None, tool: dict = None,
                     use_thinking: bool = False,
                     thinking_budget: int = 4000,
                     use_streaming: bool = False,
                     cache_key: str = None) -> dict:
        """Call OpenAI API with retry using requests.post directly."""
        import requests
        import time as _time
        _t0 = _time.time()
        
        # Check in-memory cache
        if cache_key and cache_key in _cache:
            logger.info(f"LLM cache hit: {cache_key[:40]}...")
            return _cache[cache_key]
        
        
        model = model or self.rewrite_model
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.3,
            "max_tokens": 4000,
        }
        
        _req_start = _time.time()
        logger.info(f"[LLM] REQUEST model={model} base_url={self.base_url} timeout={self.timeout}")
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.base_url + "/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                _latency = _time.time() - _req_start
                raw_text = data["choices"][0]["message"]["content"].strip()
                logger.info(f"[LLM] RESPONSE latency={_latency:.2f}s text_len={len(raw_text)}")
                result = _parse_json_response(raw_text)
                if cache_key:
                    _cache[cache_key] = result
                    logger.info(f"[LLM] CACHE saved: {cache_key[:40]}...")
                return result
                
            except requests.exceptions.HTTPError as e:
                if response.status_code in (400, 401, 403):
                    raise
                wait = 2 ** (attempt + 1)
                logger.warning(f"API error {response.status_code}, retrying in {wait}s")
                time.sleep(wait)
            except (requests.exceptions.RequestException, TimeoutError):
                wait = 2 ** (attempt + 1)
                logger.warning(f"Connection error, retrying in {wait}s")
                time.sleep(wait)
            except (KeyError, ValueError) as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Parse error: {e}, retrying (attempt {attempt+1})")
                    time.sleep(1)
                    continue
                raise

        raise RuntimeError(f"LLM call failed after {self.max_retries} retries")

    def analyze_sql(self, sql: str, dimension_name: str,
                    dimension_chinese_name: str = "") -> dict:
        user_msg = ANALYZE_USER_TEMPLATE.format(
            dimension_name=dimension_name,
            dimension_chinese_name=dimension_chinese_name,
            original_sql=sql,
        )
        key = _cache_key(sql, dimension_name, dimension_chinese_name)
        result = self._call_openai(
            ANALYZE_SYSTEM_PROMPT, user_msg,
            model=self.analyze_model,
            cache_key=key,
        )
        result = _normalize_result(result)
        
        valid_types = {"cube", "lateral_view", "group_by", "unknown"}
        if result.get("expansion_type") not in valid_types:
            result["expansion_type"] = "unknown"
        result.setdefault("upstream_tables", [])
        result.setdefault("issues", [])
        
        normalized_tables = []
        for t in result["upstream_tables"]:
            if isinstance(t, str):
                normalized_tables.append({"table_name": t})
            elif isinstance(t, dict):
                normalized_tables.append(t)
        result["upstream_tables"] = normalized_tables
        
        for t in result["upstream_tables"]:
            t.setdefault("alias", "")
            t.setdefault("field_exists", False)
            t.setdefault("via_select_star", False)
            t.setdefault("ddl_verified", False)
            t.setdefault("suggested_source", False)
            # Force coerce to bool in case LLM returns a string description
            sv = t.get("suggested_source")
            if not isinstance(sv, bool):
                t["suggested_source"] = False
        
        return result

    def rewrite_sql(self, sql: str, dimension_name: str,
                    dimension_chinese_name: str = "",
                    expansion_type: str = "group_by",
                    use_thinking: bool = False) -> dict:
        user_msg = REWRITE_USER_TEMPLATE.format(
            dimension_name=dimension_name,
            dimension_chinese_name=dimension_chinese_name,
            expansion_type=expansion_type,
            original_sql=sql,
        )
        system_prompt = REWRITE_SYSTEM_PROMPT.format(
            dim=dimension_name,
            chinese_name=dimension_chinese_name,
        )
        result = self._call_openai(
            system_prompt, user_msg,
            model=self.rewrite_model,
            use_thinking=use_thinking,
        )
        result = _normalize_result(result)
        
        if not result.get("modified_sql"):
            raise ValueError("LLM rewrite returned empty modified_sql")
        
        comment_part = f" COMMENT '{dimension_chinese_name}'" if dimension_chinese_name else ''
        result.setdefault("alter_table_sql",
                          f"ALTER TABLE {_extract_target_table(sql)} "
                          f"ADD COLUMNS ({dimension_name} STRING"
                          f"{comment_part});")
        result.setdefault("changes_made", [])
        result.setdefault("issues", [])
        return result

    def self_check(self, original_sql: str, modified_sql: str,
                   dimension_name: str, expansion_type: str,
                   alter_sql: str) -> dict:
        user_msg = SELF_CHECK_USER_TEMPLATE.format(
            original_sql=original_sql,
            modified_sql=modified_sql,
            dimension_name=dimension_name,
            expansion_type=expansion_type,
            alter_sql=alter_sql,
        )
        result = self._call_openai(
            SELF_CHECK_SYSTEM_PROMPT, user_msg,
            model=self.check_model,
        )
        result = _normalize_result(result)
        
        checks = result.get("checks", {})
        checks["all_pass"] = all(
            c.get("pass", True) for c in checks.values() if isinstance(c, dict)
        )
        return checks


# ── Singleton ────────────────────────────────────────────────────

_llm_client: Optional[LLMClient] = None


def _get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("Missing environment variable: OPENAI_API_KEY")
        _llm_client = LLMClient(OPENAI_API_KEY, OPENAI_BASE_URL)
    return _llm_client


# ── Convenience wrappers ────────────────────────────────────────

def llm_analyze(sql: str, dimension_name: str, dimension_chinese_name: str = "") -> dict:
    return _get_llm_client().analyze_sql(sql, dimension_name, dimension_chinese_name)


def llm_rewrite(sql: str, dimension_name: str, dimension_chinese_name: str = "",
                expansion_type: str = "group_by",
                use_thinking: bool = False) -> dict:
    return _get_llm_client().rewrite_sql(sql, dimension_name, dimension_chinese_name,
                                          expansion_type, use_thinking)


def llm_self_check(original_sql: str, modified_sql: str, dimension_name: str,
                   expansion_type: str, alter_sql: str) -> dict:
    return _get_llm_client().self_check(original_sql, modified_sql, dimension_name,
                                          expansion_type, alter_sql)


def llm_clear_cache():
    """Clear the result cache."""
    _cache.clear()
