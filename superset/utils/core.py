# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Utility functions used across Superset"""

from __future__ import annotations

import _thread
import collections
import errno
import logging
import os
import platform
import re
import signal
import tempfile
import threading
import traceback
import uuid
import zlib
from collections.abc import Iterable, Iterator, Sequence
from timeit import default_timer
from types import TracebackType
from typing import (
    Any,
    Callable,
    cast,
    Optional,
    TYPE_CHECKING,
    TypeVar,
)
from urllib.parse import unquote_plus

import pandas as pd
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import Certificate, load_pem_x509_certificate
from flask import current_app as app, request
from flask_appbuilder.security.sqla.models import User
from flask_babel import gettext as __
from pandas.api.types import infer_dtype
from typing_extensions import TypeGuard

from superset.constants import (
    DEFAULT_USER_AGENT,
    EXTRA_FORM_DATA_APPEND_KEYS,
    EXTRA_FORM_DATA_OVERRIDE_EXTRA_KEYS,
    EXTRA_FORM_DATA_OVERRIDE_REGULAR_MAPPINGS,
    NO_TIME_RANGE,
)
from superset.errors import ErrorLevel, SupersetErrorType
from superset.exceptions import (
    CertificateException,
    SupersetTimeoutException,
)
from superset.sql.parse import sanitize_clause
from superset.superset_typing import (
    AdhocColumn,
    AdhocMetric,
    AdhocMetricColumn,
    Column,
    FlaskResponse,
    FormData,
    Metric,
)

# ---------------------------------------------------------------------------
# Re-exports from focused submodules for backward compatibility.
# ---------------------------------------------------------------------------
from superset.utils.datetime_utils import (  # noqa: F401
    _process_datetime_column,
    DateColumn,
    DTTM_ALIAS,
    normalize_dttm_col,
)
from superset.utils.email import (  # noqa: F401
    recipients_string_to_list,
    send_email_smtp,
    send_mime_email,
)
from superset.utils.enums import (  # noqa: F401
    AdhocFilterClause,
    AdhocMetricExpressionType,
    AnnotationType,
    ColumnSpec,
    ColumnTypeSource,
    DashboardStatus,
    DatasourceDict,
    DatasourceName,
    DatasourceType,
    ExtraFiltersReasonType,
    ExtraFiltersTimeColumnType,
    FilterOperator,
    FilterStringOperators,
    GenericDataType,
    HeaderDataType,
    LoggerLevel,
    PostProcessingBoxplotWhiskerType,
    PostProcessingContributionOrientation,
    QueryObjectFilterClause,
    QuerySource,
    QueryStatus,
    ReservedUrlParameters,
    RowLevelSecurityFilterType,
    SqlExpressionType,
)
from superset.utils.hashing import hash_from_dict, hash_from_str
from superset.utils.sanitize import (  # noqa: F401
    markdown,
    sanitize_svg_content,
    sanitize_url,
)
from superset.utils.sql import (  # noqa: F401
    backend,
    generic_find_constraint_name,
    generic_find_fk_constraint_name,
    generic_find_fk_constraint_names,
    generic_find_uq_constraint_name,
    get_example_default_schema,
    LongText,
    MediumText,
    pessimistic_connection_handling,
)
from superset.utils.user import (  # noqa: F401
    get_user,
    get_user_email,
    get_user_id,
    get_username,
    override_user,
)
from superset.utils.zip import (  # noqa: F401
    check_is_safe_zip,
    create_zip,
)

if TYPE_CHECKING:
    from superset.explorables.base import ColumnMetadata, Explorable
    from superset.models.core import Database

logger = logging.getLogger(__name__)

TIME_COMPARISON = "__"

JS_MAX_INTEGER = 9007199254740991  # Largest int Java Script can handle 2^53-1

InputType = TypeVar("InputType")

ADHOC_FILTERS_REGEX = re.compile("^adhoc_filters")

TYPE_MAPPING = {
    re.compile(r"INT", re.IGNORECASE): "integer",
    re.compile(r"CHAR|TEXT|VARCHAR", re.IGNORECASE): "string",
    re.compile(r"DECIMAL|NUMERIC|FLOAT|DOUBLE", re.IGNORECASE): "floating",
    re.compile(r"BOOL", re.IGNORECASE): "boolean",
    re.compile(r"DATE|TIME", re.IGNORECASE): "datetime64",
}

METRIC_MAP_TYPE = {
    "SUM": "floating",
    "AVG": "floating",
    "COUNT": "floating",
    "COUNT_DISTINCT": "floating",
    "MIN": "numeric",
    "MAX": "numeric",
    "FIRST": "string",
    "LAST": "string",
    "GROUP_CONCAT": "string",
    "ARRAY_AGG": "string",
    "STRING_AGG": "string",
    "MEDIAN": "floating",
    "PERCENTILE": "floating",
    "VARIANCE": "floating",
    "STDDEV": "floating",
}


