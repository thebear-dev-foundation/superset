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
"""Datetime utility functions extracted from superset.utils.core."""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from datetime import timedelta

import pandas as pd
from pandas.core.dtypes.common import is_numeric_dtype

from superset.utils.date_parser import parse_human_timedelta
from superset.utils.pandas import detect_datetime_format

logger = logging.getLogger(__name__)

DTTM_ALIAS = "__timestamp"


@dataclass
class DateColumn:
    """Metadata for a date/time column used in query result post-processing."""

    col_label: str
    timestamp_format: str | None = None
    offset: int | None = None
    time_shift: str | None = None

    def __hash__(self) -> int:
        """Return a hash derived from the column label."""
        return hash(self.col_label)

    def __eq__(self, other: object) -> bool:
        """Return whether ``other`` is a ``DateColumn`` with the same label."""
        return isinstance(other, DateColumn) and hash(self) == hash(other)

    @classmethod
    def get_legacy_time_column(
        cls,
        timestamp_format: str | None,
        offset: int | None,
        time_shift: str | None,
    ) -> DateColumn:
        """Build a ``DateColumn`` using the legacy ``__timestamp`` alias."""
        return cls(
            timestamp_format=timestamp_format,
            offset=offset,
            time_shift=time_shift,
            col_label=DTTM_ALIAS,
        )


def _process_datetime_column(
    df: pd.DataFrame,
    col: DateColumn,
) -> None:
    """Process a single datetime column with format detection."""
    if col.timestamp_format in ("epoch_s", "epoch_ms"):
        dttm_series = df[col.col_label]
        if is_numeric_dtype(dttm_series):
            # Column is formatted as a numeric value
            unit = col.timestamp_format.replace("epoch_", "")
            df[col.col_label] = pd.to_datetime(
                dttm_series,
                utc=False,
                unit=unit,
                origin="unix",
                errors="coerce",
                exact=False,
            )
        else:
            # Column has already been formatted as a timestamp.
            try:
                df[col.col_label] = dttm_series.apply(
                    lambda x: pd.Timestamp(x) if pd.notna(x) else pd.NaT
                )
            except ValueError:
                logger.warning(
                    "Unable to convert column %s to datetime, ignoring",
                    col.col_label,
                )
    else:
        # Try to detect format if not specified
        format_to_use = col.timestamp_format or detect_datetime_format(
            df[col.col_label]
        )

        # Parse with or without format (suppress warning if no format)
        if format_to_use:
            df[col.col_label] = pd.to_datetime(
                df[col.col_label],
                utc=False,
                format=format_to_use,
                errors="coerce",
                exact=False,
            )
        else:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*Could not infer format.*")
                df[col.col_label] = pd.to_datetime(
                    df[col.col_label],
                    utc=False,
                    format=None,
                    errors="coerce",
                    exact=False,
                )


def normalize_dttm_col(
    df: pd.DataFrame,
    dttm_cols: tuple[DateColumn, ...] = tuple(),  # noqa: C408
    format_map: dict[str, str] | None = None,
) -> None:
    """
    Normalize datetime columns in a DataFrame.

    :param df: DataFrame to process
    :param dttm_cols: Tuple of DateColumn objects to process
    :param format_map: Optional mapping of column names to datetime formats.
                       When provided, these pre-detected formats are used instead
                       of runtime detection, improving performance and consistency.
    """
    for _col in dttm_cols:
        if _col.col_label not in df.columns:
            continue

        # Use format from format_map if available and not already set
        if format_map and _col.col_label in format_map and not _col.timestamp_format:
            _col.timestamp_format = format_map[_col.col_label]

        _process_datetime_column(df, _col)

        if _col.offset:
            df[_col.col_label] += timedelta(hours=_col.offset)
        if _col.time_shift is not None:
            df[_col.col_label] += parse_human_timedelta(_col.time_shift)
