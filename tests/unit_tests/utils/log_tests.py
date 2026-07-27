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


from typing import Any

from flask import Flask

from superset.utils.log import (
    collect_request_payload,
    get_logger_from_status,
    REDACTED_VALUE,
)


def test_log_from_status_exception() -> None:
    (func, log_level) = get_logger_from_status(500)
    assert func.__name__ == "exception"
    assert log_level == "exception"


def test_log_from_status_warning() -> None:
    (func, log_level) = get_logger_from_status(422)
    assert func.__name__ == "warning"
    assert log_level == "warning"


def test_log_from_status_info() -> None:
    (func, log_level) = get_logger_from_status(300)
    assert func.__name__ == "info"
    assert log_level == "info"


def _collect_payload_for_json_body(body: dict[str, Any]) -> dict[str, Any]:
    app = Flask(__name__)

    @app.route("/api/v1/database/", methods=["POST"])
    def create_database() -> str:  # pragma: no cover - never called
        return ""

    with app.test_request_context("/api/v1/database/", method="POST", json=body):
        return collect_request_payload()


def test_collect_request_payload_redacts_nested_parameters() -> None:
    payload = _collect_payload_for_json_body(
        {
            "database_name": "examples",
            "parameters": {
                "host": "localhost",
                "username": "superset",
                "password": "s3cret",
            },
        }
    )
    assert payload["database_name"] == "examples"
    assert payload["parameters"]["host"] == "localhost"
    assert payload["parameters"]["password"] == REDACTED_VALUE


def test_collect_request_payload_redacts_ssh_tunnel() -> None:
    payload = _collect_payload_for_json_body(
        {
            "ssh_tunnel": {
                "server_address": "bastion.example.com",
                "username": "superset",
                "password": "s3cret",
                "private_key": "-----BEGIN RSA PRIVATE KEY-----",
                "private_key_password": "s3cret",
            }
        }
    )
    ssh_tunnel = payload["ssh_tunnel"]
    assert ssh_tunnel["server_address"] == "bastion.example.com"
    assert ssh_tunnel["password"] == REDACTED_VALUE
    assert ssh_tunnel["private_key"] == REDACTED_VALUE
    assert ssh_tunnel["private_key_password"] == REDACTED_VALUE


def test_collect_request_payload_redacts_sqlalchemy_uri() -> None:
    payload = _collect_payload_for_json_body(
        {
            "sqlalchemy_uri": "postgresql://superset:s3cret@localhost:5432/examples",
            "masked_encrypted_extra": '{"service_account_info": {"private_key": "x"}}',
        }
    )
    assert payload["sqlalchemy_uri"] == REDACTED_VALUE
    assert payload["masked_encrypted_extra"] == REDACTED_VALUE


def test_collect_request_payload_redacts_within_lists() -> None:
    payload = _collect_payload_for_json_body(
        {"databases": [{"name": "a", "password": "s3cret"}]}
    )
    assert payload["databases"][0]["name"] == "a"
    assert payload["databases"][0]["password"] == REDACTED_VALUE
