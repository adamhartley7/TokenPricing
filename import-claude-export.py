#!/usr/bin/env python3
"""
import-claude-export.py — turn an Anthropic "Export data" zip into clean Markdown
ready to ingest into a memory/RAG store (mem0, claude-mem, LibreChat RAG, etc.).

PRIVACY: input and output are PERSONAL. Output goes to ./_memory_import/ which is
git-ignored. This script is 100% local — it reads a zip and writes files. It makes
NO network calls and transmits nothing.

Usage:
    python import-claude-export.py --zip path/to/export.zip            # writes ./_memory_import/
    python import-claude-export.py --zip path/to/export.zip --dry-run  # parse + count only, writes nothing
    python import-claude-export.py --zip path/to/export.zip --out my_dir

Export schema handled (verified June 2026):
    conversations.json : [ {uuid, name, summary, created_at, chat_messages:[{sender, text, content, created_at}]} ]
    memories.json      : [ {conversations_memory, project_memories, account_uuid} ]
    projects/*.json    : Claude.ai project export objects
    design_chats/*.json: design-mode chats
"""
import argparse
import json
import os
import re
import sys
import zipfile

def slug(s, maxlen=60):
    s = (s or "untitled").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s or "untitled")[:maxlen]

def msg_text(m):
    """Prefer the flat 'text'; fall back to joining 'content' blocks."""
    t = (m.get("text") or "").strip()
    if t:
        return t
    parts = []
    for block in (m.get("content") or []):
        if isinstance(block, dict):
            bt = block.get("text") or block.get("input") or ""
            if isinstance(bt, str) and bt.strip():
                parts.append(bt.strip())
    return "\n".join(parts).strip()

def load_json_member(zf, name):
    with zf.open(name) as fh:
        return json.load(fh)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True, help="path to the Anthropic export .zip")
    ap.add_argument("--out", default="_memory_import", help="output directory (git-ignored)")
    ap.add_argument("--dry-run", action="store_true", help="parse and count only; write nothing")
    args = ap.parse_args()

    if not os.path.exists(args.zip):
        sys.exit(f"ERROR: zip not found: {args.zip}")

    zf = zipfile.ZipFile(args.zip)
    names = set(zf.namelist())

    convs = load_json_member(zf, "conversations.json") if "conversations.json" in names else []
    memories = load_json_member(zf, "memories.json") if "memories.json" in names else []
    project_members = [n for n in names if n.startswith("projects/") and n.endswith(".json")]
    design_members = [n for n in names if n.startswith("design_chats/") and n.endswith(".json")]

    total_msgs = sum(len(c.get("chat_messages") or []) for c in convs)
    print(f"Parsed: {len(convs)} conversations ({total_msgs} messages), "
          f"{len(project_members)} projects, {len(design_members)} design chats, "
          f"{'memory present' if memories else 'no memory'}.")

    if args.dry_run:
        print("--dry-run: nothing written.")
        return

    out = args.out
    cdir = os.path.join(out, "conversations")
    pdir = os.path.join(out, "projects")
    os.makedirs(cdir, exist_ok=True)
    os.makedirs(pdir, exist_ok=True)

    # --- conversations -> one Markdown file each ---
    written = 0
    for c in convs:
        uuid = (c.get("uuid") or "")[:8]
        name = c.get("name") or "untitled"
        lines = [f"# {name}", ""]
        if c.get("created_at"):
            lines.append(f"_created: {c['created_at']}_")
        if c.get("summary"):
            lines.append(f"\n> {c['summary']}\n")
        lines.append("")
        for m in (c.get("chat_messages") or []):
            who = (m.get("sender") or "?").capitalize()
            txt = msg_text(m)
            if txt:
                lines.append(f"**{who}:** {txt}\n")
        fname = f"{slug(name)}-{uuid}.md" if uuid else f"{slug(name)}.md"
        with open(os.path.join(cdir, fname), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        written += 1

    # --- memory -> single Markdown file ---
    if memories:
        m0 = memories[0] if isinstance(memories, list) else memories
        lines = ["# Claude memory export", ""]
        cm = m0.get("conversations_memory")
        pm = m0.get("project_memories")
        if cm:
            lines += ["## Conversations memory", "", json.dumps(cm, indent=2, ensure_ascii=False)
                      if not isinstance(cm, str) else cm, ""]
        if pm:
            lines += ["## Project memories", "", json.dumps(pm, indent=2, ensure_ascii=False)
                      if not isinstance(pm, str) else pm, ""]
        with open(os.path.join(out, "memory.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

    # --- projects -> one Markdown file each (raw, since schema varies) ---
    for n in project_members:
        try:
            obj = load_json_member(zf, n)
        except Exception:
            continue
        base = slug(obj.get("name") if isinstance(obj, dict) else None) + "-" + os.path.basename(n).split(".")[0][:8]
        with open(os.path.join(pdir, base + ".md"), "w", encoding="utf-8") as fh:
            fh.write(f"# Project {obj.get('name','') if isinstance(obj, dict) else ''}\n\n")
            fh.write("```json\n" + json.dumps(obj, indent=2, ensure_ascii=False) + "\n```\n")

    print(f"Wrote {written} conversation files + memory + {len(project_members)} projects to ./{out}/")
    print("This folder is git-ignored. Next: ingest it into mem0 / claude-mem / LibreChat RAG (see ADVANCED-SETUP.md).")

if __name__ == "__main__":
    main()
