from __future__ import annotations


def parse_payload(value: str, hex_mode: bool) -> bytes:
    """Convert text or spaced hex input into bytes for network transmission."""

    if hex_mode:
        normalized = value.replace(" ", "")
        if not normalized:
            return b""
        return bytes.fromhex(normalized)
    return value.encode("utf-8")


def decode_text(payload: bytes) -> str:
    """Decode payload text safely so invalid bytes remain inspectable."""

    return payload.decode("utf-8", errors="replace")


def bytes_to_hex(payload: bytes) -> str:
    """Render bytes as lowercase spaced hex for the UI and packet logs."""

    return " ".join(f"{byte:02x}" for byte in payload)
