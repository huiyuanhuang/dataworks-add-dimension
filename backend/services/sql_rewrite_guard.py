"""Deterministic guardrails for LLM SQL rewrites.

The LLM is still responsible for semantic SQL expansion. This module enforces
mechanical invariants that should not depend on model behavior: COMMENT text
preservation and final-column placement for the newly added dimension.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class GuardResult:
    modified_sql: str
    alter_table_sql: str
    issues: List[str] = field(default_factory=list)


def guard_sql_rewrite(
    original_sql: str,
    modified_sql: str,
    alter_table_sql: str,
    dimension_name: str,
    dimension_chinese_name: str = "",
) -> GuardResult:
    """Normalize LLM output for comments, column order, and ALTER SQL."""
    issues: List[str] = []
    sql = modified_sql

    sql = _restore_comments(original_sql, sql, dimension_name, dimension_chinese_name)
    sql = _move_create_table_dimension_to_end(sql, dimension_name)
    sql = _move_insert_columns_dimension_to_end(sql, dimension_name)
    sql = _move_select_dimension_to_end(sql, dimension_name)
    sql = _move_group_by_cube_dimension_to_end(sql, dimension_name)
    sql = _move_group_by_dimension_to_end(sql, dimension_name)

    target_table = _extract_target_table(original_sql) or _extract_target_table(sql)
    normalized_alter = _build_alter_table_sql(target_table, dimension_name, dimension_chinese_name)
    if not target_table:
        issues.append("无法从 SQL 中识别目标表，ALTER TABLE SQL 可能需要人工确认")
        normalized_alter = alter_table_sql or normalized_alter

    issues.extend(_validate_expected_positions(sql, dimension_name))

    return GuardResult(modified_sql=sql, alter_table_sql=normalized_alter, issues=issues)


def _build_alter_table_sql(target_table: str, dimension_name: str, chinese_name: str) -> str:
    comment_part = f" COMMENT '{chinese_name}'" if chinese_name else ""
    if not target_table:
        target_table = "<target_table>"
    return f"ALTER TABLE {target_table} ADD COLUMNS ({dimension_name} STRING{comment_part});"


def _extract_target_table(sql: str) -> str:
    match = re.search(r"\bINSERT\s+OVERWRITE\s+TABLE\s+([^\s(]+)", sql, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)", sql, re.IGNORECASE)
    return match.group(1) if match else ""


def _restore_comments(original_sql: str, modified_sql: str, dimension_name: str, chinese_name: str) -> str:
    comments = _extract_column_comments(original_sql)
    if chinese_name:
        comments[dimension_name.lower()] = chinese_name
    if not comments:
        return modified_sql

    def repl(match: re.Match) -> str:
        prefix = match.group(1)
        col_name = _unquote_identifier(match.group(2)).lower()
        comment = comments.get(col_name)
        if comment is None:
            return match.group(0)
        return f"{prefix}COMMENT '{comment}'"

    pattern = re.compile(
        r"((?:^|[,\n]\s*)([`]?\w+[`]?)\s+[A-Za-z]\w*(?:\s*\([^)]*\))?\s+)"
        r"COMMENT\s+'[^']*'",
        re.IGNORECASE | re.MULTILINE,
    )
    return pattern.sub(repl, modified_sql)


def _extract_column_comments(sql: str) -> dict:
    comments = {}
    pattern = re.compile(
        r"(?:^|[,\n]\s*)([`]?\w+[`]?)\s+[A-Za-z]\w*(?:\s*\([^)]*\))?\s+COMMENT\s+'([^']*)'",
        re.IGNORECASE | re.MULTILINE,
    )
    for match in pattern.finditer(sql):
        comments[_unquote_identifier(match.group(1)).lower()] = match.group(2)
    return comments


def _unquote_identifier(identifier: str) -> str:
    return identifier.strip().strip("`")


def _ident_eq(left: str, right: str) -> bool:
    return _unquote_identifier(left).lower() == right.lower()


def _find_matching_paren(text: str, open_idx: int) -> int:
    depth = 0
    i = open_idx
    while i < len(text):
        state = _skip_quoted_or_comment(text, i)
        if state is not None:
            i = state
            continue
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _skip_quoted_or_comment(text: str, i: int) -> Optional[int]:
    if text.startswith("--", i):
        end = text.find("\n", i + 2)
        return len(text) if end == -1 else end + 1
    if text.startswith("/*", i):
        end = text.find("*/", i + 2)
        return len(text) if end == -1 else end + 2
    quote = text[i]
    if quote not in ("'", '"', "`"):
        return None
    j = i + 1
    while j < len(text):
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == quote:
            if quote == "'" and j + 1 < len(text) and text[j + 1] == "'":
                j += 2
                continue
            return j + 1
        j += 1
    return len(text)


def _split_top_level_commas(text: str) -> List[str]:
    parts = []
    start = 0
    depth = 0
    i = 0
    while i < len(text):
        state = _skip_quoted_or_comment(text, i)
        if state is not None:
            i = state
            continue
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return parts


def _join_items_like_original(items: List[str], original: str) -> str:
    clean = [item.strip() for item in items if item.strip()]
    if not clean:
        return original
    leading = re.match(r"\s*", original).group(0)
    trailing = re.search(r"\s*$", original).group(0)
    multiline_list = original.lstrip().startswith("\n") or original.count("\n") > 1
    if not multiline_list:
        return leading + _join_single_line_items(clean) + trailing
    if _uses_leading_comma_style(original):
        return _join_leading_comma_items(clean, original, leading, trailing)

    indent = "    "
    for item in items:
        match = re.match(r"(\s*)\S", item)
        if match and "\n" in match.group(1):
            indent = match.group(1).split("\n")[-1]
            break
        if match and match.group(1):
            indent = match.group(1)
            break
    return leading + (",\n".join(f"{indent}{item}" for item in clean)) + trailing


def _uses_leading_comma_style(original: str) -> bool:
    lines = original.splitlines()
    comma_lines = [line for line in lines[1:] if line.lstrip().startswith(",")]
    return len(comma_lines) >= 1


def _join_leading_comma_items(items: List[str], original: str, leading: str, trailing: str) -> str:
    lines = original.splitlines()
    first_indent = ""
    comma_indent = "    "
    for line in lines:
        if line.strip() and not line.lstrip().startswith(","):
            first_indent = re.match(r"\s*", line).group(0)
            break
    for line in lines:
        if line.lstrip().startswith(","):
            comma_indent = re.match(r"\s*", line).group(0)
            break

    rendered = [f"{first_indent}{items[0]}"]
    rendered.extend(f"{comma_indent},{item}" for item in items[1:])
    return leading + "\n".join(rendered) + trailing


def _join_single_line_items(items: List[str]) -> str:
    result = ""
    for item in items:
        if not result:
            result = item
            continue
        if "--" in result and "\n" not in result[result.rfind("--"):]:
            result += "\n, " + item
        else:
            result += ", " + item
    return result


def _move_matching_item_to_end(list_text: str, matcher) -> Tuple[str, bool]:
    items = _split_top_level_commas(list_text)
    matched = []
    others = []
    for item in items:
        if matcher(item):
            matched.append(item)
        else:
            others.append(item)
    if not matched:
        return list_text, False
    new_items = others + matched
    return _join_items_like_original(new_items, list_text), True


def _is_dimension_ddl_item(item: str, dimension_name: str) -> bool:
    match = re.match(r"\s*`?(\w+)`?\b", item)
    return bool(match and _ident_eq(match.group(1), dimension_name))


def _is_dimension_select_item(item: str, dimension_name: str) -> bool:
    stripped = item.strip()
    patterns = [
        rf"\bAS\s+`?{re.escape(dimension_name)}`?\s*(?:--.*)?$",
        rf"^`?{re.escape(dimension_name)}`?(?:\s*(?:--.*)?)?$",
        rf"\.`?{re.escape(dimension_name)}`?(?:\s*(?:--.*)?)?$",
    ]
    return any(re.search(pattern, stripped, re.IGNORECASE | re.DOTALL) for pattern in patterns)


def _is_dimension_group_item(item: str, dimension_name: str) -> bool:
    stripped = re.sub(r"--.*$", "", item.strip()).strip()
    return bool(re.fullmatch(rf"(?:\w+\.)?`?{re.escape(dimension_name)}`?", stripped, re.IGNORECASE))


def _move_create_table_dimension_to_end(sql: str, dimension_name: str) -> str:
    pattern = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[^\s(]+\s*\(", re.IGNORECASE)
    pos = 0
    result = []
    while True:
        match = pattern.search(sql, pos)
        if not match:
            result.append(sql[pos:])
            break
        open_idx = match.end() - 1
        close_idx = _find_matching_paren(sql, open_idx)
        if close_idx == -1:
            result.append(sql[pos:])
            break
        block = sql[open_idx + 1:close_idx]
        new_block, _ = _move_matching_item_to_end(block, lambda item: _is_dimension_ddl_item(item, dimension_name))
        result.append(sql[pos:open_idx + 1])
        result.append(new_block)
        pos = close_idx
    return "".join(result)


def _move_insert_columns_dimension_to_end(sql: str, dimension_name: str) -> str:
    pattern = re.compile(r"\bINSERT\s+OVERWRITE\s+TABLE\s+[^\s(]+\s*\(", re.IGNORECASE)
    pos = 0
    result = []
    while True:
        match = pattern.search(sql, pos)
        if not match:
            result.append(sql[pos:])
            break
        open_idx = match.end() - 1
        close_idx = _find_matching_paren(sql, open_idx)
        if close_idx == -1:
            result.append(sql[pos:])
            break
        block = sql[open_idx + 1:close_idx]
        new_block, _ = _move_matching_item_to_end(block, lambda item: _is_dimension_group_item(item, dimension_name))
        result.append(sql[pos:open_idx + 1])
        result.append(new_block)
        pos = close_idx
    return "".join(result)


def _move_select_dimension_to_end(sql: str, dimension_name: str) -> str:
    pos = 0
    result = []
    while True:
        select_match = _find_any_keyword(sql, "SELECT", pos)
        if select_match == -1:
            result.append(sql[pos:])
            break
        from_match = _find_keyword_same_level(sql, "FROM", select_match + len("SELECT"))
        if from_match == -1:
            result.append(sql[pos:])
            break
        select_list_start = select_match + len("SELECT")
        select_list = sql[select_list_start:from_match]
        new_list, _ = _move_matching_item_to_end(
            select_list, lambda item: _is_dimension_select_item(item, dimension_name)
        )
        result.append(sql[pos:select_list_start])
        result.append(new_list)
        pos = from_match
    return "".join(result)


def _find_any_keyword(text: str, keyword: str, start: int = 0) -> int:
    i = start
    pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
    while i < len(text):
        state = _skip_quoted_or_comment(text, i)
        if state is not None:
            i = state
            continue
        match = pattern.match(text, i)
        if match:
            return i
        i += 1
    return -1


def _find_keyword_same_level(text: str, keyword: str, start: int = 0) -> int:
    depth = 0
    i = start
    pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
    while i < len(text):
        state = _skip_quoted_or_comment(text, i)
        if state is not None:
            i = state
            continue
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        if depth == 0:
            match = pattern.match(text, i)
            if match:
                return i
        i += 1
    return -1


def _move_group_by_cube_dimension_to_end(sql: str, dimension_name: str) -> str:
    pattern = re.compile(r"\bGROUP\s+BY\s+CUBE\s*\(", re.IGNORECASE)
    pos = 0
    result = []
    while True:
        match = pattern.search(sql, pos)
        if not match:
            result.append(sql[pos:])
            break
        open_idx = match.end() - 1
        close_idx = _find_matching_paren(sql, open_idx)
        if close_idx == -1:
            result.append(sql[pos:])
            break
        block = sql[open_idx + 1:close_idx]
        new_block, _ = _move_matching_item_to_end(block, lambda item: _is_dimension_group_item(item, dimension_name))
        result.append(sql[pos:open_idx + 1])
        result.append(new_block)
        pos = close_idx
    return "".join(result)


def _move_group_by_dimension_to_end(sql: str, dimension_name: str) -> str:
    pos = 0
    result = []
    while True:
        group_idx = _find_group_by_not_cube(sql, pos)
        if group_idx == -1:
            result.append(sql[pos:])
            break
        list_start = group_idx + len(re.match(r"GROUP\s+BY", sql[group_idx:], re.IGNORECASE).group(0))
        list_end = _find_clause_end(sql, list_start)
        group_list = sql[list_start:list_end]
        new_list, _ = _move_matching_item_to_end(group_list, lambda item: _is_dimension_group_item(item, dimension_name))
        result.append(sql[pos:list_start])
        result.append(new_list)
        pos = list_end
    return "".join(result)


def _find_keyword(text: str, keyword: str, start: int = 0) -> int:
    depth = 0
    i = start
    pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
    while i < len(text):
        state = _skip_quoted_or_comment(text, i)
        if state is not None:
            i = state
            continue
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        if depth == 0:
            match = pattern.match(text, i)
            if match:
                return i
        i += 1
    return -1


def _find_group_by_not_cube(text: str, start: int = 0) -> int:
    pos = start
    pattern = re.compile(r"\bGROUP\s+BY\b", re.IGNORECASE)
    while True:
        idx = _find_any_keyword(text, "GROUP", pos)
        if idx == -1:
            return -1
        match = pattern.match(text, idx)
        if not match:
            pos = idx + len("GROUP")
            continue
        after = match.end()
        cube_match = re.match(r"\s+CUBE\b", text[after:], re.IGNORECASE)
        if cube_match:
            pos = after + cube_match.end()
            continue
        return idx


def _find_clause_end(text: str, start: int) -> int:
    clause_keywords = ("HAVING", "ORDER", "SORT", "DISTRIBUTE", "CLUSTER", "LIMIT", "UNION")
    depth = 0
    i = start
    while i < len(text):
        state = _skip_quoted_or_comment(text, i)
        if state is not None:
            i = state
            continue
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                return i
            depth -= 1
        elif ch == ";" and depth == 0:
            return i
        if depth == 0:
            for keyword in clause_keywords:
                if re.match(rf"\b{keyword}\b", text[i:], re.IGNORECASE):
                    return i
        i += 1
    return len(text)


def _validate_expected_positions(sql: str, dimension_name: str) -> List[str]:
    issues = []
    if re.search(r"\bCREATE\s+TABLE\b", sql, re.IGNORECASE) and not re.search(
        rf"(?:^|[,\n]\s*)`?{re.escape(dimension_name)}`?\s+[A-Za-z]",
        sql,
        re.IGNORECASE | re.MULTILINE,
    ):
        issues.append(f"改写后 CREATE TABLE 中未找到新增维度字段 '{dimension_name}'")
    if re.search(r"\bGROUP\s+BY\b", sql, re.IGNORECASE) and not re.search(
        rf"\bGROUP\s+BY\b[\s\S]*?\b{re.escape(dimension_name)}\b",
        sql,
        re.IGNORECASE,
    ):
        issues.append(f"改写后 GROUP BY 中未找到新增维度字段 '{dimension_name}'")
    if re.search(r"\bSELECT\b", sql, re.IGNORECASE) and not re.search(
        rf"\b(?:AS\s+)?`?{re.escape(dimension_name)}`?\b",
        sql,
        re.IGNORECASE,
    ):
        issues.append(f"改写后 SELECT 中未找到新增维度字段 '{dimension_name}'")
    return issues
