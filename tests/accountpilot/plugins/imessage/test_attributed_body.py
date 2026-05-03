"""Tests for the attributedBody decoder.

The synthetic blob builder uses a frozen prefix/trailer captured from
a real chat.db row, but the captured bytes are entirely structural —
they contain Apple class names (NSMutableAttributedString, NSString,
NSDictionary, NSNumber, NSValue) and the message-part attribute key
(`__kIMMessagePartAttributeName`). No personal content from the
source message is committed. The text payload is substituted at test
time.
"""

from __future__ import annotations

from accountpilot.plugins.imessage.attributed_body import decode_attributed_body

# Captured from an Apple chat.db `attributedBody` row, then split at
# the C-string length boundary. Inserting `<utf8_len_byte> <utf8>` and
# replacing trailer[6] with the char-length yields a valid blob that
# pytypedstream decodes back to the inserted text.
_PREFIX_HEX = (
    "040b73747265616d747970656481e803840140848484194e534d75746162"
    "6c6541747472696275746564537472696e67008484124e53417474726962"
    "75746564537472696e67008484084e534f626a6563740085928484840f4e"
    "534d757461626c65537472696e67018484084e53537472696e6701958401"
    "2b"
)
_TRAILER_HEX = (
    "8684026949012e928484840c4e5344696374696f6e6172790095840169"
    "01928498981d5f5f6b494d4d657373616765506172744174747269627574"
    "654e616d658692848484084e534e756d626572008484074e5356616c7565"
    "009584012a849b9b00868686"
)
_PREFIX = bytes.fromhex(_PREFIX_HEX)
_TRAILER = bytes.fromhex(_TRAILER_HEX)


def build_synthetic_attributed_body(text: str) -> bytes:
    """Construct a minimal attributedBody blob containing `text`.

    Constraints:
      - text's UTF-8 length must be < 128 (single-byte typedstream
        length encoding)
      - char count must be < 128 (same reason — the attributed-range
        length is also stored as a single byte)
    """
    utf8 = text.encode("utf-8")
    if len(utf8) >= 128:
        msg = "synthetic builder only supports utf-8 length < 128"
        raise ValueError(msg)
    if len(text) >= 128:
        msg = "synthetic builder only supports char length < 128"
        raise ValueError(msg)
    # Trailer index 6 holds the char-length used by the
    # NSAttributedString range descriptor; rewrite it to match.
    new_trailer = _TRAILER[:6] + bytes([len(text)]) + _TRAILER[7:]
    return _PREFIX + bytes([len(utf8)]) + utf8 + new_trailer


def test_decode_attributed_body_extracts_plain_text() -> None:
    blob = build_synthetic_attributed_body("hello from attributedBody")
    assert decode_attributed_body(blob) == "hello from attributedBody"


def test_decode_attributed_body_handles_short_text() -> None:
    blob = build_synthetic_attributed_body("ok")
    assert decode_attributed_body(blob) == "ok"


def test_decode_attributed_body_returns_empty_on_none_input() -> None:
    assert decode_attributed_body(None) == ""


def test_decode_attributed_body_returns_empty_on_empty_input() -> None:
    assert decode_attributed_body(b"") == ""


def test_decode_attributed_body_returns_empty_on_malformed_blob() -> None:
    # Garbage bytes should not raise; should return "".
    assert decode_attributed_body(b"\x00\x01\x02not-typedstream") == ""


def test_decode_attributed_body_returns_empty_on_truncated_blob() -> None:
    blob = build_synthetic_attributed_body("hello")
    # Truncate mid-stream — typedstream should fail to traverse.
    assert decode_attributed_body(blob[:30]) == ""
