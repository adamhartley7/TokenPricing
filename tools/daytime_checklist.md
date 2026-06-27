# Daytime 100/100 Verification Checklist

**95 is automated. 100 requires you.** This is the 5-point bridge from what the pipeline produced overnight to what you sign off on.

---

## Point 96: Real Filesystem Testing (15 min)

Run these on your Windows 11 machine. No LLM can do this — it needs a real OS.

### Symlink escape test
```powershell
# In PowerShell, inside the allowlisted directory:
mkdir C:\7cs-cowork-test\allowed
New-Item -ItemType SymbolicLink -Path "C:\7cs-cowork-test\allowed\escape" -Target "C:\Windows\System32"
# The sandbox must REJECT access through this symlink.
# If it lets you read C:\Windows\System32 through the symlink: FAIL.
```

### Path traversal test
```powershell
# Try to access a file outside the allowlist:
# The sandbox must reject: ../../.anthropic-key
# If it serves the key file: CRITICAL FAIL.
```

### Race condition test
```powershell
# Delete the allowlist directory while the agent is running.
# The agent must handle this gracefully — no crash, no undefined behavior.
```

### Permission test
```powershell
# Create a read-only file inside the allowlist.
# Ask the agent to modify it.
# It must detect the permission issue and report it, not crash.
```

**Sign off:** ___ All 4 tests pass. The sandbox blocks escape, traversal, and handles failure gracefully.

---

## Point 97: Permission Edge-Case Testing (10 min)

### Concurrent write test
```powershell
# Open two terminals. In both, ask the agent to write to the same file.
# One must succeed, one must get a clear "file locked" message.
# Neither may corrupt the file.
```

### Nested allowlist test
```powershell
# Allowlist: C:\7cs-cowork-test\
# Ask the agent to create a file at C:\7cs-cowork-test\subfolder\..\outside
# The path resolves outside the allowlist. Must be REJECTED.
```

### Unicode path test
```powershell
# Create a file with Unicode in the name: café.txt
# Ask the agent to read it.
# Must handle Unicode paths correctly.
```

### Empty allowlist test
```powershell
# Set allowlist to an empty directory.
# Ask the agent to "list all files."
# Must return empty, not error.
```

**Sign off:** ___ Edge cases handled. No crashes, no escapes, no undefined behavior.

---

## Point 98: Human Code Review (30 min)

Read these files from the overnight output:
1. `4_review.md` — Opus's overall review
2. `5_security_audit.md` — vulnerability findings
3. `7_integration_audit.md` — cross-file issues
4. `8_fixes.md` — what DeepSeek changed

### Review checklist
- [ ] Did Opus hallucinate any reviewed files? (Compare file names in the review to files that actually exist in the build output.)
- [ ] Are any CRITICAL or HIGH security findings unresolved in `8_fixes.md`?
- [ ] Do all function signatures in `2_build_core.md` match their callers in `3_build_ui.md`?
- [ ] Does the confirmation gate actually require confirmation for destructive ops, or is it a bypassable flag?
- [ ] Is `allowlist` enforced at filesystem level or just in a type definition?

**Sign off:** ___ I have read the code. The security claims are real, not aspirational. No hallucinated review content.

---

## Point 99: Deployment Validation (15 min)

Run the overnight build in the actual 7C's app.

1. Copy the generated files into the 7C's gateway directory
2. Start the gateway: `cd 7ces\gateway && .venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8787`
3. Open `http://localhost:8787/chat`
4. Test the Cowork tab with a simple task: "List files in the allowed directory"
5. Test with a destructive task: "Delete the test file" — must show confirmation gate
6. Check the cost meter: `http://localhost:8787/meter` — costs must be attributed per-step

**Sign off:** ___ The Cowork tab loads. The agent responds. The confirmation gate fires. The cost meter tracks spend.

---

## Point 100: User Intent Verification

This is the one no model can do. Read the original task description you gave the pipeline. Then look at what it built. Ask yourself:

1. **Is this what I meant, or just what I described?** The pipeline builds to the spec. Only you know if the spec captured your intent.

2. **Would I trust this with real files?** The sandbox has tests. But would you point it at your actual Documents folder?

3. **Does it feel like a Cowork tab?** Not "does it pass tests" — does it feel like the thing you wanted when you said "Cowork tab"?

4. **Is anything missing that I assumed was obvious?** The pipeline can't read your mind. If you assumed "the confirmation gate should have a timeout" but didn't say so, that's on you — and you catch it here.

**Sign off:** ___ Yes. This is the Cowork tab I meant. 100/100.

---

## Quick Reference

| Point | What | Time | Who |
|-------|------|------|-----|
| 96 | Real filesystem tests | 15 min | You + Windows |
| 97 | Permission edge cases | 10 min | You + PowerShell |
| 98 | Human code review | 30 min | You reading output |
| 99 | Deployment validation | 15 min | You + 7C's app |
| 100 | Intent verification | 5 min | You thinking |
| **Total** | | **~75 min** | |

---

## After Sign-Off

If all 5 points pass: merge the overnight build into the 7C's app, commit, push. The Cowork tab ships at 100/100.

If any point fails: note what failed, fix it (or have DeepSeek fix it), re-run the failing verification. The overnight pipeline did the heavy lifting — daytime is verification, not construction.
