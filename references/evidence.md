# Review stages and evidence

| Stage | Scope |
| --- | --- |
| Lite | After entering a producer: compare official catalog/Gitee candidates, resolve identity collisions and an existing base/fork |
| Basic | After production, before publication: source/security checks, successful build, block display and representative behavior, ZIP ≤ 5,000,000 bytes |

The [Basic contract](review-basic.md) binds source hash, exact ZIP hash and actual evidence files. Missing required observations are NOT_RUN/BLOCKED, not a static-only Basic pass. Build proves the recorded build scope; representative tests do not prove all device behavior. Reuse evidence only while source, artifact, scope and environment remain valid.

Use STATIC for source checks, HOST_BUILD for build/display observations, and RUNTIME for exercised behavior. Describe command/method, inputs, expected and actual results. Record user-confirmed GUI observations or actual observation evidence; never infer visibility from build success.

[P0/P1/P2](issue-levels.md) classify defects independently. Preserve advisory FAIL with evidence; don't relabel it PASS. Review preserves extension source; authorized builds and checks may produce artifacts/evidence. Source edits require affected checks again.
