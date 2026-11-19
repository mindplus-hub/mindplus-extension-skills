# Skill update policy

Questions and local maintenance of this skill use the installed files directly. For project work, run the update check once per session and reuse its result across tasks and resumes. Check again only for an explicit update request or a user-reported newer release; explicit offline or pinned use skips automatic checks.

When a check is due, run `python <absolute path of this skill directory>/scripts/update_skill.py` from any working directory. Use the active skill path reported by the client; never search broadly for another copy or run from `.mindplus-skill-backups`, staging or packaged previews. The script never renames the skill directory. Compare installed `VERSION` with stable releases at `https://gitee.com/mind-plus/mindplus-extension-skills/releases/`. Runtime files at root/one child directory select the WB ZIP; deeper runtime directories select the universal ZIP. Install only a newer matching package, retaining one compressed rollback ZIP outside skill discovery directories. Do not automatically delete historical backups or staging directories or force overwrite local Git changes.

For a user-reported newer release, add `--refresh` to bypass the one-hour cache. On success, require the returned `installation_root` to be the active skill and `installed_version` to match its `VERSION`; updating another copy is not success. On `UPDATED`, reload only this directory's `SKILL.md`, then read references when needed. On `SKIPPED` or failure, briefly report the reason and continue with the unchanged installed version; do not retry the same check automatically.

On a Release API HTTP 403 or 429, the updater checks the same repository's public `/releases/latest` page once and applies the same package and SHA-256 checks.

## Download integrity

Select the latest stable Release's explicit `-workbuddy.zip` or `-universal.zip` according to the active layout, plus its exact same-name `.zip.sha256` attachment. Do not fall back to Gitee's automatic source archive or an older release when required attachments are missing. Every installation downloads the checksum again, even when release selection uses the cache. `--check-only` reports availability, not successful package verification.

Only HTTPS Gitee hosts are allowed for initial URLs and every redirect. Reject credentials/nonstandard ports, responses exceeding 64 MiB (checksum: 4 KiB), declared-length truncation, and downloads exceeding the bounded timeout. Require a SHA-256 line binding the digest to the exact ZIP filename. Compare the downloaded ZIP bytes before extraction, backup or installation; then retain the existing archive-path, unpacked-size, version/layout and installed-file checks.

Missing, malformed or mismatching integrity evidence blocks the update with `UPDATE_INTEGRITY_FAILED`. Keep using the unchanged installation and report that the update did not occur; never bypass verification. Network failures also leave the current installation untouched. SHA-256 verifies consistency with the trusted HTTPS Release; it is not a publisher signature.

Release maintenance uses `tools/pack_workbuddy.py` to build and publish four explicit attachments: WorkBuddy ZIP, universal source ZIP (original directory structure), and each ZIP's `.sha256`. Both ZIPs come from the same source snapshot; publication verifies all four uploaded attachments before reporting success.
