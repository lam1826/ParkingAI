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
    argument = _argument(element, compiler, **kwargs)
    if isinstance(element, week_bucket):
        # SQLite only added %G/%V in 3.46.0. Python 3.12 runners and many
        # supported deployments still bundle an older SQLite where those
        # format tokens return NULL. Move to the ISO week's Thursday using
        # long-supported date modifiers, then derive the ISO year/week.
        iso_thursday = f"date({argument}, '-3 days', 'weekday 4')"
        return (
            f"strftime('%Y', {iso_thursday}) || '-' || "
            f"printf('%02d', "
            f"(CAST(strftime('%j', {iso_thursday}) AS INTEGER) - 1) / 7 + 1"
            f")"
        )
    format_string = _SQLITE_FORMATS[type(element)]
    return f"strftime('{format_string}', {argument})"


@compiles(_TimeBucket, "postgresql")
def _compile_postgres(element, compiler, **kwargs):
    format_string = _POSTGRES_FORMATS[type(element)]
    return f"to_char({_argument(element, compiler, **kwargs)}, '{format_string}')"
