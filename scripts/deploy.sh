#!/bin/bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo 'Run on the hosting server as root.'; exit 1; fi
exec 9>/run/anyapps-deploy.lock
flock -n 9 || { echo 'Another AnyApps deployment is running.'; exit 1; }
apt-get update
apt-get install -y git python3-venv
mkdir -p /opt/anyapps
if [[ ! -d /opt/anyapps/repo/.git ]]; then git clone https://github.com/olamidebello/Any-App.git /opt/anyapps/repo; fi
cd /opt/anyapps/repo
git pull --ff-only
python3 -m venv /opt/anyapps/deploy-venv
/opt/anyapps/deploy-venv/bin/pip install 'ansible-core>=2.18,<2.22'
exec /opt/anyapps/deploy-venv/bin/ansible-playbook -i localhost, -c local ansible/deploy.yml "$@"
