# V8.0 source recovery — evidence and boundaries (28 Oct 2026)

## Validated source facts

| Check | Evidence | Result |
|---|---|---|
| Original V8 ZIP raw bytes | Project Library authorized copy | 9,769,053 bytes |
| ZIP SHA-256 | Computed from the recovered original bytes | `17caa474d9ba583d477511b7734565888b7740457fbff4214d6359046ded7e19` |
| Original V8 `MANIFEST_SHA256_V8.json` | Source file | 452 file entries |
| Internal SHA-256 verification | Original unpacked source, file by file | 452/452 match |
| SHA-256 of original manifest file | SHA of exact JSON bytes | `c8d248cb351aa57de315edb370f3143da6b0fe1954df48fabf618d12e55146d3` |
| Extra source receipt | Generated after extraction, `SOURCE_RECOVERY_MANIFEST.json` | SHA-256 `0160a155eb8f60fb0a243a8fb197f4fff170f1366742e6b2067e41d306fbc4e1` |
| Git tree of original import | [`eab0d0b1`](https://github.com/PetrFedin/magadan/commit/eab0d0b1e418558914a448a21cf496982ac10a1d) | tree `fd7e050056ac6888861778582a31ce231b701949` |
| GitHub SHA-1 blob hashes and sizes | All original files and one extra receipt | **454/454 exact matches** |
| Local complete Python synthetic regression | Completed independent groups from recovered V8 source | **281 passed** |
| Local JS synthetic tests | Node client test suite | **63 passed** |
| Actual GitHub application CI | [V8 CI #40757324789](https://github.com/PetrFedin/magadan/actions/runs/40757324789) and retry | **NOT GREEN**, `runner_id=0`, no job steps |
| External trusted source receipt | A reviewer independently checks original ZIP/manifest against immutable external record | **NOT ATTESTED** |

## Very important distinction: two manifests and later development

The original `MANIFEST_SHA256_V8.json` and `SOURCE_RECOVERY_MANIFEST.json` certify the **imported release baseline** in immutable Git commit `eab0d0b1`. They must NEVER be edited to silently absorb later changes.

Any changes on the feature branch after `eab0d0b1` (such as the current project README, CI workflows or engineering fixes) are **explicit later Git commits** with own history and need their own CI and review. An application regression workflow should verify historical manifest bytes **from the pinned original import commit** and test current working-tree code. Requiring the entire evolving feature branch to match the immutable original manifest would incorrectly block any legitimate future development.

The independent `SOURCE_ADMISSION` gate must obtain two separately accepted hash pins: the ZIP SHA-256 and the imported source receipt SHA-256. Current locally computed numbers are evidence of integrity, **not** an independent third-party attestation. Do not set repository variables just to turn the check green.

## Boundaries not closed

- GitHub application CI GREEN on a single SHA and peer review.
- Dedicated PostgreSQL 17 RLS with negative tenant, concurrent writes and restore tests.
- Enterprise OIDC/MFA, signed external immutable audit, managed secrets, incident recovery.
- Actual independent engineering validation (external solver and owner-authorized measurements).
- Real Magadan asset permissions, qualified consultant, approved tariffs/costs, WBS, construction/commissioning and post-investment measured savings.

**LAB SOURCE INTEGRITY CONFIRMED / EXTERNAL SOURCE ATTESTATION HOLD / APPLICATION CI NOT GREEN / PRODUCTION HOLD.**
