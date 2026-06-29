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
"""Enum and type definitions extracted from superset.utils.core."""

from __future__ import annotations

from enum import Enum, IntEnum
from typing import NamedTuple, TYPE_CHECKING, TypedDict

from flask import request
from sqlalchemy.types import TypeEngine

from superset.utils.backports import StrEnum

if TYPE_CHECKING:
    from superset.superset_typing import Column, FilterValues


class AdhocMetricExpressionType(StrEnum):
    """Expression type for adhoc metric definitions in the Explore view."""

    SIMPLE = "SIMPLE"
    SQL = "SQL"


class SqlExpressionType(StrEnum):
    """Types of SQL expressions that can be validated."""

    COLUMN = "column"
    METRIC = "metric"
    WHERE = "where"
    HAVING = "having"


class AnnotationType(StrEnum):
    """Annotation layer types supported by chart visualizations."""

    FORMULA = "FORMULA"
    INTERVAL = "INTERVAL"
    EVENT = "EVENT"
    TIME_SERIES = "TIME_SERIES"


class GenericDataType(IntEnum):
    """
    Generic database column type that fits both frontend and backend.
    """

    NUMERIC = 0
    STRING = 1
    TEMPORAL = 2
    BOOLEAN = 3
    # ARRAY = 4     # Mapping all the complex data types to STRING for now
    # JSON = 5      # and leaving these as a reminder.
    # MAP = 6
    # ROW = 7


class DatasourceType(StrEnum):
    """Identifier for the kind of datasource backing a chart or query."""

    TABLE = "table"
    DATASET = "dataset"
    QUERY = "query"
    SAVEDQUERY = "saved_query"
    VIEW = "view"
    SEMANTIC_VIEW = "semantic_view"


class LoggerLevel(StrEnum):
    """Log severity levels used by the Superset event logger."""

    INFO = "info"
    WARNING = "warning"
    EXCEPTION = "exception"


class HeaderDataType(TypedDict):
    """Typed dict for alert/report notification header metadata."""

    notification_format: str
    owners: list[int]
    notification_type: str
    notification_source: str | None
    chart_id: int | None
    dashboard_id: int | None
    slack_channels: list[str] | None
    execution_id: str | None


class DatasourceDict(TypedDict):
    """Minimal datasource reference used in query and chart payloads."""

    type: str  # todo(hugh): update this to be DatasourceType
    id: int | str


class AdhocFilterClause(TypedDict, total=False):
    """Typed dict representing a filter clause emitted by adhoc filter controls."""

    clause: str
    expressionType: str
    filterOptionName: str | None
    comparator: FilterValues | None
    operator: str
    subject: str
    isExtra: bool | None
    sqlExpression: str | None


class QueryObjectFilterClause(TypedDict, total=False):
    """Typed dict for a normalized filter clause within a QueryObject."""

    col: Column
    op: str  # pylint: disable=invalid-name
    val: FilterValues | None
    grain: str | None
    isExtra: bool | None


class ExtraFiltersTimeColumnType(StrEnum):
    TIME_COL = "__time_col"
    TIME_GRAIN = "__time_grain"
    TIME_ORIGIN = "__time_origin"
    TIME_RANGE = "__time_range"


class ExtraFiltersReasonType(StrEnum):
    NO_TEMPORAL_COLUMN = "no_temporal_column"
    COL_NOT_IN_DATASOURCE = "not_in_datasource"


class FilterOperator(StrEnum):
    """
    Operators used filter controls
    """

    EQUALS = "=="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_THAN_OR_EQUALS = ">="
    LESS_THAN_OR_EQUALS = "<="
    LIKE = "LIKE"
    NOT_LIKE = "NOT LIKE"
    ILIKE = "ILIKE"
    NOT_ILIKE = "NOT ILIKE"
    IS_NULL = "IS NULL"
    IS_NOT_NULL = "IS NOT NULL"
    IN = "IN"
    NOT_IN = "NOT IN"
    IS_TRUE = "IS TRUE"
    IS_FALSE = "IS FALSE"
    TEMPORAL_RANGE = "TEMPORAL_RANGE"


class FilterStringOperators(StrEnum):
    EQUALS = ("EQUALS",)
    NOT_EQUALS = ("NOT_EQUALS",)
    LESS_THAN = ("LESS_THAN",)
    GREATER_THAN = ("GREATER_THAN",)
    LESS_THAN_OR_EQUAL = ("LESS_THAN_OR_EQUAL",)
    GREATER_THAN_OR_EQUAL = ("GREATER_THAN_OR_EQUAL",)
    IN = ("IN",)
    NOT_IN = ("NOT_IN",)
    ILIKE = ("ILIKE",)
    LIKE = ("LIKE",)
    IS_NOT_NULL = ("IS_NOT_NULL",)
    IS_NULL = ("IS_NULL",)
    LATEST_PARTITION = ("LATEST_PARTITION",)
    IS_TRUE = ("IS_TRUE",)
    IS_FALSE = ("IS_FALSE",)


class PostProcessingBoxplotWhiskerType(StrEnum):
    """
    Calculate cell contribution to row/column total
    """

    TUKEY = "tukey"
    MINMAX = "min/max"
    PERCENTILE = "percentile"


class PostProcessingContributionOrientation(StrEnum):
    """
    Calculate cell contribution to row/column total
    """

    ROW = "row"
    COLUMN = "column"


class QuerySource(Enum):
    """
    The source of a SQL query.
    """

    CHART = 0
    DASHBOARD = 1
    SQL_LAB = 2


class QueryStatus(StrEnum):
    """Enum-type class for query statuses"""

    STOPPED = "stopped"
    FAILED = "failed"
    PENDING = "pending"
    RUNNING = "running"
    SCHEDULED = "scheduled"
    SUCCESS = "success"
    FETCHING = "fetching"
    TIMED_OUT = "timed_out"


class DashboardStatus(StrEnum):
    """Dashboard status used for frontend filters"""

    PUBLISHED = "published"
    DRAFT = "draft"


class ReservedUrlParameters(StrEnum):
    """
    Reserved URL parameters that are used internally by Superset. These will not be
    passed to chart queries, as they control the behavior of the UI.
    """

    STANDALONE = "standalone"
    EDIT_MODE = "edit"

    @staticmethod
    def is_standalone_mode() -> bool | None:
        standalone_param = request.args.get(ReservedUrlParameters.STANDALONE.value)
        standalone: bool | None = bool(
            standalone_param and standalone_param != "false" and standalone_param != "0"
        )
        return standalone


class RowLevelSecurityFilterType(StrEnum):
    REGULAR = "Regular"
    BASE = "Base"


class ColumnTypeSource(Enum):
    GET_TABLE = 1
    CURSOR_DESCRIPTION = 2


class ColumnSpec(NamedTuple):
    sqla_type: TypeEngine | str
    generic_type: GenericDataType
    is_dttm: bool
    python_date_format: str | None = None


class DatasourceName(NamedTuple):
    table: str
    schema: str
    catalog: str | None = None
