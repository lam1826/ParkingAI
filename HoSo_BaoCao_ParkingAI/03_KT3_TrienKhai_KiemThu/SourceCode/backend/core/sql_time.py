"""Portable SQL time buckets for SQLite and PostgreSQL reporting queries."""

from sqlalchemy import String
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement


class _TimeBucket(FunctionElement):
    type = String()
    inherit_cache = True


class hour_bucket(_TimeBucket):
    inherit_cache = True


class day_bucket(_TimeBucket):
    inherit_cache = True


class week_bucket(_TimeBucket):
    inherit_cache = True


class month_bucket(_TimeBucket):
    inherit_cache = True


_SQLITE_FORMATS = {
    hour_bucket: "%H",
    day_bucket: "%Y-%m-%d",
    week_bucket: "%G-%V",
    month_bucket: "%Y-%m",
}
_POSTGRES_FORMATS = {
    hour_bucket: "HH24",
    day_bucket: "YYYY-MM-DD",
    week_bucket: "IYYY-IW",
    month_bucket: "YYYY-MM",
}


def _argument(element, compiler, **kwargs) -> str:
    return compiler.process(list(element.clauses)[0], **kwargs)


@compiles(_TimeBucket, "sqlite")
def _compile_sqlite(element, compiler, **kwargs):
    format_string = _SQLITE_FORMATS[type(element)]
    return f"strftime('{format_string}', {_argument(element, compiler, **kwargs)})"


@compiles(_TimeBucket, "postgresql")
def _compile_postgres(element, compiler, **kwargs):
    format_string = _POSTGRES_FORMATS[type(element)]
    return f"to_char({_argument(element, compiler, **kwargs)}, '{format_string}')"
