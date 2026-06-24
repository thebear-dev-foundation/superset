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
"""User/session utility functions extracted from superset.utils.core."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from flask import g
from flask_appbuilder.security.sqla.models import User


def get_user() -> User | None:
    """
    Get the current user (if defined).

    :returns: The current user
    """
    return g.user if hasattr(g, "user") else None


def get_username() -> str | None:
    """
    Get username (if defined) associated with the current user.

    :returns: The username
    """

    try:
        return g.user.username
    except AttributeError:
        return None


def get_user_id() -> int | None:
    """
    Get the user identifier (if defined) associated with the current user.

    Though the Flask-AppBuilder `User` and Flask-Login  `AnonymousUserMixin` and
    `UserMixin` models provide a convenience `get_id` method, for generality, the
    identifier is encoded as a `str` whereas in Superset all identifiers are encoded as
    an `int`.

    returns: The user identifier
    """

    try:
        return g.user.id
    except AttributeError:
        return None


def get_user_email() -> str | None:
    """
    Get the email (if defined) associated with the current user.

    :returns: The email
    """

    try:
        return g.user.email
    except AttributeError:
        return None


@contextmanager
def override_user(user: User | None, force: bool = True) -> Iterator[Any]:
    """
    Temporarily override the current user per `flask.g` with the specified user.

    Sometimes, often in the context of async Celery tasks, it is useful to switch the
    current user (which may be undefined) to different one, execute some SQLAlchemy
    tasks et al. and then revert back to the original one.

    :param user: The override user
    :param force: Whether to override the current user if set
    """

    if hasattr(g, "user"):
        if force or g.user is None:
            current = g.user
            g.user = user
            yield
            g.user = current
        else:
            yield
    else:
        g.user = user
        yield
        delattr(g, "user")
