#!/bin/bash
# Bring CX7 interfaces up with link-local addresses for topology detection.
# Arguments are passed as CX7_IFACES env var (space-separated interface names).
# Outputs CX7_BRINGUP_COUNT=N on stdout.
# Diagnostic messages go to stderr.

set -uo pipefail

if [ -z "${CX7_IFACES:-}" ]; then
    echo "CX7_BRINGUP_COUNT=0"
    exit 0
fi

echo "Bringing up CX7 interfaces: $CX7_IFACES" >&2

COUNT=0
for iface in $CX7_IFACES; do
    # Bring interface up
    if sudo ip link set "$iface" up 2>/dev/null; then
        echo "  $iface: up" >&2
        COUNT=$((COUNT + 1))
    else
        echo "  $iface: failed to bring up" >&2
    fi
done

# Wait briefly for link state to settle
sleep 2

echo "CX7_BRINGUP_COUNT=$COUNT"
