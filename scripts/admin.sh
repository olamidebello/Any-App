#!/bin/bash
set -euo pipefail
cd /opt/anyapps/repo
exec sudo -u anyapps env DATABASE=/var/lib/anyapps/anyapps.sqlite3 /opt/anyapps/venv/bin/flask --app app create-admin
