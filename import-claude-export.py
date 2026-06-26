#!/usr/bin/env python3
"""
import-claude-export.py -- turn Anthropic "Export data" and DeepSeek chat exports into
clean Markdown ready to ingest into a memory/RAG store (mem0, claude-mem, LibreChat RAG, etc.).

PRIVACY: input and output are PERSONAL. Output goes to ./_memory_import/ (or --vault) which are
git-ignored. This script is 100% local -- it reads a zip or JSON file and writes files. It makes
NO network calls and transmits nothing.

Usage:
    # Anthropic export (auto-detected):
    python import-claude-export.py --zip path/to/export.zip

    # DeepSeek browser-extension ZIP export (auto-detected):
    python import-claude-export.py --zip path/to/deepseek-export.zip

    # DeepSeek single conversation JSON file:
    python import-claude-export.py --json path/to/conversation.json

    # DeepSeek directory of conversation JSON files:
    python import-claude-export.py --dir path/to/deepseek-export/

    # Write directly to the 7CEs-Vault History folder:
    python import-claude-export.py --zip path/to/export.zip --vault

    # Dry-run (parse + count only):
    python import-claude-export.py --zip path/to/export.zip --dry-run

Anthropic export schema (verified June 2026):
    conversations.json : [ {uuid, name, summary, created_at, chat_messages:[{sender, text, content, created_at}]} ]
    memories.json      : [ {conversations_memory, project_memories, account_uuid} ]
    projects/*.json    : Claude.ai project export objects
    design_chats/*.json: design-mode chats

DeepSeek export schema (browser extensions, verified June 2026):
    Per-conversation directories each containing conversation.json:
    {id, title, created_at, updated_at, messages: [{role, content, created_at, ...}]}
    Also supports flat array-of-conversations and single-JSON conversation files.
"""
import argparse
import json
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slug(s, maxlen=60):
    s = (s or "untitled").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s or "untitled")[:maxlen]


def msg_text(m):
    """Prefer the flat 'text'; fall back to joining 'content' blocks (Anthropic)."""
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


def ds_msg_text(m):
    """DeepSeek message content.  content is usually a plain string; handle
    list-of-parts blocks as well (some exporter versions)."""
    c = m.get("content", "")
    if isinstance(c, str):
        return c.strip()
    if isinstance(c, list):
        parts = []
        for block in c:
            if isinstance(block, dict):
                bt = block.get("text") or block.get("input") or ""
                if isinstance(bt, str) and bt.strip():
                    parts.append(bt.strip())
        return "\n".join(parts).strip()
    return str(c).strip()


def load_json_member(zf, name):
    with zf.open(name) as fh:
        return json.load(fh)


def short_id(s, n=8):
    """First n chars of an id/uuid, or empty string."""
    return (s or "")[:n]


def ts_to_date(ts):
    """Try common timestamp formats; return 'YYYY-MM-DD' or empty."""
    if not ts:
        return ""
    if isinstance(ts, (int, float)):
        try:
            return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        except Exception:
            return ""
    s = str(ts).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:26], fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return s[:10] if len(s) >= 10 else s


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_format(zf):
    """Return 'anthropic' | 'deepseek-zip' | None given a ZipFile."""
    names = set(zf.namelist())
    if "conversations.json" in names:
        # Could be Anthropic or a DeepSeek flat export.
        # Peek at the first object to decide.
        convs = load_json_member(zf, "conversations.json")
        if isinstance(convs, list) and convs:
            c0 = convs[0]
            # Anthropic has "uuid" and "chat_messages"; DeepSeek has "id" and "messages"
            if "uuid" in c0 and "chat_messages" in c0:
                return "anthropic"
            if "id" in c0 and "messages" in c0:
                return "deepseek-zip"
            # Fallback: messages vs chat_messages
            if "messages" in c0 and "chat_messages" not in c0:
                return "deepseek-zip"
        return "anthropic"  # best guess
    # DeepSeek browser-extension ZIP: per-conversation dirs with conversation.json
    ds_jsons = [n for n in names if n.endswith("/conversation.json")]
    if ds_jsons:
        return "deepseek-zip"
    return None