def parse_js_uri_path_item(
    item: str | None, unquote: bool = True, eval_undefined: bool = False
) -> str | None:
    """Parse an uri path item made with js.

    :param item: an uri path component
    :param unquote: Perform unquoting of string using urllib.parse.unquote_plus()
    :param eval_undefined: When set to True and item is either 'null' or 'undefined',
    assume item is undefined and return None.
    :return: Either None, the original item or unquoted item
    """
    item = None if eval_undefined and item in ("null", "undefined") else item
    return unquote_plus(item) if unquote and item else item


def cast_to_num(value: float | int | str | None) -> float | int | None:
    """Casts a value to an int/float

    >>> cast_to_num('1 ')
    1.0
    >>> cast_to_num(' 2')
    2.0
    >>> cast_to_num('5')
    5
    >>> cast_to_num('5.2')
    5.2
    >>> cast_to_num(10)
    10
    >>> cast_to_num(10.1)
    10.1
    >>> cast_to_num(None) is None
    True
    >>> cast_to_num('this is not a string') is None
    True

    :param value: value to be converted to numeric representation
    :returns: value cast to `int` if value is all digits, `float` if `value` is
              decimal value and `None`` if it can't be converted
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        return None


def cast_to_boolean(value: Any) -> bool | None:
    """Casts a value to an int/float

    >>> cast_to_boolean(1)
    True
    >>> cast_to_boolean(0)
    False
    >>> cast_to_boolean(0.5)
    True
    >>> cast_to_boolean('true')
    True
    >>> cast_to_boolean('false')
    False
    >>> cast_to_boolean('False')
    False
    >>> cast_to_boolean(None)

    :param value: value to be converted to boolean representation
    :returns: value cast to `bool`. when value is 'true' or value that are not 0
              converted into True. Return `None` if value is `None`
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def error_msg_from_exception(ex: Exception) -> str:
    """Translate exception into error message

    Database have different ways to handle exception. This function attempts
    to make sense of the exception object and construct a human readable
    sentence.

    TODO(bkyryliuk): parse the Presto error message from the connection
                     created via create_engine.
    engine = create_engine('presto://localhost:3506/silver') -
      gives an e.message as the str(dict)
    presto.connect('localhost', port=3506, catalog='silver') - as a dict.
    The latter version is parsed correctly by this function.
    """
    msg = ""
    if hasattr(ex, "message"):
        if isinstance(ex.message, dict):
            msg = ex.message.get("message")  # type: ignore
        elif ex.message:
            msg = ex.message
    return str(msg) or str(ex)


def readfile(file_path: str) -> str | None:
    """Read and return the entire contents of a file as a string."""
    with open(file_path) as f:
        content = f.read()
    return content


def get_datasource_full_name(
    database_name: str,
    datasource_name: str,
    catalog: str | None = None,
    schema: str | None = None,
) -> str:
    """Build a dot-separated, bracket-quoted fully qualified datasource name.

    Joins the non-``None`` parts into ``[database].[catalog].[schema].[table]``
    form, omitting any segment that is ``None``.

    :param database_name: Name of the database.
    :param datasource_name: Name of the table / datasource.
    :param catalog: Optional catalog name.
    :param schema: Optional schema name.
    :returns: Fully qualified datasource name, e.g. ``[mydb].[public].[mytable]``.
    """
    parts = [database_name, catalog, schema, datasource_name]
    return ".".join([f"[{part}]" for part in parts if part])


class SigalrmTimeout:
    """
    To be used in a ``with`` block and timeout its content.
    """

    def __init__(self, seconds: int = 1, error_message: str = "Timeout") -> None:
        self.seconds = seconds
        self.error_message = error_message

    def handle_timeout(self, signum: int, frame: Any) -> None:
        logger.error("Process timed out", exc_info=True)
        raise SupersetTimeoutException(
            error_type=SupersetErrorType.BACKEND_TIMEOUT_ERROR,
            message=self.error_message,
            level=ErrorLevel.ERROR,
            extra={"timeout": self.seconds},
        )

    def __enter__(self) -> None:
        try:
            if threading.current_thread() == threading.main_thread():
                signal.signal(signal.SIGALRM, self.handle_timeout)
                signal.alarm(self.seconds)
        except ValueError as ex:
            logger.warning("timeout can't be used in the current context")
            logger.exception(ex)

    def __exit__(self, type: Any, value: Any, traceback: TracebackType) -> None:
        try:
            signal.alarm(0)
        except ValueError as ex:
            logger.warning("timeout can't be used in the current context")
            logger.exception(ex)


class TimerTimeout:
    def __init__(self, seconds: int = 1, error_message: str = "Timeout") -> None:
        self.seconds = seconds
        self.error_message = error_message
        self.timer = threading.Timer(seconds, _thread.interrupt_main)

    def __enter__(self) -> None:
        self.timer.start()

    def __exit__(self, type: Any, value: Any, traceback: TracebackType) -> None:
        self.timer.cancel()
        if type is KeyboardInterrupt:  # raised by _thread.interrupt_main
            raise SupersetTimeoutException(
                error_type=SupersetErrorType.BACKEND_TIMEOUT_ERROR,
                message=self.error_message,
                level=ErrorLevel.ERROR,
                extra={"timeout": self.seconds},
            )


