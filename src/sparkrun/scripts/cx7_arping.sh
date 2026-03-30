#!/bin/bash
# Neighbor MAC discovery via arping for CX7 topology detection.
# Arguments are passed as CX7_IFACES env var (space-separated interface names).
# Outputs CX7_NEIGHBOR_N_LOCAL_IFACE and CX7_NEIGHBOR_N_REMOTE_MAC on stdout.
# Diagnostic messages go to stderr.

set -uo pipefail

if [ -z "${CX7_IFACES:-}" ]; then
    echo "CX7_NEIGHBOR_COUNT=0"
    exit 0
fi

echo "Discovering neighbors on CX7 interfaces: $CX7_IFACES" >&2

# Send gratuitous ARPs / solicit responses on each interface
for iface in $CX7_IFACES; do
    # Use arping broadcast to solicit ARP responses from link partner.
    # -D (duplicate address detection) mode sends to broadcast and any
    # device on the link will reply.
    sudo arping -I "$iface" -c 3 -b -w 3 0.0.0.0 >/dev/null 2>&1 || true
    # Also try pinging link-local broadcast
    ping -I "$iface" -c 2 -w 2 -b 169.254.255.255 >/dev/null 2>&1 || true
done

# Wait for neighbor table to settle
sleep 1

# Read neighbor table for each interface and collect remote MACs
COUNT=0
for iface in $CX7_IFACES; do
    # Read all neighbors on this interface
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        # Format: IP dev IFACE lladdr MAC state
        remote_mac=$(echo "$line" | grep -oP 'lladdr \K[0-9a-f:]+')
        state=$(echo "$line" | awk '{print $NF}')

        if [ -n "$remote_mac" ] && [ "$state" != "FAILED" ]; then
            echo "  $iface -> $remote_mac ($state)" >&2
            echo "CX7_NEIGHBOR_${COUNT}_LOCAL_IFACE=$iface"
            echo "CX7_NEIGHBOR_${COUNT}_REMOTE_MAC=$remote_mac"
            COUNT=$((COUNT + 1))
            # Take only the first valid neighbor per interface
            break
        fi
    done < <(ip neigh show dev "$iface" 2>/dev/null)
done

echo "CX7_NEIGHBOR_COUNT=$COUNT"
