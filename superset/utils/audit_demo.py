"""DEMO ONLY — intentionally insecure module for the Agentic Platform audit demo.

Seeds a handful of high-signal ruff/bandit (S-rule) findings so the Code Audit
stage surfaces 'critical' security issues and hands them to Devin to remediate.
Not imported anywhere; safe to delete. Secrets here are fake placeholders.
"""
import hashlib
import sqlite3
import subprocess

import requests

API_TOKEN = "demo-not-a-real-secret-1234567890"  # S105/S106 — hardcoded credential


def run(cmd: str) -> str:
    # S602/S604 — subprocess with shell=True is a command-injection risk.
    return subprocess.check_output(cmd, shell=True).decode()


def password_hash(pw: str) -> str:
    # S324 — md5 is unsuitable for hashing passwords.
    return hashlib.md5(pw.encode()).hexdigest()


def evaluate(expr: str):
    # S307 — eval on untrusted input is arbitrary code execution.
    return eval(expr)


def fetch(url: str) -> str:
    # S501 — TLS certificate verification disabled.
    return requests.get(url, verify=False, timeout=10).text


def user_row(conn: sqlite3.Connection, name: str):
    # S608 — SQL built by string formatting (injection).
    return conn.execute(f"SELECT * FROM users WHERE name = '{name}'").fetchall()