# Windows has no support for SIGALRM, so we use the timer based timeout
timeout: type[TimerTimeout] | type[SigalrmTimeout] = (
    TimerTimeout if platform.system() == "Windows" else SigalrmTimeout
)


def choicify(values: Iterable[Any]) -> list[tuple[Any, Any]]:
    """Takes an iterable and makes an iterable of tuples with it"""
    return [(v, v) for v in values]


def zlib_compress(data: bytes | str) -> bytes:
    """
    Compress things in a py2/3 safe fashion
    >>> json_str = '{"test": 1}'
    >>> blob = zlib_compress(json_str)
    """
    if isinstance(data, str):
        return zlib.compress(bytes(data, "utf-8"))
    return zlib.compress(data)


def zlib_decompress(blob: bytes, decode: bool | None = True) -> bytes | str:
    """
    Decompress things to a string in a py2/3 safe fashion
    >>> json_str = '{"test": 1}'
    >>> blob = zlib_compress(json_str)
    >>> got_str = zlib_decompress(blob)
    >>> got_str == json_str
    True
    """
    if isinstance(blob, bytes):
        decompressed = zlib.decompress(blob)
    else:
        decompressed = zlib.decompress(bytes(blob, "utf-8"))
    return decompressed.decode("utf-8") if decode else decompressed


def simple_filter_to_adhoc(
    filter_clause: QueryObjectFilterClause,
    clause: str = "where",
) -> AdhocFilterClause:
    result: AdhocFilterClause = {
        "clause": clause.upper(),
        "expressionType": "SIMPLE",
        "comparator": filter_clause.get("val"),
        "operator": filter_clause["op"],
        "subject": cast(str, filter_clause["col"]),
    }
    if filter_clause.get("isExtra"):
        result["isExtra"] = True
    result["filterOptionName"] = hash_from_dict(cast(dict[Any, Any], result))

    return result


def form_data_to_adhoc(form_data: dict[str, Any], clause: str) -> AdhocFilterClause:
    if clause not in ("where", "having"):
        raise ValueError(__("Unsupported clause type: %(clause)s", clause=clause))
    result: AdhocFilterClause = {
        "clause": clause.upper(),
        "expressionType": "SQL",
        "sqlExpression": form_data.get(clause),
    }
    result["filterOptionName"] = hash_from_dict(cast(dict[Any, Any], result))

    return result


def _update_existing_temporal_filter(
    temporal_filter: AdhocFilterClause,
    granularity_sqla_override: str | None,
    time_range: str | None,
    chart_has_granularity_sqla: bool,
) -> None:
    """Update an existing temporal filter with new subject/comparator."""
    if (
        granularity_sqla_override is not None
        and temporal_filter.get("expressionType") == "SIMPLE"
    ):
        temporal_filter["subject"] = granularity_sqla_override
    if time_range and not chart_has_granularity_sqla:
        temporal_filter["comparator"] = time_range


def _create_temporal_filter(
    granularity_sqla: str,
    time_range: str,
) -> AdhocFilterClause:
    """Create a new TEMPORAL_RANGE adhoc filter."""
    new_filter: AdhocFilterClause = {
        "clause": "WHERE",
        "expressionType": "SIMPLE",
        "operator": FilterOperator.TEMPORAL_RANGE,
        "subject": granularity_sqla,
        "comparator": time_range,
        "isExtra": True,
    }
    new_filter["filterOptionName"] = hash_from_dict(cast(dict[Any, Any], new_filter))
    return new_filter


def merge_extra_form_data(form_data: dict[str, Any]) -> None:  # noqa: C901
    """
    Merge extra form data (appends and overrides) into the main payload
    and add applied time extras to the payload.
    """
    filter_keys = ["filters", "adhoc_filters"]
    extra_form_data = form_data.pop("extra_form_data", {})
    append_filters: list[QueryObjectFilterClause] = extra_form_data.get("filters", None)

    # merge append extras
    for key in [key for key in EXTRA_FORM_DATA_APPEND_KEYS if key not in filter_keys]:
        extra_value = getattr(extra_form_data, key, {})
        form_value = getattr(form_data, key, {})
        form_value.update(extra_value)
        if form_value:
            form_data["key"] = extra_value

    # map regular extras that apply to form data properties
    for src_key, target_key in EXTRA_FORM_DATA_OVERRIDE_REGULAR_MAPPINGS.items():
        value = extra_form_data.get(src_key)
        if value is not None:
            form_data[target_key] = value

    # map extras that apply to form data extra properties
    extras = form_data.get("extras", {})
    for key in EXTRA_FORM_DATA_OVERRIDE_EXTRA_KEYS:
        value = extra_form_data.get(key)
        if value is not None:
            extras[key] = value
    if extras:
        form_data["extras"] = extras

    adhoc_filters: list[AdhocFilterClause] = form_data.get("adhoc_filters", [])
    form_data["adhoc_filters"] = adhoc_filters
    append_adhoc_filters: list[AdhocFilterClause] = extra_form_data.get(
        "adhoc_filters", []
    )
    adhoc_filters.extend(
        {"isExtra": True, **adhoc_filter} for adhoc_filter in append_adhoc_filters
    )
    if append_filters:
        for key, value in form_data.items():
            if re.match("adhoc_filter.*", key):
                value.extend(
                    simple_filter_to_adhoc({"isExtra": True, **fltr})
                    for fltr in append_filters
                    if fltr
                )

    granularity_sqla_override = extra_form_data.get("granularity_sqla")
    time_range = form_data.get("time_range")
    chart_has_granularity_sqla = bool(form_data.get("granularity_sqla"))

    temporal_filters = [
        adhoc_filter
        for adhoc_filter in adhoc_filters
        if adhoc_filter.get("operator") == FilterOperator.TEMPORAL_RANGE
    ]

    for temporal_filter in temporal_filters:
        _update_existing_temporal_filter(
            temporal_filter,
            granularity_sqla_override,
            time_range,
            chart_has_granularity_sqla,
        )

    if (
        not temporal_filters
        and granularity_sqla_override is not None
        and time_range is not None
    ):
        new_temporal_filter = _create_temporal_filter(
            granularity_sqla_override,
            cast(str, time_range),
        )
        adhoc_filters.append(new_temporal_filter)


