# Runtime hidden API dumper

`scripts/dump_runtime_hiddenapi.py` generates a `hiddenapi-flags.csv` from the
hidden-API flags encoded in the boot DEX files of a connected Android device.

## Usage

The dumper requires Python 3.10 or newer, `adb`, and `dexdump` from the Android
SDK Build Tools. It selects the newest installed `dexdump` under
`ANDROID_SDK_ROOT` or `ANDROID_HOME` unless `--dexdump` is specified.

```shell
python3 scripts/dump_runtime_hiddenapi.py \
  --serial SERIAL \
  --output hiddenapi-flags.csv
```

The script:

1. reads `BOOTCLASSPATH` from the device;
2. temporarily pulls each mounted boot-class-path JAR;
3. runs `dexdump -n` on every JAR, including all of its DEX entries;
4. emits every field and method descriptor with its runtime flags; and
5. sorts labels within each row and sorts rows bytewise.

The temporary JARs and `dexdump` diagnostics are not included in the output.

## Flag provenance

The decoder is based on the flags stored in each DEX member's hidden-API class
data. AOSP's `ApiList` defines the encoded values and runtime names:

- [`sdk`, `unsupported`, `blocked`, and `max-target-*` values](https://android.googlesource.com/platform/art/+/b753cf97923c3695338d21466fa14c57b480a59a/libartbase/base/hiddenapi_flags.h#83)
- [`core-platform-api` and `test-api` domain flags](https://android.googlesource.com/platform/art/+/b753cf97923c3695338d21466fa14c57b480a59a/libartbase/base/hiddenapi_flags.h#116)
- [the corresponding runtime label strings](https://android.googlesource.com/platform/art/+/b753cf97923c3695338d21466fa14c57b480a59a/libartbase/base/hiddenapi_flags.h#152)

`sdk` has the encoded value zero. `dexdump` prints a `hiddenapi` line only for a
nonzero value for both [methods](https://android.googlesource.com/platform/art/+/b753cf97923c3695338d21466fa14c57b480a59a/dexdump/dexdump.cc#1378)
and [fields](https://android.googlesource.com/platform/art/+/b753cf97923c3695338d21466fa14c57b480a59a/dexdump/dexdump.cc#1498),
so a member without that line is emitted as `sdk` rather than omitted.

These links use the ART commit pinned by the `android-latest-release`
[superproject](https://android.googlesource.com/platform/superproject/+/329d792f6d5e33e8a6fc5a02809c795ce17774ab/)
when its [manifest](https://android.googlesource.com/platform/manifest/+/ad156f32caaa06dae91c02d443f6a8fe210eaa54/default.xml#7)
selected `android17-release`.

Only labels represented by the runtime `ApiList` can be recovered. Build-list
metadata such as `public-api`, `system-api`, `lo-prio`, and `removed` is not
synthesized, but the corresponding member row is still emitted.

## Data boundary

The CSV contains DEX class/member descriptors and their flags. It does not
contain DEX constant values, the device serial, network address, model,
fingerprint, build ID, local file paths, or application/user data. The build ID
is printed to standard output so callers can record firmware provenance
separately. The API surface itself is build-specific and can therefore identify
the firmware build or family when compared with other datasets.

`BOOTCLASSPATH` can include independently updated Mainline/APEX modules. A build
ID alone may therefore be insufficient to reproduce an identical CSV after
module updates; this dumper does not record module versions.

## License

Licensed under the Apache License, Version 2.0. See `LICENSE`.
