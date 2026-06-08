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
"""Backports of standard-library features for older Python versions."""

import sys
from enum import Enum

if sys.version_info >= (3, 11):
    # pylint: disable=unused-import
    from enum import StrEnum  # nopycln: import
else:

    class StrEnum(str, Enum):
        """String enum backport for Python < 3.11.

        Combines :class:`str` and :class:`~enum.Enum` so that each member
        is also a native string, matching the behaviour of
        :class:`enum.StrEnum` introduced in Python 3.11.
        """
