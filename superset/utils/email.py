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
"""Email utility functions extracted from superset.utils.core."""

from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from typing import Any

from superset.utils.enums import HeaderDataType

logger = logging.getLogger(__name__)


def send_email_smtp(  # pylint: disable=invalid-name,too-many-arguments,too-many-locals
    to: str,
    subject: str,
    html_content: str,
    config: dict[str, Any],
    files: list[str] | None = None,
    data: dict[str, str] | None = None,
    pdf: dict[str, bytes] | None = None,
    images: dict[str, bytes] | None = None,
    dryrun: bool = False,
    cc: str | None = None,
    bcc: str | None = None,
    mime_subtype: str = "mixed",
    header_data: HeaderDataType | None = None,
) -> None:
    """
    Send an email with html content, eg:
    send_email_smtp(
        'test@example.com', 'foo', '<b>Foo</b> bar',['/dev/null'], dryrun=True)
    """
    smtp_mail_from = config["SMTP_MAIL_FROM"]
    smtp_mail_to = recipients_string_to_list(to)

    msg = MIMEMultipart(mime_subtype)
    # Strip CR/LF from the subject so the value cannot inject additional
    # email headers via header folding/splitting.
    subject = subject.replace("\r", "").replace("\n", " ").strip()
    msg["Subject"] = subject
    msg["From"] = smtp_mail_from
    msg["To"] = ", ".join(smtp_mail_to)

    msg.preamble = "This is a multi-part message in MIME format."

    recipients = smtp_mail_to
    if cc:
        smtp_mail_cc = recipients_string_to_list(cc)
        msg["Cc"] = ", ".join(smtp_mail_cc)
        recipients = recipients + smtp_mail_cc

    smtp_mail_bcc = []
    if bcc:
        # don't add bcc in header
        smtp_mail_bcc = recipients_string_to_list(bcc)
        recipients = recipients + smtp_mail_bcc

    msg["Date"] = formatdate(localtime=True)
    mime_text = MIMEText(html_content, "html")
    msg.attach(mime_text)

    # Attach files by reading them from disk
    for fname in files or []:
        basename = os.path.basename(fname)
        with open(fname, "rb") as f:
            msg.attach(
                MIMEApplication(
                    f.read(),
                    Content_Disposition=f"attachment; filename='{basename}'",
                    Name=basename,
                )
            )

    # Attach any files passed directly
    for name, body in (data or {}).items():
        msg.attach(
            MIMEApplication(
                body, Content_Disposition=f"attachment; filename='{name}'", Name=name
            )
        )

    for name, body_pdf in (pdf or {}).items():
        msg.attach(
            MIMEApplication(
                body_pdf,
                Content_Disposition=f"attachment; filename='{name}'",
                Name=name,
            )
        )

    # Attach any inline images, which may be required for display in
    # HTML content (inline)
    for msgid, imgdata in (images or {}).items():
        formatted_time = formatdate(localtime=True)
        file_name = f"{subject} {formatted_time}"
        image = MIMEImage(imgdata, name=file_name)
        image.add_header("Content-ID", f"<{msgid}>")
        image.add_header("Content-Disposition", "inline")
        msg.attach(image)
    msg_mutator = config["EMAIL_HEADER_MUTATOR"]
    # the base notification returns the message without any editing.
    new_msg = msg_mutator(msg, **(header_data or {}))
    new_to = new_msg["To"].split(", ") if "To" in new_msg else []
    new_cc = new_msg["Cc"].split(", ") if "Cc" in new_msg else []
    new_recipients = new_to + new_cc + smtp_mail_bcc
    if set(new_recipients) != set(recipients):
        recipients = new_recipients
    send_mime_email(smtp_mail_from, recipients, new_msg, config, dryrun=dryrun)


def send_mime_email(
    e_from: str,
    e_to: list[str],
    mime_msg: MIMEMultipart,
    config: dict[str, Any],
    dryrun: bool = False,
) -> None:
    """Send a MIME email message via SMTP.

    :param e_from: Sender email address.
    :param e_to: List of recipient email addresses.
    :param mime_msg: The MIME message to send.
    :param config: Application config dict with SMTP settings.
    :param dryrun: If ``True``, log the message instead of sending.
    """
    smtp_host = config["SMTP_HOST"]
    smtp_port = config["SMTP_PORT"]
    smtp_user = config["SMTP_USER"]
    smtp_password = config["SMTP_PASSWORD"]
    smtp_starttls = config["SMTP_STARTTLS"]
    smtp_ssl = config["SMTP_SSL"]
    smtp_ssl_server_auth = config["SMTP_SSL_SERVER_AUTH"]

    if dryrun:
        logger.info("Dryrun enabled, email notification content is below:")
        logger.info(mime_msg.as_string())
        return

    # Default ssl context is SERVER_AUTH using the default system
    # root CA certificates
    ssl_context = ssl.create_default_context() if smtp_ssl_server_auth else None
    smtp = (
        smtplib.SMTP_SSL(smtp_host, smtp_port, context=ssl_context)
        if smtp_ssl
        else smtplib.SMTP(smtp_host, smtp_port)
    )
    if smtp_starttls:
        smtp.starttls(context=ssl_context)
    if smtp_user and smtp_password:
        smtp.login(smtp_user, smtp_password)
    logger.debug("Sent an email to %s", str(e_to))
    smtp.sendmail(e_from, e_to, mime_msg.as_string())
    smtp.quit()


def recipients_string_to_list(address_string: str | None) -> list[str]:
    """
    Returns the list of target recipients for alerts and reports.

    Strips values and converts a comma/semicolon separated
    string into a list.
    """
    address_string_list: list[str] = []
    if isinstance(address_string, str):
        address_string_list = re.split(r",|\s|;", address_string)
    return [x.strip() for x in address_string_list if x.strip()]
