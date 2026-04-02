---
name: commit
description: Create a git commit with a well-crafted message
allowed_tools: [Bash, Read, Grep]
context: inline
---

Create a git commit for the current changes. Follow these steps:

1. Run `git status` and `git diff --staged` to see what will be committed
2. If nothing is staged, run `git diff` to see unstaged changes and suggest what to stage
3. Analyze the changes and draft a concise commit message:
   - Summarize the nature of the changes (feature, fix, refactor, etc.)
   - Focus on "why" rather than "what"
   - Keep the first line under 72 characters
4. Create the commit

$ARGUMENTS
