# gitfc

A simple CLI tool for making git commits with a custom date. Instead of typing the full git command every time, you just run `gitfc`.

## Installation

Clone the repo and run:

```
make install
```

If you're working on the tool itself and want changes to take effect without reinstalling:

```
make dev
```

To uninstall:

```
make uninstall
```

## Usage

```
gitfc [flags] "commit message" [date]
```

Both the message and date are optional depending on which flags you use. If you skip the date, it defaults to right now.

## Date formats

| Input | What it means |
|---|---|
| *(nothing)* | Current date and time |
| `+15m` | 15 minutes from now |
| `-2h` | 2 hours ago |
| `+3d` | 3 days from now |
| `14:30` | Today at 14:30 |
| `2026-04-01` | That date at midnight |
| `2026-04-01 14:30:00` | Exact date and time |

## Flags

| Flag | What it does |
|---|---|
| `-a` | Stage all changes before committing (`git add -A`) |
| `--amend` | Amend the previous commit instead of creating a new one |
| `-v`, `--verbose` | Print commit details (hash, date, message) after committing |
| `-p`, `--push` | Push to remote after committing |
| `--dry-run` | Show the command and resolved date without actually committing |

## Examples

```
# Commit with current date and time
gitfc "my message"

# Commit staged changes, dated 2 days ago
gitfc "my message" "-2d"

# Stage everything and commit with a specific date
gitfc -a "my message" "2026-03-15 10:00:00"

# Amend the last commit's date to 1 hour ago, keep message
gitfc --amend "-1h"

# Amend with a new message and date
gitfc --amend "new message" "2026-04-01"

# Commit, push, and show details
gitfc -a -v -p "my message" "+30m"

# Preview what would happen without committing
gitfc --dry-run "my message" "2026-04-01 09:00:00"
```

**Disclaimer:** AI was used to generate most of this tool.