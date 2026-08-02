#!/usr/bin/env python3
"""Dump the hidden-API flags encoded in a device's boot class path."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Iterator


class DumpError(RuntimeError):
    pass


_MEMBER_RE = re.compile(rb"^\s+#\d+\s+: \(in (L[^)]*;)\)$")
_NAME_RE = re.compile(rb"^\s+name\s+: '(.*)'$")
_TYPE_RE = re.compile(rb"^\s+type\s+: '(.*)'$")
_HIDDENAPI_RE = re.compile(
    rb"^\s+hiddenapi\s+: 0x([0-9a-fA-F]+) \(([^)]*)\)$"
)
_CLASS_RE = re.compile(rb"^Class #\d+\s+-$")

_VALUE_FLAGS = {
    0: b"sdk",
    1: b"unsupported",
    2: b"blocked",
    3: b"max-target-o",
    4: b"max-target-p",
    5: b"max-target-q",
    6: b"max-target-r",
    7: b"max-target-s",
}
_DOMAIN_FLAGS = {
    0x10: b"core-platform-api",
    0x20: b"test-api",
}
_KNOWN_FLAG_MASK = 0x3F


def _decode_hiddenapi(
    raw: int, printed: bytes, source: str, line_number: int
) -> tuple[bytes, ...]:
    unknown_bits = raw & ~_KNOWN_FLAG_MASK
    value = raw & 0x0F
    if unknown_bits or value not in _VALUE_FLAGS:
        raise DumpError(
            f"{source}:{line_number}: unknown hiddenapi encoding 0x{raw:04x}; "
            "use a dexdump compatible with this device"
        )

    decoded = [_VALUE_FLAGS[value]]
    decoded.extend(name for bit, name in _DOMAIN_FLAGS.items() if raw & bit)
    decoded_flags = tuple(sorted(decoded))
    printed_flags = tuple(sorted(flag.strip().lower() for flag in printed.split(b",")))
    if not all(printed_flags) or printed_flags != decoded_flags:
        raise DumpError(
            f"{source}:{line_number}: dexdump printed {printed_flags!r} for "
            f"0x{raw:04x}, expected {decoded_flags!r}"
        )
    return decoded_flags


def parse_dexdump(
    lines: Iterable[bytes], source: str = "<dexdump>"
) -> Iterator[tuple[bytes, tuple[bytes, ...]]]:
    """Yield member descriptors and runtime flags from plain dexdump output."""

    current: dict[str, object] | None = None

    def finish(line_number: int) -> tuple[bytes, tuple[bytes, ...]] | None:
        nonlocal current
        if current is None:
            return None

        owner = current["owner"]
        name = current.get("name")
        type_descriptor = current.get("type")
        if not isinstance(owner, bytes) or not isinstance(name, bytes) or not isinstance(
            type_descriptor, bytes
        ):
            raise DumpError(
                f"{source}:{line_number}: incomplete member beginning on line "
                f"{current['line']}"
            )

        separator = b"" if type_descriptor.startswith(b"(") else b":"
        descriptor = owner + b"->" + name + separator + type_descriptor
        flags = current.get("flags")
        if flags is None:
            # ART encodes sdk as zero, and dexdump suppresses zero-valued flags.
            flags = (b"sdk",)
        if not isinstance(flags, tuple):
            raise AssertionError("invalid parser state")
        current = None
        return descriptor, flags

    last_line = 0
    for line_number, raw_line in enumerate(lines, 1):
        last_line = line_number
        line = raw_line.rstrip(b"\r\n")

        member_match = _MEMBER_RE.match(line)
        if member_match:
            completed = finish(line_number)
            if completed is not None:
                yield completed
            current = {"owner": member_match.group(1), "line": line_number}
            continue

        if _CLASS_RE.match(line):
            completed = finish(line_number)
            if completed is not None:
                yield completed
            continue

        name_match = _NAME_RE.match(line)
        if name_match and current is not None:
            if "name" in current:
                raise DumpError(f"{source}:{line_number}: duplicate member name")
            current["name"] = name_match.group(1)
            continue

        type_match = _TYPE_RE.match(line)
        if type_match and current is not None:
            if "type" in current:
                raise DumpError(f"{source}:{line_number}: duplicate member type")
            current["type"] = type_match.group(1)
            continue

        hiddenapi_match = _HIDDENAPI_RE.match(line)
        if hiddenapi_match:
            if current is None:
                raise DumpError(f"{source}:{line_number}: hiddenapi flags outside a member")
            if "flags" in current:
                raise DumpError(f"{source}:{line_number}: duplicate hiddenapi flags")
            current["flags"] = _decode_hiddenapi(
                int(hiddenapi_match.group(1), 16),
                hiddenapi_match.group(2),
                source,
                line_number,
            )
            continue
        if line.lstrip().startswith(b"hiddenapi"):
            raise DumpError(f"{source}:{line_number}: malformed hiddenapi flags")

    completed = finish(last_line + 1)
    if completed is not None:
        yield completed


def merge_member(
    members: dict[bytes, tuple[bytes, ...]],
    descriptor: bytes,
    flags: tuple[bytes, ...],
    source: str,
) -> None:
    previous = members.get(descriptor)
    if previous is not None and previous != flags:
        raise DumpError(
            f"{source}: conflicting flags for {descriptor}: {previous!r} and {flags!r}"
        )
    members[descriptor] = flags


def _run(command: list[str], description: str) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise DumpError(f"{description} failed ({result.returncode}): {detail}")
    return result.stdout.strip()


def _adb_command(adb: str, serial: str | None, *arguments: str) -> list[str]:
    command = [adb]
    if serial:
        command.extend(("-s", serial))
    command.extend(arguments)
    return command


def _resolve_executable(value: str, description: str) -> str:
    if os.sep in value:
        path = Path(value).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    else:
        resolved = shutil.which(value)
        if resolved:
            return resolved
    raise DumpError(f"could not find {description}: {value}")


def _build_tools_version(path: Path) -> tuple[tuple[int, ...], int, str]:
    match = re.fullmatch(r"(\d+(?:\.\d+)*)(.*)", path.parent.name)
    if match is None:
        return (), 0, path.parent.name
    numbers = tuple(int(part) for part in match.group(1).split("."))
    suffix = match.group(2)
    return numbers, int(not suffix), suffix


def find_dexdump(explicit: str | None) -> str:
    if explicit:
        return _resolve_executable(explicit, "dexdump")

    candidates: list[Path] = []
    for variable in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        root = os.environ.get(variable)
        if root:
            candidates.extend(Path(root).expanduser().glob("build-tools/*/dexdump"))
    candidates = [path for path in candidates if path.is_file() and os.access(path, os.X_OK)]
    if candidates:
        return str(max(candidates, key=_build_tools_version))

    resolved = shutil.which("dexdump")
    if resolved:
        return resolved
    raise DumpError(
        "could not find dexdump; set ANDROID_SDK_ROOT or pass --dexdump"
    )


def _dump_jar(
    dexdump: str,
    jar: Path,
    remote_path: str,
    members: dict[bytes, tuple[bytes, ...]],
    stderr_path: Path,
) -> int:
    with stderr_path.open("w+b") as stderr_file:
        process = subprocess.Popen(
            [dexdump, "-n", str(jar)],
            stdout=subprocess.PIPE,
            stderr=stderr_file,
        )
        assert process.stdout is not None
        count = 0
        try:
            for descriptor, flags in parse_dexdump(process.stdout, remote_path):
                merge_member(members, descriptor, flags, remote_path)
                count += 1
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            process.stdout.close()

        return_code = process.wait()
        stderr_file.seek(0)
        error = stderr_file.read().decode("utf-8", "replace").strip()
    if return_code:
        raise DumpError(f"dexdump failed for {remote_path} ({return_code}): {error}")
    if not count:
        raise DumpError(f"dexdump found no members in {remote_path}")
    return count


def _write_csv(output: Path, members: dict[bytes, tuple[bytes, ...]]) -> str:
    if not output.parent.is_dir():
        raise DumpError(f"output directory does not exist: {output.parent}")
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        digest = hashlib.sha256()
        with os.fdopen(file_descriptor, "wb") as stream:
            for descriptor in sorted(members):
                row = descriptor + b"," + b",".join(members[descriptor]) + b"\n"
                stream.write(row)
                digest.update(row)
        os.replace(temporary, output)
        return digest.hexdigest()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def dump_runtime_hiddenapi(
    adb: str,
    dexdump: str,
    serial: str | None,
    output: Path,
) -> tuple[str, int, str]:
    build_id = _run(
        _adb_command(adb, serial, "shell", "getprop", "ro.build.id"),
        "reading the device build ID",
    )
    bootclasspath = _run(
        _adb_command(adb, serial, "shell", "printenv", "BOOTCLASSPATH"),
        "reading BOOTCLASSPATH",
    )
    remote_jars = bootclasspath.split(":") if bootclasspath else []
    if not remote_jars or any(not path.startswith("/") for path in remote_jars):
        raise DumpError(f"invalid BOOTCLASSPATH: {bootclasspath!r}")

    members: dict[bytes, tuple[bytes, ...]] = {}
    with tempfile.TemporaryDirectory(prefix="runtime-hiddenapi-") as directory:
        temporary = Path(directory)
        for index, remote_path in enumerate(remote_jars, 1):
            print(f"[{index}/{len(remote_jars)}] {remote_path}", file=sys.stderr)
            local_jar = temporary / f"{index:03d}-{Path(remote_path).name}"
            _run(
                _adb_command(adb, serial, "pull", remote_path, str(local_jar)),
                f"pulling {remote_path}",
            )
            _dump_jar(
                dexdump,
                local_jar,
                remote_path,
                members,
                temporary / f"{index:03d}-dexdump.stderr",
            )

    if not members:
        raise DumpError("no boot class path members found")
    digest = _write_csv(output, members)
    return build_id, len(members), digest


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--adb", default=os.environ.get("ADB", "adb"), help="adb executable"
    )
    parser.add_argument(
        "--dexdump",
        default=os.environ.get("DEXDUMP"),
        help="dexdump executable (default: newest installed Android Build Tools)",
    )
    parser.add_argument(
        "--serial", default=os.environ.get("ANDROID_SERIAL"), help="adb device serial"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("hiddenapi-flags.csv"),
        help="output CSV path (default: hiddenapi-flags.csv)",
    )
    options = parser.parse_args(arguments)

    try:
        adb = _resolve_executable(options.adb, "adb")
        dexdump = find_dexdump(options.dexdump)
        build_id, count, digest = dump_runtime_hiddenapi(
            adb, dexdump, options.serial, options.output
        )
    except DumpError as error:
        parser.exit(1, f"error: {error}\n")

    print(f"build: {build_id}")
    print(f"rows: {count}")
    print(f"sha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
