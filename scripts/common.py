"""Local, standard-library-only storage and AnkiConnect primitives."""
import contextlib
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
try:
    import msvcrt
except ImportError:  # macOS and Linux
    msvcrt = None

WINDOWS = os.name == "nt"

NAME = "Academic Vocabulary"
FIELDS = ["Key", "Term", "Definition", "Context", "Prompt", "Answer", "Hint",
          "Collocation", "Contrast", "Receptive", "Productive", "IPA"]
ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent.parent / "assets"
ENDPOINT = "http://127.0.0.1:8765"


class Error(Exception):
    pass


class Unavailable(Error):
    pass


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalized(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def make_key(term, sense):
    return "av1-" + hashlib.sha256((normalized(term) + "\n" + sense).encode()).hexdigest()


def contains(text, word):
    return bool(re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text, re.I))


def cloze_fields(context, answer, requested_spans):
    """Resolve the model's exact-text selections without deciding vocabulary senses."""
    def matches(text):
        return list(re.finditer(r"(?<!\w)" + re.escape(text) + r"(?!\w)", context))

    selected = []
    if requested_spans is None:
        if not answer.strip():
            raise Error("Missing Answer or answer_spans")
        selected = [(m.start(), m.end(), answer, i) for i, m in enumerate(matches(answer), 1)]
        if not selected:
            raise Error("Answer must occur with exact capitalization in Context")
    else:
        if not isinstance(requested_spans, list) or not requested_spans:
            raise Error("answer_spans must be a nonempty list")
        for span in requested_spans:
            if not isinstance(span, dict) or set(span) != {"text", "occurrence"}:
                raise Error("Each answer span needs only text and occurrence")
            text, occurrence = span["text"], span["occurrence"]
            if not isinstance(text, str) or not text.strip() or type(occurrence) is not int or occurrence < 1:
                raise Error("Answer span needs exact text and a positive integer occurrence")
            found = matches(text)
            if occurrence > len(found):
                raise Error("Answer span does not match Context with exact capitalization")
            match = found[occurrence - 1]
            selected.append((match.start(), match.end(), text, occurrence))
        selected.sort()
        if any(a[1] > b[0] for a, b in zip(selected, selected[1:])):
            raise Error("Answer spans overlap or repeat the same position")

    shared_answer = len({span[2] for span in selected}) == 1
    derived_answer = selected[0][2] if shared_answer else "\n".join(
        f"{i}. {span[2]}" for i, span in enumerate(selected, 1))
    if answer and answer != derived_answer:
        raise Error("Answer must match the selected spans in context order")
    parts, end = [], 0
    for i, (start, stop, text, occurrence) in enumerate(selected, 1):
        parts.extend((context[end:start], "_____" if shared_answer else f"_____ ({i})"))
        end = stop
    parts.append(context[end:])
    return "".join(parts), derived_answer, selected


