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

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any, Callable

import backoff


def retry_call(  # pylint: disable=too-many-arguments
    func: Callable[..., Any],
    *args: Any,
    strategy: Callable[..., Generator[int, None, None]] = backoff.constant,
    exception: type[Exception] = Exception,
    giveup_log_level: int = logging.WARNING,
    fargs: list[Any] | None = None,
    fkwargs: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Retry *func* with exponential/constant back-off via the ``backoff`` library.

    Wraps ``func`` with :pyfunc:`backoff.on_exception` using the given
    ``strategy`` and ``exception`` type, then invokes it with the supplied
    positional and keyword arguments.

    :param func: The callable to retry on failure.
    :param args: Extra positional arguments forwarded to ``backoff.on_exception``.
    :param strategy: Back-off wait generator (default: ``backoff.constant``).
    :param exception: Exception type (or tuple) that triggers a retry.
    :param giveup_log_level: Log level used when retries are exhausted.
    :param fargs: Positional arguments passed to *func* on each attempt.
    :param fkwargs: Keyword arguments passed to *func* on each attempt.
    :param kwargs: Extra keyword arguments forwarded to ``backoff.on_exception``.
    :returns: The return value of a successful *func* invocation.
    """
    kwargs["giveup_log_level"] = giveup_log_level
    decorated = backoff.on_exception(strategy, exception, *args, **kwargs)(func)
    fargs = fargs or []
    fkwargs = fkwargs or {}
    return decorated(*fargs, **fkwargs)
