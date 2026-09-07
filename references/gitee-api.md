# Gitee API boundary

Read this file only after `check_gitee_token.py` reports a local token present and publication preconditions are otherwise satisfiable.

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
