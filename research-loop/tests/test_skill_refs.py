"""Test 13: every role skill names only things that exist, and writes only what its role json allows.

Source: 06 L252-L262 (the three checks, ruled 2026-08-18), 09 L27-L29 (no copies of common/ text), proxy
decision D-08 (the two discipline sentences every role skill carries are exempt from checks 2 and 3;
sources 06 L29 and 09 L53), proxy decision D-17 (backticks mark the tokens this test reads, and common/GLOSSARY.md's
first column is a definition site next to the four kinds 06 L260 lists), SPEC-TEMPLATE.md "Token convention".

Check 1  every `rl` write command a skill names is in that role json's ledger_writes; query commands are free.
Check 2  every ledger name and every directory a skill names is in that role json's reads (or writes for directories).
Check 3  every command, ledger, status, directory, flag, path or term a skill names exists at its definition site
         (tables/commands.json with its signatures, tables/ledgers.json, tables/transitions.json,
         schemas/*.schema.json, the role jsons, common/GLOSSARY.md, the plugin's own tree); and no sentence of
         common/ is copied into a skill, except the two sentences. Host files are never checked on disk.

The test fails, never skips, when a table, schema, json or skill is missing: an absent definition site means
the check cannot run, and a check that cannot run is red.
"""
import json
import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parent
ROLES = ["idea", "deploy", "run", "analysis", "reviewer"]

# D-08: the two sentences every role skill copies verbatim from common/GLOBAL-RULES.md.
EXEMPT_SENTENCES = [
    "Writes the hook cannot see (a script writing files internally, `python -c`, heredocs, any Bash command "
    "whose target path the hook cannot parse) never go into the four role directories or `loop/`; to write "
    "there use Write/Edit or a Bash form the hook can see, and ledgers only ever go through `rl`.",
    "One session loads one role. To switch roles, open another session. The machine does not enforce this; "
    "what happens on a second load in the same session is undefined and has no fallback.",
]

GLOBAL_FLAGS = {"--json", "--as-gyb", "--quote", "--force", "--reason"}
BACKTICK = re.compile(r"`([^`\n]+)`")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
MIN_COPY_LEN = 50


def _load_json(rel):
    path = PLUGIN / rel
    assert path.is_file(), f"definition site missing: {path}"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _read_text(path):
    assert path.is_file(), f"file missing: {path}"
    return path.read_text(encoding="utf-8")


def load_commands():
    """name -> {ledger, kind}; pending_commands do not exist (grants are PENDING(issue 43c))."""
    table = _load_json("tables/commands.json")
    commands = {}
    flags = set()
    for c in table["commands"]:
        own = set(re.findall(r"--[a-z][a-z0-9-]*", c.get("signature", "")))
        commands[c["name"]] = {"ledger": c["ledger"], "kind": c["kind"], "flags": own}
        flags.update(own)
    assert commands, "tables/commands.json lists no commands"
    return commands, flags


def load_ledgers():
    """Ledger names as reads/ledger_writes spell them: plain names plus decisions.<book>."""
    table = _load_json("tables/ledgers.json")
    names = set()
    statuses = set()
    for ledger in table["ledgers"]:
        names.add(ledger["name"])
        for book in ledger.get("books", []):
            names.add(f"{ledger['name']}.{book}")
        statuses.update(ledger.get("status_values", []))
        schema_rel = ledger.get("schema")
        if schema_rel:
            schema = _load_json(schema_rel)
            statuses.update(_status_enum(schema))
    assert names, "tables/ledgers.json lists no ledgers"
    return names, statuses


def _status_enum(schema):
    found = set()

    def walk(node):
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict) and isinstance(props.get("status"), dict):
                found.update(props["status"].get("enum", []))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return found


def load_transitions():
    table = _load_json("tables/transitions.json")
    tokens = set(table["states"])
    tokens.update(table.get("work_types", []))
    tokens.update(table.get("dispatch_values", []))
    return tokens


def load_role(role):
    data = _load_json(f"tables/roles/{role}.json")
    assert data["role"] == role, f"tables/roles/{role}.json declares role {data['role']!r}"
    return data


def load_glossary_terms():
    text = _read_text(PLUGIN / "common" / "GLOSSARY.md")
    terms = set()
    for line in text.splitlines():
        if line.startswith("| `"):
            first_cell = line.split("|")[1]
            terms.update(BACKTICK.findall(first_cell))
    assert terms, "common/GLOSSARY.md has no backticked terms in its first column"
    return terms


def load_common_sentences():
    """Sentences of common/ long enough that a verbatim copy in a skill is a copy, not a coincidence."""
    sentences = set()
    for path in sorted((PLUGIN / "common").glob("*.md")):
        text = _read_text(path)
        text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("|"):
                continue
            for sentence in SENTENCE_SPLIT.split(line):
                sentence = sentence.strip()
                if len(sentence) >= MIN_COPY_LEN and sentence not in EXEMPT_SENTENCES:
                    sentences.add(sentence)
    assert sentences, "common/ has no sentences to compare against"
    return sentences