def detect_json_file(path):
    """Return 'deepseek-json' | None if path looks like a single DeepSeek conversation."""
    try:
        obj = _open_json(path)
    except Exception:
        return None
    if isinstance(obj, dict) and "messages" in obj and ("id" in obj or "title" in obj):
        return "deepseek-json"
    if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "messages" in obj[0]:
        return "deepseek-json"
    return None


# ---------------------------------------------------------------------------
# DeepSeek parsers
# ---------------------------------------------------------------------------

def parse_deepseek_zip(zf):
    """Parse a DeepSeek browser-extension ZIP export.
    Returns list of conversation dicts with keys: uuid, name, created_at, messages.
    """
    names = set(zf.namelist())

    # Form A: flat conversations.json with DeepSeek schema
    if "conversations.json" in names:
        raw = load_json_member(zf, "conversations.json")
        return _normalise_deepseek_convs(raw)

    # Form B: per-conversation directories
    convs = []
    for n in sorted(names):
        if n.endswith("/conversation.json"):
            try:
                obj = load_json_member(zf, n)
            except Exception:
                continue
            if isinstance(obj, dict):
                convs.append(obj)
    return _normalise_deepseek_convs(convs)


def _open_json(path):
    """Open a JSON file tolerating BOM (utf-8-sig)."""
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def parse_deepseek_json(path):
    """Parse a standalone DeepSeek conversation JSON file.
    Returns list of conversation dicts."""
    obj = _open_json(path)
    if isinstance(obj, dict):
        obj = [obj]
    return _normalise_deepseek_convs(obj)


def parse_deepseek_dir(path):
    """Parse a directory of DeepSeek conversation JSON files.
    Returns list of conversation dicts."""
    convs = []
    for root, _dirs, files in os.walk(path):
        for fn in sorted(files):
            if fn.endswith(".json"):
                fp = os.path.join(root, fn)
                try:
                    obj = _open_json(fp)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    convs.append(obj)
                elif isinstance(obj, list):
                    convs.extend(obj)
    return _normalise_deepseek_convs(convs)


def _normalise_deepseek_convs(raw):
    """Normalise a list of DeepSeek conversation objects into the common shape:
    {uuid, name, created_at, messages: [{role, content, created_at}]}
    """
    out = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        msgs = c.get("messages") or []
        if not msgs:
            continue  # skip empty
        # The DeepSeek format uses "id" (not "uuid"); map it.
        uid = c.get("id") or c.get("uuid") or c.get("conversation_id") or ""
        name = c.get("title") or c.get("name") or "untitled"
        created = c.get("created_at") or c.get("create_time") or c.get("created") or ""
        normalised_msgs = []
        for m in msgs:
            role = (m.get("role") or m.get("sender") or "unknown").lower()
            content = ds_msg_text(m)
            if not content:
                continue
            m_created = m.get("created_at") or m.get("timestamp") or m.get("create_time") or ""
            normalised_msgs.append({
                "role": role,
                "content": content,
                "created_at": m_created,
            })
        if not normalised_msgs:
            continue
        out.append({
            "uuid": str(uid),
            "name": str(name),
            "created_at": str(created),
            "messages": normalised_msgs,
        })
    return out


# ---------------------------------------------------------------------------
# Markdown writers
# ---------------------------------------------------------------------------

