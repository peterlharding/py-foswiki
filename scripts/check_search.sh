#!/bin/sh
#
# -----------------------------------------------------------------------------

set -x

curl -s "http://localhost:8000/api/v1/search?q=Welcome" | python3 -m json.tool


