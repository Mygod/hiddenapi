from __future__ import annotations

import unittest

from scripts.dump_runtime_hiddenapi import DumpError, merge_member, parse_dexdump


class ParseDexdumpTest(unittest.TestCase):
    def test_parses_runtime_flags_and_retains_zero_valued_sdk_members(self) -> None:
        output = b"""\
Class #0            -
  Class descriptor  : 'Lexample/Foo;'
  Static fields     -
    #0              : (in Lexample/Foo;)
      name          : 'answer'
      type          : 'I'
      access        : 0x0009 (PUBLIC STATIC)
      value         : '\xed\xa0\x80'
    #1              : (in Lexample/Foo;)
      name          : 'internal'
      type          : '()V'
      access        : 0x0001 (PUBLIC)
      hiddenapi     : 0x0021 (UNSUPPORTED,TEST-API)
  Direct methods    -
    #0              : (in Lexample/Foo;)
      name          : '<init>'
      type          : '()V'
      access        : 0x10001 (PUBLIC CONSTRUCTOR)
      hiddenapi     : 0x0030 (SDK,CORE-PLATFORM-API,TEST-API)
"""

        self.assertEqual(
            [
                (b"Lexample/Foo;->answer:I", (b"sdk",)),
                (b"Lexample/Foo;->internal()V", (b"test-api", b"unsupported")),
                (
                    b"Lexample/Foo;-><init>()V",
                    (b"core-platform-api", b"sdk", b"test-api"),
                ),
            ],
            list(parse_dexdump(output.splitlines(keepends=True), "fixture")),
        )

    def test_rejects_incomplete_member(self) -> None:
        output = b"""\
    #0              : (in Lexample/Foo;)
      name          : 'missingType'
Class #1            -
"""

        with self.assertRaisesRegex(DumpError, "incomplete member"):
            list(parse_dexdump(output.splitlines(keepends=True), "fixture"))

    def test_rejects_unknown_runtime_encoding(self) -> None:
        output = b"""\
    #0              : (in Lexample/Foo;)
      name          : 'future'
      type          : '()V'
      hiddenapi     : 0x0008 (UNSUPPORTED)
"""

        with self.assertRaisesRegex(DumpError, "compatible with this device"):
            list(parse_dexdump(output.splitlines(keepends=True), "fixture"))

    def test_rejects_malformed_hiddenapi_line(self) -> None:
        output = b"""\
    #0              : (in Lexample/Foo;)
      name          : 'internal'
      type          : '()V'
      hiddenapi     : future format
"""

        with self.assertRaisesRegex(DumpError, "malformed hiddenapi"):
            list(parse_dexdump(output.splitlines(keepends=True), "fixture"))

    def test_rejects_conflicting_duplicate_descriptor(self) -> None:
        members = {b"Lexample/Foo;->answer:I": (b"sdk",)}

        with self.assertRaisesRegex(DumpError, "conflicting flags"):
            merge_member(
                members,
                b"Lexample/Foo;->answer:I",
                (b"blocked",),
                "second.jar",
            )


if __name__ == "__main__":
    unittest.main()