def merge_extra_filters(form_data: dict[str, Any]) -> None:  # noqa: C901
    # extra_filters are temporary/contextual filters (using the legacy constructs)
    # that are external to the slice definition. We use those for dynamic
    # interactive filters.
    # Note extra_filters only support simple filters.
    form_data.setdefault("applied_time_extras", {})
    adhoc_filters = form_data.get("adhoc_filters", [])
    form_data["adhoc_filters"] = adhoc_filters
    merge_extra_form_data(form_data)
    if "extra_filters" in form_data:
        # __form and __to are special extra_filters that target time
        # boundaries. The rest of extra_filters are simple
        # [column_name in list_of_values]. `__` prefix is there to avoid
        # potential conflicts with column that would be named `from` or `to`
        date_options = {
            "__time_range": "time_range",
            "__time_col": "granularity_sqla",
            "__time_grain": "time_grain_sqla",
        }

        # Grab list of existing filters 'keyed' on the column and operator

        def get_filter_key(f: dict[str, Any]) -> str:
            if "expressionType" in f:
                return f"{f['subject']}__{f['operator']}"

            return f"{f['col']}__{f['op']}"

        existing_filters = {}
        for existing in adhoc_filters:
            if (
                existing["expressionType"] == "SIMPLE"
                and existing.get("comparator") is not None
                and existing.get("subject") is not None
            ):
                existing_filters[get_filter_key(existing)] = existing["comparator"]

        for filtr in form_data["extra_filters"]:
            filtr["isExtra"] = True
            # Pull out time filters/options and merge into form data
            filter_column = filtr["col"]
            if time_extra := date_options.get(filter_column):
                time_extra_value = filtr.get("val")
                if time_extra_value and time_extra_value != NO_TIME_RANGE:
                    form_data[time_extra] = time_extra_value
                    form_data["applied_time_extras"][filter_column] = time_extra_value
            elif filtr["val"]:
                # Merge column filters
                if (filter_key := get_filter_key(filtr)) in existing_filters:
                    # Check if the filter already exists
                    if isinstance(filtr["val"], list):
                        if isinstance(existing_filters[filter_key], list):
                            # Add filters for unequal lists
                            # order doesn't matter
                            if set(existing_filters[filter_key]) != set(filtr["val"]):
                                adhoc_filters.append(simple_filter_to_adhoc(filtr))
                        else:
                            adhoc_filters.append(simple_filter_to_adhoc(filtr))
                    else:
                        # Do not add filter if same value already exists
                        if filtr["val"] != existing_filters[filter_key]:
                            adhoc_filters.append(simple_filter_to_adhoc(filtr))
                else:
                    # Filter not found, add it
                    adhoc_filters.append(simple_filter_to_adhoc(filtr))
        # Remove extra filters from the form data since no longer needed
        del form_data["extra_filters"]


def merge_request_params(form_data: dict[str, Any], params: dict[str, Any]) -> None:
    """
    Merge request parameters to the key `url_params` in form_data. Only updates
    or appends parameters to `form_data` that are defined in `params; preexisting
    parameters not defined in params are left unchanged.

    :param form_data: object to be updated
    :param params: request parameters received via query string
    """
    url_params = form_data.get("url_params", {})
    for key, value in params.items():
        if key in ("form_data", "r"):
            continue
        url_params[key] = value
    form_data["url_params"] = url_params


def user_label(user: User) -> str | None:
    """Given a user ORM FAB object, returns a label"""
    if user:
        if user.first_name and user.last_name:
            return user.first_name + " " + user.last_name

        return user.username

    return None


def is_adhoc_metric(metric: Metric) -> TypeGuard[AdhocMetric]:
    return isinstance(metric, dict) and "expressionType" in metric


def is_adhoc_column(column: Column) -> TypeGuard[AdhocColumn]:
    return isinstance(column, dict) and ({"label", "sqlExpression"}).issubset(
        column.keys()
    )


