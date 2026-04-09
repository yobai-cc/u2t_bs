# UDP Relay Legacy Behavior Snapshot

This document captures the UDP behavior that exists on `master` before the service is simplified to fixed auto-reply mode.

## Current Page Fields

- `bind_ip` / `bind_port`: local UDP listener address used by the server.
- `cloud_ip` / `cloud_port`: configured remote peer treated as the upstream "cloud" endpoint.
- `custom_reply_data`: payload returned to the last client after a packet is received from the configured cloud endpoint.
- `hex_mode`: controls whether manual send and configured reply payloads are parsed as hex.

## Current Runtime Flow

The current implementation is not a pure auto-reply server.

1. A terminal device sends a UDP packet to `bind_ip:bind_port`.
2. The server records that source as `last_client_addr`.
3. The server forwards the original packet to `cloud_ip:cloud_port`.
4. When a packet later arrives from `cloud_ip:cloud_port`, the server sends `custom_reply_data` to `last_client_addr`.

In other words, the configured reply payload is triggered by traffic from the configured cloud endpoint, not directly by the original terminal device packet.

## Manual Send Behavior

The page also exposes a manual send action.

- If `last_client_addr` exists, manual send targets the last client.
- Otherwise it falls back to `cloud_ip:cloud_port`.

This makes the page look like it supports multiple behaviors, but the core runtime still centers on relay-first logic.

## Why This Is Being Archived

The term "cloud" is misleading for the intended use case where a terminal device should send data to the UDP server and receive an immediate fixed custom response.

The next change on `master` will simplify the service so that:

1. the terminal device sends a packet to the UDP server,
2. the UDP server immediately replies with configured custom data,
3. cloud forwarding fields are removed from the main UDP configuration surface.
