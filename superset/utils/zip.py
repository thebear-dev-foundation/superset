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
"""Zip utility functions extracted from superset.utils.core."""

from __future__ import annotations

from io import BytesIO
from typing import Any
from zipfile import ZipFile

from flask import current_app as app

from superset.exceptions import SupersetException


def create_zip(files: dict[str, Any]) -> BytesIO:
    """Create an in-memory ZIP archive from a mapping of filenames to contents.

    :param files: Dict mapping archive member names to their byte contents.
    :returns: A seeked-to-start :class:`BytesIO` containing the ZIP data.
    """
    buf = BytesIO()
    with ZipFile(buf, "w") as bundle:
        for filename, contents in files.items():
            with bundle.open(filename, "w") as fp:
                fp.write(contents)
    buf.seek(0)
    return buf


def check_is_safe_zip(zip_file: ZipFile) -> None:
    """
    Checks whether a ZIP file is safe, raises SupersetException if not.

    :param zip_file:
    :return:
    """
    # pylint: disable=import-outside-toplevel

    uncompress_size = 0
    compress_size = 0
    for zip_file_element in zip_file.infolist():
        if zip_file_element.file_size > app.config["ZIPPED_FILE_MAX_SIZE"]:
            raise SupersetException("Found file with size above allowed threshold")
        uncompress_size += zip_file_element.file_size
        compress_size += zip_file_element.compress_size
    if compress_size == 0:
        return
    compress_ratio = uncompress_size / compress_size
    if compress_ratio > app.config["ZIP_FILE_MAX_COMPRESS_RATIO"]:
        raise SupersetException("Zip compress ratio above allowed threshold")