def is_base_axis(column: Column) -> bool:
    return is_adhoc_column(column) and column.get("columnType") == "BASE_AXIS"


def get_base_axis_columns(columns: list[Column] | None) -> list[Column]:
    return [column for column in columns or [] if is_base_axis(column)]


def get_non_base_axis_columns(columns: list[Column] | None) -> list[Column]:
    return [column for column in columns or [] if not is_base_axis(column)]


def get_base_axis_labels(columns: list[Column] | None) -> tuple[str, ...]:
    return tuple(get_column_name(column) for column in get_base_axis_columns(columns))


def get_x_axis_label(columns: list[Column] | None) -> str | None:
    labels = get_base_axis_labels(columns)
    return labels[0] if labels else None


def get_column_name(column: Column, verbose_map: dict[str, Any] | None = None) -> str:
    """
    Extract label from column

    :param column: object to extract label from
    :param verbose_map: verbose_map from dataset for optional mapping from
                        raw name to verbose name
    :return: String representation of column
    :raises ValueError: if metric object is invalid
    """
    if hasattr(column, "column_name"):
        column_name = getattr(column, "column_name", "")
        verbose_name = getattr(column, "verbose_name", "")
        return verbose_name or column_name

    if isinstance(column, dict):
        if label := column.get("label"):
            return label
        if expr := column.get("sqlExpression"):
            return expr

    if isinstance(column, str):
        verbose_map = verbose_map or {}
        return verbose_map.get(column, column)

    raise ValueError("Missing label")


def get_metric_name(metric: Metric, verbose_map: dict[str, Any] | None = None) -> str:
    """
    Extract label from metric

    :param metric: object to extract label from
    :param verbose_map: verbose_map from dataset for optional mapping from
                        raw name to verbose name
    :return: String representation of metric
    :raises ValueError: if metric object is invalid
    """
    if is_adhoc_metric(metric):
        if label := metric.get("label"):
            return label
        if (expression_type := metric.get("expressionType")) == "SQL":
            if sql_expression := metric.get("sqlExpression"):
                return sql_expression
        if expression_type == "SIMPLE":
            column: AdhocMetricColumn = metric.get("column") or {}
            column_name = column.get("column_name")
            aggregate = metric.get("aggregate")
            if column and aggregate:
                return f"{aggregate}({column_name})"
            if column_name:
                return column_name

    if isinstance(metric, str):
        verbose_map = verbose_map or {}
        return verbose_map.get(metric, metric)

    raise ValueError(__("Invalid metric object: %(metric)s", metric=str(metric)))


def get_column_names(
    columns: Sequence[Column] | None,
    verbose_map: dict[str, Any] | None = None,
) -> list[str]:
    return [
        column
        for column in [get_column_name(column, verbose_map) for column in columns or []]
        if column
    ]


def get_metric_names(
    metrics: Sequence[Metric] | None,
    verbose_map: dict[str, Any] | None = None,
) -> list[str]:
    return [
        metric
        for metric in [get_metric_name(metric, verbose_map) for metric in metrics or []]
        if metric
    ]


def get_first_metric_name(
    metrics: Sequence[Metric] | None,
    verbose_map: dict[str, Any] | None = None,
) -> str | None:
    metric_labels = get_metric_names(metrics, verbose_map)
    return metric_labels[0] if metric_labels else None


def ensure_path_exists(path: str) -> None:
    try:
        os.makedirs(path)
    except OSError as ex:
        if not (os.path.isdir(path) and ex.errno == errno.EEXIST):
            raise


def convert_legacy_filters_into_adhoc(
    form_data: FormData,
) -> None:
    if not form_data.get("adhoc_filters"):
        adhoc_filters: list[AdhocFilterClause] = []
        form_data["adhoc_filters"] = adhoc_filters

        for clause in ("having", "where"):
            if clause in form_data and form_data[clause] != "":
                adhoc_filters.append(form_data_to_adhoc(form_data, clause))

        if "filters" in form_data:
            adhoc_filters.extend(
                simple_filter_to_adhoc(fltr, "where")
                for fltr in form_data["filters"]
                if fltr is not None
            )

    for key in ("filters", "having", "where"):
        if key in form_data:
            del form_data[key]


def split_adhoc_filters_into_base_filters(
    form_data: FormData,
    engine: str,
) -> None:
    """
    Mutates form data to restructure the adhoc filters in the form of the three base
    filters, `where`, `having`, and `filters` which represent free form where sql,
    free form having sql, and structured where clauses.
    """
    adhoc_filters = form_data.get("adhoc_filters")
    if isinstance(adhoc_filters, list):
        simple_where_filters = []
        sql_where_filters = []
        sql_having_filters = []
        for adhoc_filter in adhoc_filters:
            expression_type = adhoc_filter.get("expressionType")
            clause = adhoc_filter.get("clause")
            if expression_type == "SIMPLE":
                if clause == "WHERE":
                    simple_where_filters.append(
                        {
                            "col": adhoc_filter.get("subject"),
                            "op": adhoc_filter.get("operator"),
                            "val": adhoc_filter.get("comparator"),
                        }
                    )
            elif expression_type == "SQL":
                sql_expression = adhoc_filter.get("sqlExpression")
                sql_expression = sanitize_clause(sql_expression, engine)
                if clause == "WHERE":
                    sql_where_filters.append(sql_expression)
                elif clause == "HAVING":
                    sql_having_filters.append(sql_expression)
        form_data["where"] = " AND ".join([f"({sql})" for sql in sql_where_filters])
        form_data["having"] = " AND ".join([f"({sql})" for sql in sql_having_filters])
        form_data["filters"] = simple_where_filters


