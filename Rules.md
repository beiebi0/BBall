# Rules

Development workflow rules for the BBall project.

---

## Before Taking Any Action

1. **Read all `.md` files** in the project root before starting work:
   - `Task.md` — current tasks and status
   - `Master_Plan.md` — overall architecture and design
   - `README.md` — project overview and setup
   - `User_journey.md` — end-to-end user flow
   - `Implementation_plan.md` — development history and phases
   - `Rules.md` — this file

## Before Writing Code

2. **Check `Task.md`** to confirm the current task matches what you're about to work on. Do not start work that isn't tracked there.

## After Completing a Task

3. **Write a test** for the completed work before moving on. The task is not done until its test passes.
4. **Mark the task as complete** (`[x]`) in `Task.md` only after the test passes.
5. Move on to the next task.

## After Any Code Change or `git pull`

6. **Update all `.md` files** to reflect the changes (new features, bug fixes, architectural changes, completed tasks, etc.).
7. **Review the updates with the user** before committing — do not commit silently.

## Committing

8. **Documentation and code changes go in the same commit.** Never commit code without updating the relevant docs, and never commit doc updates separately from the code they describe.