def validate(raw):
    if not isinstance(raw, dict):
        raise Error("Each record must be an object")
    allowed = {"sense", "fields", "tags", "context_origin", "original_context",
               "ipa_source", "sources", "target_forms", "answer_start", "answer_spans"}
    if set(raw) - allowed:
        raise Error("Unknown record properties: " + ", ".join(sorted(set(raw) - allowed)))
    sense = raw.get("sense", "")
    if not isinstance(sense, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", sense) or len(sense) > 80:
        raise Error("sense must be a stable lowercase meaning slug (max 80 characters)")
    supplied = raw.get("fields", {})
    if not isinstance(supplied, dict) or set(supplied) - set(FIELDS):
        raise Error("Unknown or invalid Anki fields")
    fields = {name: supplied.get(name, "") for name in FIELDS}
    for name, value in fields.items():
        if not isinstance(value, str) or len(value) > 8000:
            raise Error(f"{name} must be a string of at most 8000 characters")
        if any(ord(c) < 32 and c not in "\n\t" for c in value) or any(x in value.lower() for x in ("{{", "}}", "[sound:", "[anki:")):
            raise Error(f"{name}: control characters or Anki markup are not accepted")
    for name in ("Term", "Definition", "Context"):
        if not fields[name].strip():
            raise Error(f"Missing {name}")
    if len(fields["Term"]) > 160 or len(fields["Definition"]) > 500 or len(fields["Context"]) > 2000:
        raise Error("Term, definition or context is too long for a focused card")
    for flag in ("Receptive", "Productive"):
        if fields[flag] not in ("", "1"):
            raise Error(f"{flag} must be '1' or empty")
    if not (fields["Receptive"] or fields["Productive"]):
        raise Error("Enable at least one card type")
    context, answer = fields["Context"], fields["Answer"]
    if len(context.split()) < 4 or "_____" in context:
        raise Error("Context must be a complete example, without an existing blank")
    if "answer_spans" in raw and raw["answer_spans"] is None:
        raise Error("answer_spans must be a nonempty list")
    prompt, answer, selected = cloze_fields(context, answer, raw.get("answer_spans"))
    start = selected[0][0]
    if "answer_start" in raw and raw["answer_start"] != start:
        raise Error("answer_start does not match the exact target span")
    if supplied.get("Prompt") and supplied["Prompt"] != prompt:
        raise Error("Prompt must match the selected answer spans")
    fields["Prompt"] = prompt
    fields["Answer"] = answer
    if any(len(fields[name]) > 8000 for name in ("Prompt", "Answer")):
        raise Error("Derived Prompt or Answer exceeds the 8000-character field limit")
    forms = raw.get("target_forms", [])
    if not isinstance(forms, list) or any(not isinstance(x, str) or not x.strip() for x in forms):
        raise Error("target_forms must be a list of nonempty strings")
    forms = sorted(set(forms + [fields["Term"]] + [span[2] for span in selected]))
    if fields["Productive"]:
        for name in ("Definition", "Prompt", "Hint"):
            if any(contains(fields[name], form) for form in forms):
                raise Error(f"{name} leaks a target form; revise the cue or use Receptive only")
    origin = raw.get("context_origin")
    if origin not in ("user", "generated"):
        raise Error("context_origin must be user or generated")
    original = raw.get("original_context", "")
    if not isinstance(original, str) or (origin == "user" and original != context):
        raise Error("User Context must exactly equal original_context")
    if origin == "generated" and original:
        raise Error("Generated contexts must not claim an original user sentence")
    ipa_source = raw.get("ipa_source", "")
    sources = raw.get("sources", [])
    if not isinstance(ipa_source, str) or not isinstance(sources, list) or any(not isinstance(x, str) for x in sources):
        raise Error("Sources must be URL strings")
    if fields["IPA"] and not re.match(r"https://[^\s]+$", ipa_source):
        raise Error("Nonempty IPA requires a verified American IPA source URL")
    if any(not re.fullmatch(r"https://[^\s]+", x) for x in sources):
        raise Error("sources must contain HTTPS URLs")
    tags = raw.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(t, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_:-]*", t) for t in tags):
        raise Error("Tags must be lowercase Anki tag tokens")
    if not set(tags) - {"context_user", "context_generated"}:
        raise Error("Provide at least one domain tag")
    if any(t.startswith("context_") and t != "context_" + origin for t in tags):
        raise Error("Context tag conflicts with provenance")
    tags = sorted(set(tags) | {"context_" + origin})
    key = make_key(fields["Term"], sense)
    if supplied.get("Key") and supplied["Key"] != key:
        raise Error("Supplied Key does not match Term and sense")
    fields["Key"] = key
    record = {"schema_version": 1, "sense": sense, "fields": fields, "tags": tags,
              "context_origin": origin, "original_context": original,
              "ipa_source": ipa_source, "sources": sources, "target_forms": forms}
    if "answer_spans" in raw:
        record["answer_spans"] = [{"text": text, "occurrence": occurrence}
                                  for _, _, text, occurrence in selected]
    record["id"] = hashlib.sha256(canonical(record).encode()).hexdigest()
    return record


def check_record(record):
    raw = {k: record[k] for k in ("sense", "fields", "tags", "context_origin",
                                "original_context", "ipa_source", "sources", "target_forms")}
    if "answer_spans" in record:
        raw["answer_spans"] = record["answer_spans"]
    if validate(raw) != record:
        raise Error("Queue record validation or checksum failed; original file preserved")


def durable_replace(path, contents):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
            if hasattr(fcntl, "F_FULLFSYNC"):
                fcntl.fcntl(stream.fileno(), fcntl.F_FULLFSYNC)
        os.replace(temporary, path)
        # Windows cannot open a directory for fsync; os.replace is already atomic there.
        if not WINDOWS:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_jsonl(path):
    if not path.exists():
        return []
    result = []
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise Error(f"{path.name}:{line_no} invalid JSON; file preserved") from exc
    return result


def write_jsonl(path, rows):
    durable_replace(path, "".join(canonical(row) + "\n" for row in rows))


def lock_file(fd):
    if WINDOWS:
        # msvcrt locks a byte range from the current position; always lock byte 0.
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError(*exc.args) from exc
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def unlock_file(fd):
    if WINDOWS:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.contextmanager
def locked(root):
    data = Path(root) / "data"
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(data / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "a") as stream:
        try:
            lock_file(stream.fileno())
        except BlockingIOError as exc:
            raise Error("Another intake/sync is running; retry after it finishes") from exc
        try:
            yield data
        finally:
            unlock_file(stream.fileno())


def use_utf8_stdio():
    """Keep JSON input and output in UTF-8 even under a legacy Windows code page."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def config(root):
    path = Path(root) / "config.json"
    cfg = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if cfg.get("endpoint", ENDPOINT) != ENDPOINT:
        raise Error("Only local http://127.0.0.1:8765 is permitted")
    if not isinstance(cfg.get("timeout_seconds", 8), (int, float)) or not 1 <= cfg.get("timeout_seconds", 8) <= 30:
        raise Error("timeout_seconds must be between 1 and 30")
    return cfg


class Anki:
    def __init__(self, cfg):
        self.cfg = cfg
        # Ignore ambient HTTP proxies and never follow a redirect off localhost.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(self, action, **params):
        request = {"action": action, "version": 6, "params": params}
        key_env = self.cfg.get("api_key_env", "ANKICONNECT_API_KEY")
        if os.environ.get(key_env):
            request["key"] = os.environ[key_env]
        req = urllib.request.Request(ENDPOINT, data=json.dumps(request).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=self.cfg.get("timeout_seconds", 8)) as response:
                payload = json.loads(response.read())
        except (OSError, urllib.error.URLError, ValueError) as exc:
            raise Unavailable("AnkiConnect unavailable or response uncertain; keep pending and retry next run") from exc
        if not isinstance(payload, dict) or "error" not in payload or "result" not in payload:
            raise Unavailable("Malformed AnkiConnect response; keep pending")
        if payload["error"] is not None:
            # Do not echo arbitrary remote responses or authentication details.
            raise Error(f"AnkiConnect rejected {action}; check Anki, profile and API-key configuration")
        return payload["result"]


def encode_fields(fields):
    return {k: html.escape(v, quote=True).replace("\n", "<br>") for k, v in fields.items()}


def plain(value):
    return html.unescape(re.sub(r"<[^>]*>", "", re.sub(r"<br\s*/?>", "\n", value, flags=re.I)))


def note_fields(note):
    return {k: note["fields"][k]["value"] for k in FIELDS}


def templates():
    return [{"Name": name,
             "Front": (ASSETS / (prefix + "-front.html")).read_text(encoding="utf-8"),
             "Back": (ASSETS / (prefix + "-back.html")).read_text(encoding="utf-8")}
            for name, prefix in (("Receptive", "receptive"), ("Productive", "productive"))]


def check_profile(api, cfg):
    if not cfg.get("expected_profile"):
        raise Error("Run sync.py --init once to bind the intended Anki profile")
    if api.call("getActiveProfile") != cfg["expected_profile"]:
        raise Error("Active Anki profile differs from config.json; no writes performed")


def ensure_model(api):
    wanted = templates()
    if NAME not in api.call("modelNames"):
        api.call("createModel", modelName=NAME, inOrderFields=FIELDS, cardTemplates=wanted,
                 css=(ASSETS / "cards.css").read_text(encoding="utf-8"), isCloze=False)
    if api.call("modelFieldNames", modelName=NAME) != FIELDS:
        raise Error("Existing Academic Vocabulary fields differ; no model changes performed")
    existing = api.call("modelTemplates", modelName=NAME)
    if existing != {t["Name"]: {"Front": t["Front"], "Back": t["Back"]} for t in wanted}:
        raise Error("Existing templates differ; review them manually; no overwrite performed")
    if NAME not in api.call("deckNames"):
        api.call("createDeck", deck=NAME)


def find_key(api, key):
    ids = api.call("findNotes", query=f'"note:{NAME}" "Key:{key}"')
    notes = api.call("notesInfo", notes=ids) if ids else []
    exact = [n for n in notes if n.get("modelName") == NAME and n["fields"]["Key"]["value"] == key]
    if len(exact) != len(ids) or len(exact) > 1:
        raise Error("Ambiguous or duplicate Key in Anki; manual review required")
    return exact[0] if exact else None