def parse_ssl_cert(certificate: str) -> Certificate:
    """
    Parses the contents of a certificate and returns a valid certificate object
    if valid.

    :param certificate: Contents of certificate file
    :return: Valid certificate instance
    :raises CertificateException: If certificate is not valid/unparseable
    """
    try:
        return load_pem_x509_certificate(certificate.encode("utf-8"), default_backend())
    except ValueError as ex:
        raise CertificateException("Invalid certificate") from ex


def create_ssl_cert_file(certificate: str) -> str:
    """
    This creates a certificate file that can be used to validate HTTPS
    sessions. A certificate is only written to disk once; on subsequent calls,
    only the path of the existing certificate is returned.

    :param certificate: The contents of the certificate
    :return: The path to the certificate file
    :raises CertificateException: If certificate is not valid/unparseable
    """
    filename = f"{hash_from_str(certificate)}.crt"
    cert_dir = app.config["SSL_CERT_PATH"]
    path = cert_dir if cert_dir else tempfile.gettempdir()
    path = os.path.join(path, filename)
    if not os.path.exists(path):
        # Validate certificate prior to persisting to temporary directory
        parse_ssl_cert(certificate)
        with open(path, "w") as cert_file:
            cert_file.write(certificate)
    return path


def time_function(
    func: Callable[..., FlaskResponse], *args: Any, **kwargs: Any
) -> tuple[float, Any]:
    """
    Measures the amount of time a function takes to execute in ms

    :param func: The function execution time to measure
    :param args: args to be passed to the function
    :param kwargs: kwargs to be passed to the function
    :return: A tuple with the duration and response from the function
    """
    start = default_timer()
    response = func(*args, **kwargs)
    stop = default_timer()
    return (stop - start) * 1000.0, response


def shortid() -> str:
    return f"{uuid.uuid4()}"[-12:]


def get_stacktrace() -> str | None:
    if app.config["SHOW_STACKTRACE"]:
        return traceback.format_exc()
    return None


def split(
    string: str, delimiter: str = " ", quote: str = '"', escaped_quote: str = r"\""
) -> Iterator[str]:
    """
    A split function that is aware of quotes and parentheses.

    :param string: string to split
    :param delimiter: string defining where to split, usually a comma or space
    :param quote: string, either a single or a double quote
    :param escaped_quote: string representing an escaped quote
    :return: list of strings
    """
    parens = 0
    quotes = False
    i = 0
    for j, character in enumerate(string):
        complete = parens == 0 and not quotes
        if complete and character == delimiter:
            yield string[i:j]
            i = j + len(delimiter)
        elif character == "(":
            parens += 1
        elif character == ")":
            parens -= 1
        elif character == quote:
            if quotes and string[j - len(escaped_quote) + 1 : j + 1] != escaped_quote:
                quotes = False
            elif not quotes:
                quotes = True
    yield string[i:]


T = TypeVar("T")


def as_list(x: T | list[T]) -> list[T]:
    """
    Wrap an object in a list if it's not a list.

    :param x: The object
    :returns: A list wrapping the object if it's not already a list
    """
    return x if isinstance(x, list) else [x]


def get_form_data_token(form_data: dict[str, Any]) -> str:
    """
    Return the token contained within form data or generate a new one.

    :param form_data: chart form data
    :return: original token if predefined, otherwise new uuid4 based token
    """
    return form_data.get("token") or "token_" + uuid.uuid4().hex[:8]


def get_column_name_from_column(column: Column) -> str | None:
    """
    Extract the physical column that a column is referencing. If the column is
    an adhoc column, always returns `None`.

    :param column: Physical and ad-hoc column
    :return: column name if physical column, otherwise None
    """
    if is_adhoc_column(column):
        return None
    return column  # type: ignore


def get_column_names_from_columns(columns: list[Column]) -> list[str]:
    """
    Extract the physical columns that a list of columns are referencing. Ignore
    adhoc columns

    :param columns: Physical and adhoc columns
    :return: column names of all physical columns
    """
    return [col for col in map(get_column_name_from_column, columns) if col]


def get_column_name_from_metric(metric: Metric) -> str | None:
    """
    Extract the column that a metric is referencing. If the metric isn't
    a simple metric, always returns `None`.

    :param metric: Ad-hoc metric
    :return: column name if simple metric, otherwise None
    """
    if is_adhoc_metric(metric):
        metric = cast(AdhocMetric, metric)
        if metric["expressionType"] == AdhocMetricExpressionType.SIMPLE:
            column = metric["column"]
            if column:
                return column["column_name"]
    return None


