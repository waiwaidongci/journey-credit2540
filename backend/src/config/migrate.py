from sqlalchemy import inspect,text
# 首次建表由ORM metadata完成；这里只补既有库缺失的列，保持幂等，结构变化仍需审查迁移目录。
def ensure_schema(engine):
    tables=inspect(engine).get_table_names()
    if "journeys" not in tables:return
    columns={c["name"] for c in inspect(engine).get_columns("journeys")}
    with engine.begin() as c:
        if "revision" not in columns:c.execute(text("ALTER TABLE journeys ADD COLUMN revision INTEGER NOT NULL DEFAULT 1"))
        if "withdrawn" not in columns:c.execute(text("ALTER TABLE journeys ADD COLUMN withdrawn BOOLEAN NOT NULL DEFAULT FALSE"))
