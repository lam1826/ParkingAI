from sqlalchemy import column, create_engine, literal, select
from sqlalchemy.dialects import postgresql, sqlite

from core.sql_time import day_bucket, hour_bucket, month_bucket, week_bucket


def _sql(expression, dialect) -> str:
    return str(select(expression).compile(dialect=dialect))


def test_time_buckets_compile_to_sqlite_strftime():
    dialect = sqlite.dialect()
    timestamp = column("check_in_time")
    assert "strftime('%H'" in _sql(hour_bucket(timestamp), dialect)
    assert "strftime('%Y-%m-%d'" in _sql(day_bucket(timestamp), dialect)
    assert "strftime('%G-%V'" in _sql(week_bucket(timestamp), dialect)
    assert "strftime('%Y-%m'" in _sql(month_bucket(timestamp), dialect)


def test_time_bucket_subclasses_explicitly_enable_sql_cache_keys():
    for bucket in (hour_bucket, day_bucket, week_bucket, month_bucket):
        assert bucket.__dict__["inherit_cache"] is True


def test_time_buckets_compile_to_postgres_to_char():
    dialect = postgresql.dialect()
    timestamp = column("check_in_time")
    assert "to_char(check_in_time, 'HH24')" in _sql(hour_bucket(timestamp), dialect)
    assert "to_char(check_in_time, 'YYYY-MM-DD')" in _sql(day_bucket(timestamp), dialect)
    assert "to_char(check_in_time, 'IYYY-IW')" in _sql(week_bucket(timestamp), dialect)
    assert "to_char(check_in_time, 'YYYY-MM')" in _sql(month_bucket(timestamp), dialect)


def test_sqlite_week_bucket_uses_iso_week_year_at_new_year_boundary():
    engine = create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            actual = connection.execute(
                select(week_bucket(literal("2021-01-01")))
            ).scalar_one()
    finally:
        engine.dispose()
    assert actual == "2020-53"