def get_column_names_from_metrics(metrics: list[Metric]) -> list[str]:
    """
    Extract the columns that a list of metrics are referencing. Excludes all
    SQL metrics.

    :param metrics: Ad-hoc metric
    :return: column name if simple metric, otherwise None
    """
    return [col for col in map(get_column_name_from_metric, metrics) if col]


def map_sql_type_to_inferred_type(sql_type: Optional[str]) -> str:
    """
    Map a SQL type to a type string recognized by pandas' `infer_objects` method.

    If the SQL type is not recognized, the function will return "string" as the
    default type.

    :param sql_type: SQL type to map
    :return: string type recognized by pandas
    """
    if not sql_type:
        return "string"  # If no SQL type is provided, return "string" as default

    # Use regular expressions to check the SQL type. The first match is returned.
    for pattern, inferred_type in TYPE_MAPPING.items():
        if pattern.search(sql_type):
            return inferred_type

    return "string"  # If no match is found, return "string" as default


def get_metric_type_from_column(column: Any, datasource: Explorable) -> str:
    """
    Determine the metric type from a given column in a datasource.

    This function checks if the specified column is a metric in the provided
    datasource. If it is, it extracts the SQL expression associated with the
    metric and attempts to identify the aggregation operation used within
    the expression (e.g., SUM, COUNT, etc.). It then maps the operation to
    a corresponding GenericDataType.

    :param column: The column name or identifier to check.
    :param datasource: The datasource containing metrics to search within.
    :return: The inferred metric type as a string, or an empty string if the
             column is not a metric or no valid operation is found.
    """
    metric = next(
        (m for m in datasource.metrics if m.metric_name == column),
        None,
    )

    if metric is None:
        return ""

    expression: str = metric.expression

    match = re.match(
        r"(SUM|AVG|COUNT|COUNT_DISTINCT|MIN|MAX|FIRST|LAST)\((.*)\)", expression
    )

    if match:
        operation = match.group(1)
        return METRIC_MAP_TYPE.get(operation, "")

    logger.warning("Unexpected metric expression type: %s", expression)
    return ""


def extract_dataframe_dtypes(
    df: pd.DataFrame,
    datasource: Explorable | None = None,
) -> list[GenericDataType]:
    """Serialize pandas/numpy dtypes to generic types"""

    # omitting string types as those will be the default type
    inferred_type_map: dict[str, GenericDataType] = {
        "floating": GenericDataType.NUMERIC,
        "integer": GenericDataType.NUMERIC,
        "mixed-integer-float": GenericDataType.NUMERIC,
        "decimal": GenericDataType.NUMERIC,
        "boolean": GenericDataType.BOOLEAN,
        "datetime64": GenericDataType.TEMPORAL,
        "datetime": GenericDataType.TEMPORAL,
        "date": GenericDataType.TEMPORAL,
    }

    columns_by_name: dict[str, Any] = {}
    if datasource:
        for column in datasource.columns:
            if isinstance(column, dict):
                if column_name := column.get("column_name"):
                    columns_by_name[column_name] = column
            else:
                columns_by_name[column.column_name] = column

    generic_types: list[GenericDataType] = []
    for column in df.columns:
        column_object = columns_by_name.get(str(column))
        series = df[column]
        inferred_type: str = ""
        if series.isna().all():
            sql_type: Optional[str] = ""
            if datasource and hasattr(datasource, "columns_types"):
                if column in datasource.columns_types:
                    sql_type = datasource.columns_types.get(column)
                    inferred_type = map_sql_type_to_inferred_type(sql_type)
                else:
                    inferred_type = get_metric_type_from_column(column, datasource)
        else:
            inferred_type = infer_dtype(series)
        if isinstance(column_object, dict):
            generic_type = (
                GenericDataType.TEMPORAL
                if column_object and column_object.get("is_dttm")
                else inferred_type_map.get(inferred_type, GenericDataType.STRING)
            )
        else:
            generic_type = (
                GenericDataType.TEMPORAL
                if column_object and column_object.is_dttm
                else inferred_type_map.get(inferred_type, GenericDataType.STRING)
            )
        generic_types.append(generic_type)

    return generic_types


def extract_column_dtype(col: ColumnMetadata) -> GenericDataType:
    # Check for temporal type
    if hasattr(col, "is_temporal") and col.is_temporal:
        return GenericDataType.TEMPORAL
    if col.is_dttm:
        return GenericDataType.TEMPORAL

    # Check for numeric type
    if hasattr(col, "is_numeric") and col.is_numeric:
        return GenericDataType.NUMERIC

    # TODO: add check for boolean data type when proper support is added
    return GenericDataType.STRING


def is_test() -> bool:
    return parse_boolean_string(os.environ.get("SUPERSET_TESTENV", "false"))


