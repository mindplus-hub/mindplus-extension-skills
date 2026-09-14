# Gitee API boundary

Read this file only after `check_gitee_token.py` reports a local token present and the requested publication or fork preconditions are otherwise satisfiable. Fork preparation is described in [workflows/upgrade.md](workflows/upgrade.md).

## Verified interface baseline

Checked on 2026-09-01 against Gitee-hosted OpenAPI SDK documentation:

- API base: `https://gitee.com/api/v5`.
- Personal repository creation: `POST /user/repos`.
- Organization repository creation: `POST /orgs/{org}/repos`.
- Repository lookup: `GET /repos/{owner}/{repo}`.
- These operations use OAuth2 access-token authorization.
- Gitee recommends personal access tokens instead of account passwords for HTTPS Git operations.

Primary references:

- `https://gitee.com/sdk/gitee5j/blob/main/docs/RepositoriesApi.md`
- `https://gitee.com/profile/personal_access_tokens` (requires the user's Gitee login)

Treat endpoint schemas and token permissions as version-sensitive. Recheck the current official documentation before implementing or changing the remote adapter.

## Safety rules

- Never send a create request until owner/org, name, description, and visibility are explicit.
- Never send the token as a URL query parameter or persist it in a request/response log.
- Redact authorization headers and credential-bearing diagnostics.
- A new empty remote is a real external side effect. Record its URL and result even if a later push fails.
- Do not delete or recreate a colliding repository automatically.
- Do not treat an HTTP success alone as publication success; verify the intended owner/name/visibility and later the pushed ref/SHA.

## Repository Topic addition (0.2.1)

`GET /repos/{owner}/{repo}/project_labels` lists repository Topics; POST on the same path adds a JSON string array. Use `["MindPlus-Ext2"]`, not issue `/labels` or Git `/tags`. Never replace all Topics with PUT. Read back to verify.

Interface reference checked 2026-09-10: [LabelsApi SDK contract](https://github.com/gitee-php/gitee-sdk/blob/main/docs/Api/LabelsApi.md#postv5reposownerrepoprojectlabels). This documents POST string-array input and ProjectLabel-array output. Reuse the existing in-memory token header transport; a denied request blocks Topic completion and must never trigger a credential-bearing URL fallback. Live token permissions and server acceptance require integration verification; no token value belongs in evidence.

Repository visibility update uses `PATCH /repos/{owner}/{repo}` with the existing display `name` and `private: false`. Read back the same repository via GET; PATCH success alone is insufficient.

## Creation-time visibility (0.3.3)

Verified 2026-09-14 against live Gitee responses, so these are observations rather than SDK-schema claims:

- `POST /orgs/{org}/repos` with `{"private": false, "auto_init": false}` **succeeds**: HTTP 201 and the created repository reports `"private": false`. An empty repository can therefore be created directly as public; the older "Gitee refuses empty public repositories (HTTP 422)" assumption does not hold on this path, so a requested-public repository should not be created private first.
- The same body against `POST /user/repos` returned HTTP 201 with `"private": true` — a **silent downgrade with no error**. A creation-time public request is therefore never evidence of public visibility: always read `private` back from the created repository.
- `auto_init: true` makes the repository non-empty, but it also creates a remote initial commit whose history is unrelated to the local root commit, so the push stops being a fast-forward. Do not use it as a visibility workaround.
- Changing visibility **after** creation is a different permission than creating: an organization admin holding `permission.admin: true` on the repository still receives `401 修改仓库公开属性失败，您没有此项权限`. Only the repository/namespace owner can change it. Creation-time visibility avoids this rule entirely.
- `DELETE /repos/{owner}/{repo}` succeeded (HTTP 204) for a repository created by the same credential, so throwaway probes created during verification can be removed.
