"""迁移 51：XLAB 项目场景赛道字段（2026-09-27，幂等）。

用法（项目根）：python scripts/migrate/migrate_51_showcase_track.py
回滚：ALTER TABLE showcase_project DROP COLUMN track;（升级前先备份）
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app import app  # noqa: E402,F401
from sqlalchemy import create_engine, inspect, text  # noqa: E402

import config  # noqa: E402

engine = create_engine(config.SQLALCHEMY_DATABASE_URI)


def migrate():
    inspector = inspect(engine)
    columns = [column['name'] for column in inspector.get_columns('showcase_project')]
    with engine.connect() as connection:
        if 'track' not in columns:
            connection.execute(text(
                "ALTER TABLE showcase_project "
                "ADD COLUMN track VARCHAR(30) NOT NULL DEFAULT 'other' AFTER tags"
            ))
            print("[+] showcase_project.track 已加列")
        else:
            print("[=] showcase_project.track 已存在")
        connection.execute(text(
            "UPDATE showcase_project SET track = 'other' "
            "WHERE track IS NULL OR track = ''"
        ))
        connection.commit()


if __name__ == '__main__':
    with app.app_context():
        migrate()
    print("migrate_51 完成")
