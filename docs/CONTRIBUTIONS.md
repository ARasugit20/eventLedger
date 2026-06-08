# Contribution & GitHub Graph Guide

This doc explains why commits may not show on your GitHub contribution graph and how to fix it.

## Why green squares might be missing

GitHub counts a contribution when **all** of these are true:

1. The commit is on the **default branch** (`main`) or a merged PR
2. The commit **author email** matches a **verified** email on your GitHub account
3. The commit date falls within GitHub's contribution window (last year)
4. The repo is not a fork (unless you open a PR to the parent)

Common causes of missing squares:

| Symptom | Likely cause |
|---------|----------------|
| Commits exist on GitHub but no greens | Author email not verified or not linked to your account |
| Greens on unexpected dates | Commit **timestamps** differ from when you pushed |
| Local commits never appear | Not pushed to `origin/main` |

## Fix author email

Check your local config:

```bash
git config user.email
git config user.name
```

Set the email that is **verified** on GitHub:

```bash
git config user.email "you@example.com"
git config user.name "Your Name"
```

Verify at: **GitHub → Settings → Emails**

## Check commit attribution before push

```bash
git log -3 --format='%h %ae %ad %s'
```

Confirm `%ae` matches a verified GitHub email.

## When the graph updates

- Pushes to `main` update immediately after GitHub processes the push
- **Amended or rebased** commits get **new SHAs and dates** — squares move to those dates
- Force-pushes rewrite history; old contribution dates may disappear

## Recommended workflow for this repo

1. Configure verified email locally
2. Make logical, meaningful commits (see project plan)
3. Run quality gates before push:

```bash
make test-cov
ruff check app tests analytics scripts
```

4. Push to `main`:

```bash
git push origin main
```

5. Confirm on GitHub: **Insights → Contributors** and your profile contribution graph

## Rewriting history (use carefully)

If past commits used the wrong email:

```bash
git rebase -i HEAD~N   # edit commits
# or
git commit --amend --author="Name <verified@email.com>" --no-edit
git push --force-with-lease origin main
```

Only rewrite history on repos you own. Force-push changes contribution dates.

## Questions?

Open an issue on [github.com/ARasugit20/eventLedger](https://github.com/ARasugit20/eventLedger) with:

- Output of `git log -1 --format='%ae %ad'`
- Screenshot of GitHub → Settings → Emails (redact addresses if needed)
