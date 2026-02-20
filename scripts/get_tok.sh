#!/bin/sh
#
#

TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=admin&password=Admin123!" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "TOKEN |${TOKEN}|"


