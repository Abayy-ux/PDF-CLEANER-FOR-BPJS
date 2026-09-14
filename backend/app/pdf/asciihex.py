from typing import Union

def encode_asciihex(data: bytes, chars_per_line: int = 72) -> bytes:
    """
    Encodes raw binary data into PDF ASCIIHexDecode format.
    - Each byte is represented by two uppercase hexadecimal characters (0-9, A-F).
    - Formats with newlines every `chars_per_line` characters for standard compliance.
    - Terminated with the PDF EOD marker '>' per ISO 32000-1 Section 7.4.2.
    """
    hex_str = data.hex().upper()
    if chars_per_line <= 0:
        return (hex_str + ">").encode("ascii")

    lines = []
    for i in range(0, len(hex_str), chars_per_line):
        lines.append(hex_str[i : i + chars_per_line])
    
    return ("\n".join(lines) + " >\n").encode("ascii")

def decode_asciihex(hex_data: Union[bytes, str]) -> bytes:
    """
    Decodes PDF ASCIIHexDecode stream back to raw binary bytes.
    Ignores whitespace and stops at '>'.
    """
    if isinstance(hex_data, bytes):
        raw_text = hex_data.decode("ascii", errors="ignore")
    else:
        raw_text = hex_data

    # Strip everything after '>'
    if ">" in raw_text:
        raw_text = raw_text.split(">", 1)[0]

    # Filter out whitespace
    clean_hex = "".join(c for c in raw_text if c in "0123456789abcdefABCDEF")

    # If odd length, append '0' per PDF standard
    if len(clean_hex) % 2 != 0:
        clean_hex += "0"

    return bytes.fromhex(clean_hex)
