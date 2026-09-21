# Leaf: Basic review before publication

Load for `REVIEW_EXISTING`. Read [review-basic.md](../review-basic.md) for the eight required checks, safety-before-execution order, ZIP limit and source/artifact-bound evidence. Review preserves extension source. Authorized builds/checks may produce artifacts and evidence; correct source defects in development, then refresh affected checks.

This leaf follows CREATE/CONVERT/UPGRADE and precedes PUBLISH. An existing project may also enter it directly. Reuse valid producer evidence rather than repeating work. Missing build/display/behavior evidence is BLOCKED, not a successful static-only Basic. Report P1/P2 suggestions without requiring fixes; unresolved P0 or independent gates block.

Run `scripts/check_basic_review.py`, attach its passing report as `basic_review`, and hand off `REVIEWED_BASIC` with all eight required checks. A failed or incomplete report cannot advance to publication. Resume after obtaining the missing evidence; do not edit logs to manufacture PASS.

## Report-first branch

Take this branch when the request reads as findings-only: the user asks what is wrong with the project, or for an audit, without naming a repository, a release, a publication or a handoff. "列出具体问题", "不修改文件", "看有没有问题" and a bare "审核一下" all qualify.

Leave the branch — and run the full eight-check Basic instead — the moment the request mentions publication, Gitee, a repository, a version bump or a handoff, or when the project has already been staged for publication. When the intent is genuinely unclear and the project looks publishable, ask which one is wanted before spending evidence work rather than guessing in the expensive direction.

On this branch, execute the four static checks (`config_schema`, `extension_static_integrity`, `source_semantics`, `malicious_code_review`) plus a build when no current artifact exists, classify P0/P1/P2, and list `blocks_visible`, `blocks_functional` and `package_size` as not executed with the reason. Keep each executed check's evidence file in the run's `evidence/` directory and cite it with its SHA-256.

Finish with a terminal `REPORTED_FINDINGS` handoff, then run `mpa.py transition`. Record each static gate as its actual evidenced `PASS` or `FAIL` (a failed gate is P0); record `builder_build` as `PASS`, `FAIL`, or optional `NOT_RUN`; record the two observation checks and `package_size` as optional `NOT_RUN`. This handoff is valid only for a review-only route with no publication successor. It has no `basic_review` artifact and no `REVIEWED_BASIC` outcome; the `PASS` status means the findings report was delivered, not that the project passed Basic. The terminal transition retains the run evidence automatically.

Passed static evidence is reusable in a later full Basic while the project hash remains current. A failed gate must be fixed and rechecked; later Basic still adds the build, the two observation checks and the package size. Decide the branch up front from the request, before starting evidence work.
