#!/bin/sh
#
# ----------------------------------------------------------------------------

curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@example.com","password":"Admin123!","display_name":"Admin"}' | python3 -m json.tool


