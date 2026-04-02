#!/bin/bash
set -uo pipefail

echo "Executing serve command in container {container_name}..."
echo "--- Command ---"
echo '{b64_cmd}' | base64 -d
echo -e "\n---------------"

docker exec {container_name} bash -c "echo '{b64_cmd}' | base64 -d > /tmp/sparkrun_serve.sh && bash /tmp/sparkrun_serve.sh"
