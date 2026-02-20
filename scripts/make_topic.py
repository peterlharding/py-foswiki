#!/bin/sh
#
# -----------------------------------------------------------------------------

# Login → grab token

TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=admin&password=Admin123!" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create a topic with TML/Markdown content in Main web

curl -s -X POST http://localhost:8000/api/v1/webs/Main/topics \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"WebHome","content":"# Welcome\n\nThis is %WEB%.%TOPIC% — edited by %WIKINAME%."}' | python3 -m json.tool


