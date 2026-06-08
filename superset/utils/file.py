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
"""Filename helpers for model export artefacts."""

from werkzeug.utils import secure_filename


def get_filename(model_name: str, model_id: int, skip_id: bool = False) -> str:
    """Build a safe, filesystem-friendly filename for a model export.

    :param model_name: Human-readable model name (sanitised via
        :func:`werkzeug.utils.secure_filename`).
    :param model_id: Numeric identifier appended to the slug unless
        *skip_id* is ``True``.
    :param skip_id: When ``True``, omit the numeric suffix.
    :returns: A sanitised filename string.  Falls back to ``str(model_id)``
        when the sanitised slug is empty.
    """
    slug = secure_filename(model_name)
    filename = slug if skip_id else f"{slug}_{model_id}"
    return filename if slug else str(model_id)
