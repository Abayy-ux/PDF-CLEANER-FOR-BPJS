from backend.app.pdf.asciihex import encode_asciihex, decode_asciihex

def test_asciihex_encoding_format():
    data = b"Hello, PDF Safe Normalizer!"
    encoded = encode_asciihex(data, chars_per_line=16)
    
    # Must end with '>'
    assert encoded.strip().endswith(b">")
    
    # Must be uppercase hex characters and newlines
    lines = encoded.decode("ascii").strip().split("\n")
    for line in lines[:-1]:
        clean_line = line.strip()
        assert len(clean_line) <= 16
        assert all(c in "0123456789ABCDEF" for c in clean_line)

def test_asciihex_roundtrip():
    test_payloads = [
        b"",
        b"\x00\x01\x02\x03\xFF\xFE\xFD",
        b"Standard PDF Stream Data 1234567890!@#$%^&*()_+",
        bytes(range(256)),
    ]

    for payload in test_payloads:
        encoded = encode_asciihex(payload)
        decoded = decode_asciihex(encoded)
        assert decoded == payload

def test_odd_length_asciihex_decoding():
    # PDF specification: if odd number of digits before '>', append '0'
    odd_hex = b"ABC>"  # Interpreted as "ABC0" -> 0xAB, 0xC0
    decoded = decode_asciihex(odd_hex)
    assert decoded == bytes.fromhex("ABC0")
