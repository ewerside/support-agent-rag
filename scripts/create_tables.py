"""Create the schema, tables and search function from sql/schema.sql. Run: python -m scripts.create_tables"""

import psycopg

import config

SCHEMA_SQL = config.ROOT / "sql" / "schema.sql"


def main() -> None:
    with psycopg.connect(config.DATABASE_URL, connect_timeout=10) as conn:
        # No parameters, so psycopg sends the whole file as one script.
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        tables = conn.execute(
            "select table_name from information_schema.tables "
            "where table_schema = 'support_agent' order by 1"
        ).fetchall()
        functions = conn.execute(
            "select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'support_agent' order by 1"
        ).fetchall()
    print("tables:", ", ".join(t[0] for t in tables))
    print("functions:", ", ".join(f[0] for f in functions))


if __name__ == "__main__":
    main()