def write_conversation_md(c, out_dir):
    """Write one conversation to out_dir as {slug}-{uuid}.md.  Returns filename."""
    uid = short_id(c.get("uuid") or c.get("id") or "")
    name = c.get("name") or c.get("title") or "untitled"
    date = ts_to_date(c.get("created_at"))
    date_prefix = f"{date} " if date else ""
    fname = f"{date_prefix}{slug(name)}-{uid}.md" if uid else f"{date_prefix}{slug(name)}.md"
    # Sanitise filename for Windows
    fname = re.sub(r'[<>:"/\\|?*]', "-", fname)

    msgs = c.get("messages") or c.get("chat_messages") or []
    lines = [f"# {name}", ""]
    if date:
        lines.append(f"_created: {date}_")
    lines.append("")
    for m in msgs:
        who = (m.get("role") or m.get("sender") or "?").capitalize()
        txt = msg_text(m) or ds_msg_text(m)
        if txt:
            lines.append(f"**{who}:** {txt}\n")

    fpath = os.path.join(out_dir, fname)
    with open(fpath, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return fname


# ---------------------------------------------------------------------------
# Vault index update
# ---------------------------------------------------------------------------

def update_vault_history_index(vault_root, new_files):
    """Append new entries to a History folder index note if it exists, else create one."""
    history_dir = os.path.join(vault_root, "Resources", "Claude History")
    index_path = os.path.join(history_dir, "_history-index.md")

    existing = set()
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as fh:
            for line in fh:
                m = re.search(r"\[([^\]]+)\]\(([^)]+)\)", line)
                if m:
                    existing.add(m.group(2))

    new_entries = []
    for fn in sorted(new_files):
        if fn not in existing:
            # Derive title from filename
            title = fn.rsplit(".", 1)[0]
            title = re.sub(r"^\d{4}-\d{2}-\d{2} ", "", title)
            title = title.replace("-", " ").strip()
            new_entries.append(f"- [{title}]({fn})")

    if not new_entries:
        return

    header = (
        "---\nstatus: active\nproject: meta\ntype: index\n---\n\n"
        "# Claude History — imported conversations\n\n"
        "Auto-generated index.  New entries appended by `import-claude-export.py --vault`.\n\n"
    )

    if os.path.exists(index_path):
        with open(index_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(new_entries) + "\n")
    else:
        with open(index_path, "w", encoding="utf-8") as fh:
            fh.write(header + "\n".join(new_entries) + "\n")

    print(f"  Index: {len(new_entries)} entries appended to {index_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Import Anthropic and DeepSeek chat exports into Markdown.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--zip", help="path to an Anthropic or DeepSeek export .zip")
    src.add_argument("--json", help="path to a single DeepSeek conversation .json file")
    src.add_argument("--dir", help="path to a directory of DeepSeek conversation .json files")
    ap.add_argument("--out", default="_memory_import",
                    help="output directory (default _memory_import; use --vault instead)")
    ap.add_argument("--vault", action="store_true",
                    help="write to 7CEs-Vault/Resources/Claude History/ instead of --out")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and count only; write nothing")
    ap.add_argument("--source", choices=("auto", "anthropic", "deepseek"), default="auto",
                    help="force format detection (default auto)")
    args = ap.parse_args()

    # --- resolve output directory ------------------------------------------
    if args.vault:
        # Find the vault: repo parent or common locations
        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "7CEs-Vault"),
            os.path.expanduser("~/7CEs-Vault"),
            "C:\\Users\\adam1\\7CEs-Vault",
        ]
        vault_root = None
        for c in candidates:
            if os.path.isdir(c):
                vault_root = c
                break
        if not vault_root:
            sys.exit("ERROR: could not find 7CEs-Vault.  Pass --out explicitly instead of --vault.")
        out_dir = os.path.join(vault_root, "Resources", "Claude History")
        print(f"Vault found: {vault_root}")
    else:
        out_dir = args.out

    # --- load input --------------------------------------------------------
    format_used = args.source
    zf = None
    convs = []
    memories = None
    project_members = []
    design_members = []

    if args.zip:
        if not os.path.exists(args.zip):
            sys.exit(f"ERROR: zip not found: {args.zip}")
        zf = zipfile.ZipFile(args.zip)
        names = set(zf.namelist())

        if format_used == "auto":
            detected = detect_format(zf)
            if detected is None:
                sys.exit("ERROR: could not auto-detect format in zip.  Pass --source anthropic|deepseek.")
            format_used = detected
            print(f"Auto-detected format: {format_used}")

        if format_used == "anthropic":
            convs = load_json_member(zf, "conversations.json") if "conversations.json" in names else []
            memories = load_json_member(zf, "memories.json") if "memories.json" in names else []
            project_members = [n for n in names if n.startswith("projects/") and n.endswith(".json")]
            design_members = [n for n in names if n.startswith("design_chats/") and n.endswith(".json")]
        else:
            convs = parse_deepseek_zip(zf)

    elif args.json:
        if not os.path.exists(args.json):
            sys.exit(f"ERROR: JSON file not found: {args.json}")
        if format_used == "auto":
            format_used = detect_json_file(args.json) or "deepseek"
            print(f"Auto-detected format: {format_used}")
        if format_used in ("deepseek", "deepseek-json"):
            convs = parse_deepseek_json(args.json)
        else:
            sys.exit("ERROR: --json only supports DeepSeek format.  Use --zip for Anthropic exports.")

    elif args.dir:
        if not os.path.isdir(args.dir):
            sys.exit(f"ERROR: directory not found: {args.dir}")
        format_used = "deepseek"
        convs = parse_deepseek_dir(args.dir)

    # --- stats -------------------------------------------------------------
    total_msgs = sum(len(c.get("messages") or []) for c in convs)
    extras = []
    if memories:
        extras.append("memory present")
    if project_members:
        extras.append(f"{len(project_members)} projects")
    if design_members:
        extras.append(f"{len(design_members)} design chats")
    extra_str = ", " + ", ".join(extras) if extras else ""
    print(f"Parsed: {len(convs)} conversations ({total_msgs} messages){extra_str}.")

    if args.dry_run:
        print("--dry-run: nothing written.")
        if zf:
            zf.close()
        return

    # --- write -------------------------------------------------------------
    cdir = os.path.join(out_dir, "conversations") if format_used == "anthropic" and args.vault is False else out_dir
    os.makedirs(cdir, exist_ok=True)

    written = 0
    new_files = []
    for c in convs:
        fname = write_conversation_md(c, cdir)
        new_files.append(fname)
        written += 1

    # Anthropic-specific extras (only when writing to --out, not --vault)
    if format_used == "anthropic" and not args.vault:
        out = args.out
        # memory -> single markdown
        if memories:
            m0 = memories[0] if isinstance(memories, list) else memories
            lines = ["# Claude memory export", ""]
            cm = m0.get("conversations_memory")
            pm = m0.get("project_memories")
            if cm:
                lines += ["## Conversations memory", "",
                          json.dumps(cm, indent=2, ensure_ascii=False) if not isinstance(cm, str) else cm, ""]
            if pm:
                lines += ["## Project memories", "",
                          json.dumps(pm, indent=2, ensure_ascii=False) if not isinstance(pm, str) else pm, ""]
            with open(os.path.join(out, "memory.md"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))

        # projects
        pdir = os.path.join(out, "projects")
        os.makedirs(pdir, exist_ok=True)
        for n in project_members:
            try:
                obj = load_json_member(zf, n)
            except Exception:
                continue
            base = slug(obj.get("name") if isinstance(obj, dict) else None) + "-" + os.path.basename(n).split(".")[0][:8]
            with open(os.path.join(pdir, base + ".md"), "w", encoding="utf-8") as fh:
                fh.write(f"# Project {obj.get('name','') if isinstance(obj, dict) else ''}\n\n")
                fh.write("```json\n" + json.dumps(obj, indent=2, ensure_ascii=False) + "\n```\n")

    # --- vault index -------------------------------------------------------
    if args.vault and new_files:
        update_vault_history_index(vault_root, new_files)

    # --- done --------------------------------------------------------------
    plural = "s" if written != 1 else ""
    print(f"Wrote {written} conversation file{plural} to {cdir}/")
    if format_used == "anthropic" and not args.vault:
        print(f"(+ memory + {len(project_members)} projects to ./{args.out}/)")
        print("This folder is git-ignored. Next: ingest it into mem0 / claude-mem / LibreChat RAG (see ADVANCED-SETUP.md).")
    elif args.vault:
        print("Conversations are now in your vault's Claude History folder — ready for RAG / manual browsing.")

    if zf:
        zf.close()


if __name__ == "__main__":
    main()
