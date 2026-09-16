# Leaf: Basic review before publication

Load for `REVIEW_EXISTING`. Read [review-basic.md](../review-basic.md) for the eight required checks, safety-before-execution order, ZIP limit and source/artifact-bound evidence. Review preserves extension source. Authorized builds/checks may produce artifacts and evidence; correct source defects in development, then refresh affected checks.

This leaf follows CREATE/CONVERT/UPGRADE and precedes PUBLISH. An existing project may also enter it directly. Reuse valid producer evidence rather than repeating work. Missing build/display/behavior evidence is BLOCKED, not a successful static-only Basic. Report P1/P2 suggestions without requiring fixes; unresolved P0 or independent gates block.

Run `scripts/check_basic_review.py`, attach its passing report as `basic_review`, and hand off `REVIEWED_BASIC` with all eight required checks. A failed or incomplete report cannot advance to publication. Resume after obtaining the missing evidence; do not edit logs to manufacture PASS.