def get_time_filter_status(
    datasource: Explorable,
    applied_time_extras: dict[str, str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    temporal_columns: set[Any] = {
        col.column_name for col in datasource.columns if col.is_dttm
    }
    applied: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    if time_column := applied_time_extras.get(ExtraFiltersTimeColumnType.TIME_COL):
        if time_column in temporal_columns:
            applied.append({"column": ExtraFiltersTimeColumnType.TIME_COL})
        else:
            rejected.append(
                {
                    "reason": ExtraFiltersReasonType.COL_NOT_IN_DATASOURCE,
                    "column": ExtraFiltersTimeColumnType.TIME_COL,
                }
            )

    if ExtraFiltersTimeColumnType.TIME_GRAIN in applied_time_extras:
        # are there any temporal columns to assign the time grain to?
        if temporal_columns:
            applied.append({"column": ExtraFiltersTimeColumnType.TIME_GRAIN})
        else:
            rejected.append(
                {
                    "reason": ExtraFiltersReasonType.NO_TEMPORAL_COLUMN,
                    "column": ExtraFiltersTimeColumnType.TIME_GRAIN,
                }
            )

    if applied_time_extras.get(ExtraFiltersTimeColumnType.TIME_RANGE):
        # are there any temporal columns to assign the time range to?
        if temporal_columns:
            applied.append({"column": ExtraFiltersTimeColumnType.TIME_RANGE})
        else:
            rejected.append(
                {
                    "reason": ExtraFiltersReasonType.NO_TEMPORAL_COLUMN,
                    "column": ExtraFiltersTimeColumnType.TIME_RANGE,
                }
            )

    return applied, rejected


def format_list(items: Sequence[str], sep: str = ", ", quote: str = '"') -> str:
    quote_escaped = "\\" + quote
    return sep.join(f"{quote}{x.replace(quote, quote_escaped)}{quote}" for x in items)


def find_duplicates(items: Iterable[InputType]) -> list[InputType]:
    """Find duplicate items in an iterable."""
    return [item for item, count in collections.Counter(items).items() if count > 1]


def remove_duplicates(
    items: Iterable[InputType], key: Callable[[InputType], Any] | None = None
) -> list[InputType]:
    """Remove duplicate items in an iterable."""
    if not key:
        return list(dict.fromkeys(items).keys())
    seen = set()
    result = []
    for item in items:
        item_key = key(item)
        if item_key not in seen:
            seen.add(item_key)
            result.append(item)
    return result


def parse_boolean_string(bool_str: str | None) -> bool:
    """
    Convert a string representation of a true/false value into a boolean

    >>> parse_boolean_string(None)
    False
    >>> parse_boolean_string('false')
    False
    >>> parse_boolean_string('true')
    True
    >>> parse_boolean_string('False')
    False
    >>> parse_boolean_string('True')
    True
    >>> parse_boolean_string('foo')
    False
    >>> parse_boolean_string('0')
    False
    >>> parse_boolean_string('1')
    True

    :param bool_str: string representation of a value that is assumed to be boolean
    :return: parsed boolean value
    """
    if bool_str is None:
        return False
    return bool_str.lower() in ("y", "Y", "yes", "True", "t", "true", "On", "on", "1")


def apply_max_row_limit(
    limit: int,
    server_pagination: bool | None = None,
) -> int:
    """
    Override row limit based on server pagination setting

    :param limit: requested row limit
    :param server_pagination: whether server-side pagination
    is enabled, defaults to None
    :return: Capped row limit

    >>> apply_max_row_limit(600000, server_pagination=True)  # Server pagination
    500000
    >>> apply_max_row_limit(600000, server_pagination=False)  # No pagination
    50000
    >>> apply_max_row_limit(5000)  # No server_pagination specified
    5000
    >>> apply_max_row_limit(0)  # Zero returns default max limit
    50000
    """
    max_limit = (
        app.config["TABLE_VIZ_MAX_ROW_SERVER"]
        if server_pagination
        else app.config["SQL_MAX_ROW"]
    )
    if limit != 0:
        return min(max_limit, limit)
    return max_limit


def remove_extra_adhoc_filters(form_data: dict[str, Any]) -> None:
    """
    Remove filters from slice data that originate from a filter box or native filter
    """
    adhoc_filters = {
        key: value for key, value in form_data.items() if ADHOC_FILTERS_REGEX.match(key)
    }
    for key, value in adhoc_filters.items():
        form_data[key] = [
            filter_ for filter_ in value or [] if not filter_.get("isExtra")
        ]


def to_int(v: Any, value_if_invalid: int = 0) -> int:
    try:
        return int(v)
    except (ValueError, TypeError):
        return value_if_invalid


def get_query_source_from_request() -> QuerySource | None:
    if not request or not request.referrer:
        return None
    if "/superset/dashboard/" in request.referrer:
        return QuerySource.DASHBOARD
    if "/explore/" in request.referrer:
        return QuerySource.CHART
    if "/sqllab/" in request.referrer:
        return QuerySource.SQL_LAB
    return None


def get_user_agent(database: Database, source: QuerySource | None) -> str:
    source = source or get_query_source_from_request()
    if user_agent_func := app.config["USER_AGENT_FUNC"]:
        return user_agent_func(database, source)

    return DEFAULT_USER_AGENT
