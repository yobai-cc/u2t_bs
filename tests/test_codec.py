from app.utils.codec import bytes_to_hex, decode_text, parse_payload


def test_parse_payload_hex_mode_round_trip() -> None:
    payload = parse_payload("48 65 6c 6c 6f", True)
    assert payload == b"Hello"


def test_parse_payload_text_mode_round_trip() -> None:
    payload = parse_payload("hello", False)
    assert payload == b"hello"


def test_decode_text_replaces_invalid_bytes() -> None:
    assert decode_text(b"abc\xff") == "abc\ufffd"


def test_bytes_to_hex_uses_spaced_lowercase() -> None:
    assert bytes_to_hex(b"\x0a\xff") == "0a ff"
