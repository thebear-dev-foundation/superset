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
"""add sessions_invalidated_at to user_attribute

Revision ID: f7a1c93e0b21
Revises: 33d7e0e21daa
Create Date: 2026-06-02 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

from superset.migrations.shared.utils import (
    add_columns,
    create_index,
    drop_columns,
    drop_index,
)

# revision identifiers, used by Alembic.
revision = "f7a1c93e0b21"
down_revision = "33d7e0e21daa"

TABLE = "user_attribute"
COLUMN = "sessions_invalidated_at"
INDEX = "ix_user_attribute_sessions_invalidated_at"
UQ = "uq_user_attribute_user_id"


MERGE_COLUMNS = ("avatar_url", "welcome_dashboard_id", "sessions_invalidated_at")


def upgrade():
    add_columns(TABLE, sa.Column(COLUMN, sa.DateTime(), nullable=True))
    create_index(TABLE, INDEX, [COLUMN])
    # The model treats ``user_attribute`` as one row per user (all readers use
    # ``extra_attributes[0]``). Enforce that invariant so the session-invalidation
    # upsert is race-safe. Collapse any pre-existing duplicates into the lowest
    # ``id`` per user before adding the unique constraint.
    #
    # The merge/de-dup is driven in Python rather than via correlated subqueries:
    # MySQL forbids referencing the UPDATE/DELETE target table in a subquery
    # (error 1093), so a portable SQL form is awkward. Reading the duplicate rows
    # and resolving the winner in Python works identically on SQLite/MySQL/Postgres.
    _dedupe_user_attributes()
    # SQLite has no ALTER ... ADD CONSTRAINT, so use batch mode (copy-and-move)
    # which all dialects support.
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.create_unique_constraint(UQ, ["user_id"])


def _dedupe_user_attributes():
    """Collapse duplicate ``user_attribute`` rows into the lowest ``id`` per user.

    Settings stored only on a higher-``id`` duplicate are merged forward into the
    kept row (the kept row's NULL columns take the lowest-``id`` non-NULL sibling
    value) so nothing is silently lost, then the redundant rows are deleted.
    """
    bind = op.get_bind()
    columns = ", ".join(("id", "user_id", *MERGE_COLUMNS))
    rows = bind.execute(
        sa.text(f"SELECT {columns} FROM {TABLE} ORDER BY id")  # noqa: S608
    ).fetchall()

    by_user: dict[int, list] = {}
    for row in rows:
        mapping = row._mapping
        if mapping["user_id"] is None:
            continue
        by_user.setdefault(mapping["user_id"], []).append(mapping)

    for user_rows in by_user.values():
        if len(user_rows) < 2:
            continue
        # Rows are ordered by id, so the first is the keeper.
        keeper = user_rows[0]
        duplicates = user_rows[1:]
        updates = {}
        for column in MERGE_COLUMNS:
            if keeper[column] is not None:
                continue
            for dup in duplicates:
                if dup[column] is not None:
                    updates[column] = dup[column]
                    break
        if updates:
            assignments = ", ".join(f"{col} = :{col}" for col in updates)
            bind.execute(
                sa.text(
                    f"UPDATE {TABLE} SET {assignments} WHERE id = :id"  # noqa: S608
                ),
                {**updates, "id": keeper["id"]},
            )
        bind.execute(
            sa.text(f"DELETE FROM {TABLE} WHERE id = :id"),  # noqa: S608
            [{"id": dup["id"]} for dup in duplicates],
        )


def downgrade():
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_constraint(UQ, type_="unique")
    drop_index(TABLE, INDEX)
    drop_columns(TABLE, COLUMN)