def skill_body(role):
    text = _read_text(PLUGIN / "skills" / role / "SKILL.md")
    for sentence in EXEMPT_SENTENCES:
        text = text.replace(sentence, " ")
    return text


def resolve_command(token, commands):
    """`rl handoff open --type ...` -> 'handoff open'; `rl doctor --ack ITEM ID` -> 'doctor --ack'; None if unknown."""
    words = token.split()[1:]
    for width in (2, 1):
        name = " ".join(words[:width])
        if name in commands:
            return name
    return None


def allowed_write(name, ledger, role_json):
    writes = role_json["ledger_writes"]
    keys = [ledger] if ledger != "decisions" else [k for k in writes if k.startswith("decisions.")]
    for key in keys:
        allowed = writes.get(key)
        if allowed == "*" or (isinstance(allowed, list) and name in allowed):
            return True
    return False


def classify(token):
    if token == "rl":
        return "entry"
    if token.startswith("rl "):
        return "command"
    if token.endswith("/"):
        return "directory"
    if token.startswith("--"):
        return "flag"
    if "/" in token or "." in token:
        return "path"
    if re.fullmatch(r"[a-z][a-z0-9_]*", token):
        return "word"
    return "other"


def check_role(role, commands, flags, ledgers, statuses, transition_tokens, glossary, common_sentences):
    role_json = load_role(role)
    reads = set(role_json["reads"])
    writes_dirs = {w for w in role_json.get("writes", []) if w.endswith("/")}
    directories = {"loop/"}
    read_files = set()
    for other in ROLES:
        other_json = load_role(other)
        for entry in other_json["reads"] + other_json.get("writes", []):
            if entry.endswith("/"):
                directories.add(entry)
            elif "/" in entry or "." in entry:
                read_files.add(entry)
    body = skill_body(role)
    errors = []
    for token in BACKTICK.findall(body):
        kind = classify(token)
        if kind == "command":
            name = resolve_command(token, commands)
            if name is None:
                errors.append(f"unknown rl command: `{token}`")
                continue
            if commands[name]["kind"] == "write" and not allowed_write(name, commands[name]["ledger"], role_json):
                errors.append(f"write command not in ledger_writes: `{name}`")
            # A flag written on a command must be in that command's own signature; the five global
            # flags (--json, --as-gyb, --quote, --force, --reason; tables/README.md convention 15) are free.
            for word in token.split():
                if word.startswith("--") and word not in commands[name]["flags"] and word not in GLOBAL_FLAGS:
                    errors.append(f"flag not in the signature of `{name}`: `{word}`")
        elif kind == "directory":
            if (PLUGIN / token).is_dir():
                continue
            if token not in directories:
                errors.append(f"unknown directory: `{token}`")
            elif token not in reads and token not in writes_dirs:
                errors.append(f"directory not in reads or writes: `{token}`")
        elif kind == "flag":
            if token in glossary:
                continue
            for word in token.split():
                if word.startswith("--") and word not in flags and word not in glossary:
                    errors.append(f"unknown flag: `{word}` in `{token}`")
        elif kind == "path":
            # Definition sites for a path: the glossary, a role json's reads/writes, or the plugin's own tree.
            # Files of the host repository are never checked on disk: their existence depends on host state.
            plugin_relative = token[len("research-loop/"):] if token.startswith("research-loop/") else token
            if token in glossary or (PLUGIN / plugin_relative).exists():
                continue
            if token in read_files:
                if token not in reads:
                    errors.append(f"file not in reads: `{token}`")
            else:
                errors.append(f"path defined nowhere: `{token}`")
        elif kind == "word":
            if token in ledgers:
                if token not in reads:
                    errors.append(f"ledger not in reads: `{token}`")
            elif token not in statuses and token not in transition_tokens and token not in glossary:
                errors.append(f"name defined nowhere: `{token}`")
    for sentence in common_sentences:
        if sentence in body:
            errors.append(f"copy of common/ text: {sentence[:60]!r}...")
    return errors


def _context():
    commands, flags = load_commands()
    ledgers, statuses = load_ledgers()
    return commands, flags, ledgers, statuses, load_transitions(), load_glossary_terms(), load_common_sentences()


def test_exempt_sentences_match_global_rules():
    rules = _read_text(PLUGIN / "common" / "GLOBAL-RULES.md")
    for sentence in EXEMPT_SENTENCES:
        assert sentence in rules, f"exempt sentence drifted from common/GLOBAL-RULES.md: {sentence[:60]!r}..."


def test_every_role_has_a_skill():
    for role in ROLES:
        assert (PLUGIN / "skills" / role / "SKILL.md").is_file(), f"skills/{role}/SKILL.md missing"


def test_skill_refs():
    ctx = _context()
    failures = {}
    for role in ROLES:
        errors = check_role(role, *ctx)
        if errors:
            failures[role] = errors
    assert not failures, "\n" + "\n".join(f"{role}: {e}" for role, errs in failures.items() for e in errs)


if __name__ == "__main__":
    test_exempt_sentences_match_global_rules()
    test_every_role_has_a_skill()
    test_skill_refs()
    print("test_skill_refs: green")
