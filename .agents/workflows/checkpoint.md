# Workflow: Checkpoint & Git Protocol (`checkpoint.md`)

Use this workflow before creating any checkpoint commit in the repository to guarantee repository cleanliness, security, and traceability.

---

## 1. Pre-Commit Hygiene & Security Audit
1. **Check Working Tree Status**:
   ```bash
   git status
   ```
2. **Review Full Git Diff**:
   ```bash
   git diff --staged
   ```
3. **Verify Zero Secrets / Sensitive Artifacts**:
   - Confirm **NO** `.env`, `.env.local`, `.pem`, `.key`, or credentials files are staged.
   - Confirm **NO** `node_modules`, `dist`, `__pycache__`, `.venv`, or binary files are staged.
   - Confirm all untracked files are intentional.

---

## 2. Verification Gate
Run the verification suite defined in [.agents/workflows/verify.md](.agents/workflows/verify.md).
- Proceed **ONLY** if all checks pass without errors.

---

## 3. Atomic Commit Creation
1. Stage modified and new project files intentionally:
   ```bash
   git add <specific-files-or-directories>
   ```
2. Commit with a conventional semantic message format:
   - `feat(scope): ...`
   - `fix(scope): ...`
   - `docs(scope): ...`
   - `refactor(scope): ...`
   - `test(scope): ...`
   - `chore(scope): ...`

   *Example:*
   ```bash
   git commit -m "docs(init): establish project architecture and SIH26069 source of truth"
   ```

---

## 4. Checkpoint Reporting
After committing, report to the user:
- Commit SHA hash (short form: 7 characters)
- Commit message
- Summary of modified components
