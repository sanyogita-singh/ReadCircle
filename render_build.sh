#!/usr/bin/env bash
set -e

echo "---- Installing Dependencies ----"
pip install --upgrade pip
pip install -r requirements.txt

echo "---- Ensuring instance directory ----"
mkdir -p instance

echo "---- Setting Flask App ----"
export FLASK_APP=app.py

echo "---- Running Database Migrations ----"
# Bootstrap migrations if the folder is absent
if [ ! -d "migrations" ]; then
  echo "No migrations folder found. Bootstrapping..."
  python -m flask db init
  python -m flask db migrate -m "Initial schema (auto)"
fi

python -m flask db upgrade
echo "---- Build Complete ----"
