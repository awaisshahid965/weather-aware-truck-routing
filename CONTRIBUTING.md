# Contributing

## Setup

With Node.js 24.22.0 and uv installed, run these once in the repository root:

1. `npm install`: installs the git hooks and root tools.
2. `npm run setup`: installs both apps and creates their local env files.

## Branches

- `main` is always releasable. Never commit to it directly.
- Branch from `main`. Name the branch `<type>/<short-topic>`, for example `feat/route-checkpoints` or `fix/heatmap-slider`.
- Keep one concern per branch. Open a pull request into `main`. Delete the branch after it merges.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). The `commit-msg` hook rejects anything else.

```text
<type>(<optional-scope>): <summary>
```

| Type | Use it for |
|---|---|
| `feat` | A new user-facing capability |
| `fix` | A bug fix |
| `refactor` | A code change that does not change behaviour |
| `perf` | A performance improvement |
| `test` | Adding or fixing tests only |
| `docs` | Documentation only |
| `build` | Dependencies, build tooling, Dockerfiles |
| `ci` | CI workflows |
| `chore` | Anything else (repository housekeeping) |
| `revert` | Reverting an earlier commit |

- Scope: `backend` or `frontend`. Leave it out for changes across the whole repository.
- Summary: imperative mood, lowercase, no trailing period. Example: `feat(backend): add route checkpoint sampling`.
- Add `!` after the type or scope for a breaking change: `feat(backend)!: rename route plan fields`.

## Git hooks

| Hook | What it runs |
|---|---|
| `pre-commit` | lint-staged, on staged files only. Root JSON and YAML: Prettier. App files: the rules in that app's `.lintstagedrc.json`. |
| `commit-msg` | The commit message rule above. |

Do not skip hooks with `--no-verify`. If a hook is wrong, fix the hook.

## Before opening a pull request

Run `npm run check` in the repository root. It runs the root formatting check and every backend and frontend check. CI runs the same app checks.

To check one app only: `npm run check:backend` or `npm run check:frontend`.

Fill in the pull request template: what changed, why, and how you tested it.

## Dependencies

- Versions are pinned exactly. Lockfiles are committed: `package-lock.json`, `backend/uv.lock`.
- Dependabot opens update PRs every week. Review the changelog, run the checks, then merge.
- Upgrade on purpose, in its own pull request, with a `build(deps): ...` commit.
