I'll audit the provided code, focusing on the path-scoping logic which is the core security control.

# Security Audit: Cowork Scoped Filesystem

## Summary
The code implements a deny-by-default allowlist for filesystem access, but contains **several critical flaws** in its path-validation logic. Most importantly, the actual enforcement function (`_validate`/`_check`) is truncated — but the documented design and `from_allowlist` already contain exploitable defects.

---

## Findings

### CRITICAL #1 — TOCTOU race: realpath check decoupled from open()
**Where:** Design described in `coworkfs.py` docstring ("canonicalize... BEFORE any check" then later open).

The audit description says paths are canonicalized with `realpath`, validated, and *then* operated on. Between the `realpath` validation and the actual `open()`/read/write syscall, an attacker who controls any directory along the path can swap a component for a symlink pointing outside the allowlist.

**Exploit:** Validate `/allowed/file` (real file), then replace `/allowed` with a symlink to `/etc` before the `open()` fires.

**Fix:** Eliminate the gap. Open with `O_NOFOLLOW` on the final component and resolve+open directory components incrementally using `os.open(..., O_NOFOLLOW)` with `dir_fd`, or use `openat2(RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS)` on Linux. Re-validate the realpath of the opened fd via `/proc/self/fd/N` after opening. Never validate a path string and then independently re-resolve it in the syscall.

---

### CRITICAL #2 — New-file writes validate parent only, enabling symlink-target escape
**Where:** docstring: "For writes to a new file, we validate the canonical parent directory instead."

Validating only the parent does **not** prevent writing through a symlink *named as the new file*, nor does it prevent the leaf being a pre-planted symlink. If `target` is a symlink (or becomes one) whose name doesn't yet "exist" as a regular file, `realpath(parent)` passes while the eventual `open(target, 'w')` follows the symlink and writes outside the allowlist.

**Fix:** Open new files with `os.open(path, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW)`. `O_NOFOLLOW` rejects a symlink leaf; `O_EXCL` avoids clobbering. Use `dir_fd` from the validated parent fd rather than re-walking the path.

---

### CRITICAL #3 — Non-existent paths are silently accepted into the allowlist
**Where:** `cowork_config._normalize` and `ScopedFS.from_allowlist`.

```python
if os.path.isdir(p) or p not in roots:
    roots.append(p)
```
This condition is logically broken: `p not in roots` is true for essentially every new path, so **every entry is appended regardless of whether it is a real directory**. A non-existent or attacker-typoed root that later gets created (or symlinked) becomes a live allowed root. Also, `realpath` of a non-existent path returns a normalized string that may later resolve differently once the path is created.

**Severity:** CRITICAL — defeats deny-by-default integrity.

**Fix:**
```python
if os.path.isdir(p) and p not in roots:
    roots.append(p)
```
Require roots to exist as real directories at load time, and reject (log) any that don't.

---

### HIGH #4 — relpath-based containment is unreliable on case-insensitive / UNC / drive-relative Windows paths
**Where:** docstring: containment via `os.path.relpath(target, root)` not starting with `..`.

`relpath` is a **string** operation. On Windows it is case-insensitive vs. case-sensitive mismatches, 8.3 short names (`PROGRA~1`), UNC paths (`\\?\`), and extended-length prefixes can cause a true-inside path to look outside or vice-versa. Also, a root like `/allow` will incorrectly *match* sibling `/allow-evil` if you instead used `startswith`; `relpath` mitigates that case but introduces the Windows ambiguities above.

**Fix:** Use `os.path.commonpath([root, target]) == root` after both are realpath-canonicalized, and on Windows normalize case explicitly (`os.path.normcase`) for both sides. Reject UNC/`\\?\` unless explicitly allowlisted.

---

### HIGH #5 — `_normalize` swallows realpath OSError and proceeds with unresolved path
**Where:** `cowork_config._normalize` and `ScopedFS.from_allowlist` (`except OSError: pass`).

If `realpath` raises (e.g., loop, permission), the code keeps the *non-canonical* `abspath` value and treats it as canonical. An unresolved path containing an unresolved symlink/junction can then pass containment checks while actually pointing elsewhere.

**Fix:** On `realpath` failure, **reject** the path (drop from allowlist / raise `PathDenied`) rather than silently using the un-resolved form.

---

### MEDIUM #6 — `expanduser` introduces environment-controlled roots
**Where:** `_normalize` / `from_allowlist` use `os.path.expanduser(raw)`.

`~` expansion depends on `HOME`/`USERPROFILE`, which an attacker controlling the environment (or a less-privileged caller) can manipulate to redirect an allowlist root. Combined with the env-var allowlist source (`COWORK_ALLOWLIST`), the trust boundary is loose.

**Fix:** Require absolute paths in config; reject entries containing `~`. If user expansion is needed, resolve `HOME` from a trusted source, not the ambient environment.

---

### MEDIUM #7 — `COWORK_ALLOWLIST` env var overrides file config (privilege/scope escalation)
**Where:** `load_allowlist` resolution order: env var takes precedence over the JSON file.

Any process able to set this environment variable can **widen** the agent's filesystem scope at runtime, bypassing the carefully-managed JSON allowlist. For an agent that may be invoked by partially-trusted callers, this is an escalation vector.

**Fix:** Treat the JSON file as authoritative for the upper bound. If env override is permitted, **intersect** env paths with file paths rather than replacing, and gate the override behind an explicit trusted flag. Document and restrict who can set the env var.

---

### MEDIUM #8 — Empty/malformed config fails open to "empty" but errors are silently ignored
**Where:** `load_allowlist` `except (json.JSONDecodeError, OSError): pass`.

Silently ignoring a corrupt/unreadable allowlist file yields an empty allowlist (correctly deny-all here), but masks tampering. Worse, if a future caller treats "empty allowlist" specially, behavior may invert. Silent failure also hides an attacker who corrupts the file to disrupt config loading.

**Fix:** Log a loud error on parse/IO failure and fail closed explicitly. Do not silently `pass`.

---

### LOW #9 — Allowlist file permissions not validated
**Where:** `cowork_allowlist.json` loading.

If the JSON file is world-writable, any local user can append roots and escalate the agent's access.

**Fix:** Before reading, verify the file is owned by the expected user and not group/world-writable (`os.stat` mode check). Refuse to load otherwise.

---

### LOW #10 — Dedup `seen` set is case/normalization sensitive, may keep duplicate roots
**Where:** `load_allowlist` dedup and `from_allowlist`.

On Windows, `C:\Foo` and `c:\foo` produce distinct `seen` keys, leaving redundant roots and inconsistent matching later.

**Fix:** Key dedup on `os.path.normcase(norm)`.

---

## Key Recommendations (priority order)
1. **Replace string-based validation with fd-based, race-free opens** (`O_NOFOLLOW`, `dir_fd`, `openat2 RESOLVE_BENEATH` on Linux). This fixes #1, #2, and #4 structurally.
2. Fix the broken `from_allowlist` condition (#3) — require roots to exist.
3. Reject (don't swallow) `realpath` failures (#5).
4. Lock down config sourcing: drop/restrict env override and `~` expansion (#6, #7), validate file perms (#9).
5. Use `commonpath` + `normcase` for containment (#4, #10).

**Note:** The core enforcement method (`_check`/`read`/`write`) was truncated in the submission. The most critical verdict — whether validation and the syscall are atomic — depends on that code. Based on the documented design ("canonicalize BEFORE any check"), findings #1 and #2 stand and are exploitable. Please provide the remaining `coworkfs.py` body for a complete confirmation.