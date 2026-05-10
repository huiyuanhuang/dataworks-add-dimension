import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.sql_rewrite_guard import guard_sql_rewrite


def test_restores_existing_chinese_comments_and_sets_new_dimension_comment():
    original_sql = """
CREATE TABLE ads_demo (
    country STRING COMMENT '国家',
    uv BIGINT COMMENT '活跃用户'
);
"""
    modified_sql = """
CREATE TABLE ads_demo (
    country STRING COMMENT 'å›½å®¶',
    uv BIGINT COMMENT 'æ´»è·ƒç”¨æˆ·',
    app_version STRING COMMENT 'garbled'
);
SELECT country, app_version, uv FROM src GROUP BY country, app_version;
"""

    result = guard_sql_rewrite(
        original_sql=original_sql,
        modified_sql=modified_sql,
        alter_table_sql="",
        dimension_name="app_version",
        dimension_chinese_name="应用版本",
    )

    assert "country STRING COMMENT '国家'" in result.modified_sql
    assert "uv BIGINT COMMENT '活跃用户'" in result.modified_sql
    assert "app_version STRING COMMENT '应用版本'" in result.modified_sql
    assert result.alter_table_sql == "ALTER TABLE ads_demo ADD COLUMNS (app_version STRING COMMENT '应用版本');"


def test_moves_new_dimension_to_end_of_create_table_select_and_group_by_lists():
    original_sql = "CREATE TABLE ads_demo (country STRING COMMENT '国家', uv BIGINT COMMENT '活跃用户');"
    modified_sql = """
CREATE TABLE ads_demo (
    country STRING COMMENT '国家',
    app_version STRING COMMENT 'bad',
    uv BIGINT COMMENT '活跃用户'
);
INSERT OVERWRITE TABLE ads_demo(country, app_version, uv)
SELECT country, app_version, sum(uv) AS uv
FROM (
    SELECT country, app_version, uv
    FROM src
    GROUP BY country, app_version, uv
) t
GROUP BY country, app_version;
"""

    result = guard_sql_rewrite(
        original_sql=original_sql,
        modified_sql=modified_sql,
        alter_table_sql="",
        dimension_name="app_version",
        dimension_chinese_name="应用版本",
    )

    assert "country STRING COMMENT '国家',\n    uv BIGINT COMMENT '活跃用户',\n    app_version STRING COMMENT '应用版本'" in result.modified_sql
    assert "INSERT OVERWRITE TABLE ads_demo(country, uv, app_version)" in result.modified_sql
    assert "SELECT country, sum(uv) AS uv, app_version\nFROM (" in result.modified_sql
    assert "SELECT country, uv, app_version\n    FROM src" in result.modified_sql
    assert "GROUP BY country, uv, app_version" in result.modified_sql
    assert "GROUP BY country, app_version;" in result.modified_sql


def test_moves_new_dimension_to_end_of_group_by_cube_without_splitting_nested_commas():
    original_sql = "CREATE TABLE ads_demo (country STRING COMMENT '国家', uv BIGINT COMMENT '活跃用户');"
    modified_sql = """
CREATE TABLE ads_demo (
    country STRING COMMENT '国家',
    uv BIGINT COMMENT '活跃用户',
    app_version STRING COMMENT '应用版本'
);
SELECT country, app_version, concat(country, ',', 'x') AS label, sum(uv) AS uv -- keep, comma
FROM src
GROUP BY CUBE(country, app_version, concat(country, ',', 'x'));
"""

    result = guard_sql_rewrite(
        original_sql=original_sql,
        modified_sql=modified_sql,
        alter_table_sql="",
        dimension_name="app_version",
        dimension_chinese_name="应用版本",
    )

    assert "SELECT country, concat(country, ',', 'x') AS label, sum(uv) AS uv -- keep, comma\n, app_version\nFROM src" in result.modified_sql
    assert "GROUP BY CUBE(country, concat(country, ',', 'x'), app_version)" in result.modified_sql


def test_preserves_leading_comma_style_without_merging_dimension_with_from():
    original_sql = """
CREATE TABLE IF NOT EXISTS dwr_spock_test2_1d
(
    cou          STRING COMMENT '国家'
    ,ver         STRING COMMENT '版本'
    ,cha         STRING COMMENT '渠道'
    ,active_uv   BIGINT COMMENT '日活UV'
    ,online_time DOUBLE COMMENT '总在线时长'
)
;
"""
    modified_sql = """
CREATE TABLE IF NOT EXISTS dwr_spock_test2_1d
(
    cou          STRING COMMENT '国家'
    ,ver         STRING COMMENT '版本'
    ,cha         STRING COMMENT '渠道'
    ,active_uv   BIGINT COMMENT '日活UV'
    ,online_time DOUBLE COMMENT '总在线时长'
    ,sub STRING COMMENT '子渠道'
)
;
SELECT  cou
        ,ver
        ,cha
        ,SUM(IF(active_pv > 0,1,0)) AS active_uv
        ,SUM(IF(online_time < 43200,online_time,0)) AS online_time
        ,sub
FROM    (
            SELECT  union_key
                    ,IF(grouping(cou) = 0,cou,'ALL') AS cou
                    ,IF(grouping(ver) = 0,ver,'ALL') AS ver
                    ,IF(grouping(cha) = 0,cha,'ALL') AS cha
                    ,SUM(active_pv) AS active_pv
                    ,SUM(online_time) AS online_time
                    ,IF(grouping(sub) = 0,sub,'ALL') AS sub
            FROM    src
            GROUP BY CUBE(cou,ver,cha,sub)
                     ,union_key
        ) t4
GROUP BY cou
         ,ver
         ,cha
         ,sub
;
"""

    result = guard_sql_rewrite(
        original_sql=original_sql,
        modified_sql=modified_sql,
        alter_table_sql="",
        dimension_name="sub",
        dimension_chinese_name="子渠道",
    )

    assert "subFROM" not in result.modified_sql
    assert "AS sub\n            FROM    src" in result.modified_sql
    assert "        ,sub\nFROM    (" in result.modified_sql
    assert "GROUP BY CUBE(cou, ver, cha, sub)" in result.modified_sql
    assert result.issues == []
