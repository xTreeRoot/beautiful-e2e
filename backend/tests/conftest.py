from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL, make_url

from app.core.config import get_settings
from app.db import Base


def _mysql_test_database_url() -> URL:
    """基于当前 MySQL 配置生成隔离测试库地址。

    测试库固定追加 `_test` 后缀，避免清表和建表操作影响本地开发库。
    """
    url = make_url(get_settings().database_url)
    if not url.drivername.startswith("mysql"):
        pytest.fail("后端测试需要配置 MySQL DATABASE_URL，当前配置不是 MySQL。")
    if not url.database:
        pytest.fail("DATABASE_URL 必须包含数据库名，才能派生隔离测试库。")

    test_database = f"{url.database}_test"
    admin_engine = create_engine(url.set(database=None), pool_pre_ping=True)
    try:
        with admin_engine.begin() as connection:
            connection.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{test_database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                )
            )
    finally:
        admin_engine.dispose()

    return url.set(database=test_database)


@pytest.fixture()
def mysql_engine() -> Iterator[Engine]:
    """提供每个测试独立重建表结构的 MySQL 引擎。"""
    engine = create_engine(_mysql_test_database_url(), pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
