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
from flask import Flask
from pytest_mock import MockerFixture

from superset import is_feature_enabled
from superset.utils.feature_flag_manager import FeatureFlagManager


def dummy_is_feature_enabled(feature_flag_name: str, default: bool = True) -> bool:
    return True if feature_flag_name.startswith("True_") else default


def test_init_app_does_not_mutate_default_feature_flags() -> None:
    app = Flask(__name__)
    app.config.update(
        DEFAULT_FEATURE_FLAGS={"DEFAULT": False},
        FEATURE_FLAGS={"DEFAULT": True, "OVERRIDE": True},
        GET_FEATURE_FLAGS_FUNC=None,
        IS_FEATURE_ENABLED_FUNC=None,
    )

    feature_flag_manager = FeatureFlagManager()
    feature_flag_manager.init_app(app)

    assert app.config["DEFAULT_FEATURE_FLAGS"] == {"DEFAULT": False}
    assert feature_flag_manager.get_feature_flags() == {
        "DEFAULT": True,
        "OVERRIDE": True,
    }


def test_existing_feature_flags(mocker: MockerFixture) -> None:
    """
    Test that ``is_feature_enabled`` reads flags correctly.
    """
    mocker.patch.dict(
        "superset.extensions.feature_flag_manager._feature_flags",
        {"FOO": True},
        clear=True,
    )
    assert is_feature_enabled("FOO") is True


def test_nonexistent_feature_flags(mocker: MockerFixture) -> None:
    """
    Test that ``is_feature_enabled`` returns ``False`` when flag not set.
    """
    mocker.patch.dict(
        "superset.extensions.feature_flag_manager._feature_flags", {}, clear=True
    )
    assert is_feature_enabled("FOO") is False


def test_is_feature_enabled(mocker: MockerFixture) -> None:
    """
    Test ``_is_feature_enabled_func``.
    """
    mocker.patch.dict(
        "superset.extensions.feature_flag_manager._feature_flags",
        {"True_Flag1": False, "True_Flag2": True, "Flag3": False, "Flag4": True},
        clear=True,
    )
    mocker.patch(
        "superset.extensions.feature_flag_manager._is_feature_enabled_func",
        dummy_is_feature_enabled,
    )

    assert is_feature_enabled("True_Flag1") is True
    assert is_feature_enabled("True_Flag2") is True
    assert is_feature_enabled("Flag3") is False
    assert is_feature_enabled("Flag4") is True
