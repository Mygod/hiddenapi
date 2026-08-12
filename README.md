# Runtime hidden API flags

`hiddenapi-flags.csv` was generated from the hidden-API flags encoded in the
mounted boot-class-path JARs of the firmware build named by this branch's commit
subject. It was produced by `scripts/dump_runtime_hiddenapi.py` from the
`runtime-hiddenapi-dumper` branch.

Generation provenance:

- generator commit: `275f4aea43867142f6f9057e605cfee172ea7f09`;
- `dexdump`: Android SDK Build Tools 37.0.0;
- input: 52 mounted `BOOTCLASSPATH` JARs;
- output: 759,092 rows; and
- SHA-256: `3f57977f6a689ad4487761d02e1c0f50fd5e833c33c73ba09a626b1c7ed3c4e5`.

Each row contains a DEX field or method descriptor followed by the runtime
labels encoded for that member. ART defines the [encoded values and domain
bits](https://android.googlesource.com/platform/art/+/b753cf97923c3695338d21466fa14c57b480a59a/libartbase/base/hiddenapi_flags.h#83)
and their [runtime names](https://android.googlesource.com/platform/art/+/b753cf97923c3695338d21466fa14c57b480a59a/libartbase/base/hiddenapi_flags.h#152).
Because `sdk` is zero and `dexdump` suppresses zero-valued `hiddenapi` lines for
[methods](https://android.googlesource.com/platform/art/+/b753cf97923c3695338d21466fa14c57b480a59a/dexdump/dexdump.cc#1378)
and [fields](https://android.googlesource.com/platform/art/+/b753cf97923c3695338d21466fa14c57b480a59a/dexdump/dexdump.cc#1498),
members without such a line are recorded as `sdk`.

Only runtime-recoverable labels are present. Source-list metadata such as
`public-api`, `system-api`, `lo-prio`, and `removed` is not synthesized; its
absence does not remove the member row.

The CSV contains no device serial, network address, model, fingerprint, local
path, DEX constant value, or application/user data. It contains a build-specific
API surface, and the non-unique firmware build ID is retained only as the commit
subject for provenance.

Mounted Mainline/APEX modules can update independently of the firmware build ID.
The CSV therefore represents the device's module state when it was generated,
but it does not record module versions and the build ID alone may not reproduce
an identical dataset later.
