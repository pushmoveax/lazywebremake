"""lazyweb — небольшой сервер для чтения заметок в markdown."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote_to_bytes

import markdown
from flask import Flask, abort, redirect, render_template, request, url_for
from markdown.extensions.toc import TocExtension, slugify_unicode
from markdown.preprocessors import Preprocessor
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.util import ClassNotFound

BASE_DIR = Path(__file__).resolve().parent
CONTENT_DIR = (BASE_DIR / "content").resolve()

# Файлы, которые показываем как подсвеченный исходник, а не как заметку.
SOURCE_SUFFIXES = {
    ".c", ".cpp", ".css", ".go", ".h", ".hpp", ".html", ".java", ".js",
    ".json", ".jsx", ".kt", ".lua", ".php", ".py", ".rb", ".rs", ".sh",
    ".sql", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}

app = Flask(__name__)


class DecodePathInfo:
    """Раскодировать PATH_INFO, если этого не сделал сервер.

    По WSGI-спецификации PATH_INFO приходит уже раскодированным, и Werkzeug
    на это рассчитывает. Python-рантайм Vercel отдаёт путь как есть, вместе
    с %-escape-последовательностями, поэтому пути с кириллицей и пробелами
    не находились. Локальный сервер декодирует правильно, так что чинить
    нужно только на Vercel — иначе имя файла с настоящим «%» раскодируется
    второй раз и сломается.
    """

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if "%" in path:
            # PATH_INFO по спецификации — байты, разложенные по latin-1;
            # Werkzeug сам соберёт их обратно и раскодирует как utf-8.
            environ["PATH_INFO"] = unquote_to_bytes(path).decode("latin-1")
        return self.wsgi_app(environ, start_response)


if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    app.wsgi_app = DecodePathInfo(app.wsgi_app)


# --------------------------------------------------------------------------
# markdown
# --------------------------------------------------------------------------

class UnindentHeadings(Preprocessor):
    """`  # Заголовок` с отступом до трёх пробелов — всё ещё заголовок.

    Python-Markdown такие строки считает обычным текстом, хотя CommonMark
    их разрешает; в конспектах отступ перед `#` встречается регулярно.
    """

    RE = re.compile(r"^ {1,3}(#{1,6}[ \t])")

    def run(self, lines: list[str]) -> list[str]:
        return [self.RE.sub(r"\1", line) for line in lines]


def build_markdown() -> markdown.Markdown:
    md = markdown.Markdown(
        extensions=[
            "extra",        # таблицы, ```-блоки, сноски, attr_list, def_list
            "sane_lists",
            "nl2br",        # перенос строки = перенос строки, как в Obsidian
            "admonition",
            "codehilite",
            TocExtension(permalink=False, toc_depth="1-4",
                         slugify=slugify_unicode),
        ],
        extension_configs={
            "codehilite": {"guess_lang": False, "linenums": False},
        },
    )
    # Заметки пишут с отступами для наглядности (стрелки, схемы) — не хочется,
    # чтобы каждый такой абзац превращался в блок кода. ```-блоки не трогаем.
    md.parser.blockprocessors.deregister("code")

    # Приоритет ниже 25, чтобы отработать уже после fenced_code.
    md.preprocessors.register(UnindentHeadings(md), "unindent_headings", 20)
    return md


HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
INLINE_RE = re.compile(r"[*_`~]+")


def extract_title(text: str, fallback: str) -> str:
    """Заголовок страницы — первый заголовок заметки, иначе имя файла."""
    match = HEADING_RE.search(text)
    if not match:
        return fallback
    title = INLINE_RE.sub("", match.group(1)).strip()
    return title or fallback


def flatten_toc(tokens: list, depth: int = 0) -> list:
    out = []
    for token in tokens:
        out.append({"id": token["id"], "name": token["name"], "depth": depth})
        out.extend(flatten_toc(token.get("children", []), depth + 1))
    return out


# --------------------------------------------------------------------------
# файловая часть
# --------------------------------------------------------------------------

def resolve_safe(filepath: str) -> Path:
    """Путь внутри content/ — или 404."""
    if "\x00" in filepath:
        abort(404)

    target = (CONTENT_DIR / filepath).resolve()

    if target != CONTENT_DIR and CONTENT_DIR not in target.parents:
        abort(404)

    if any(part.startswith(".") for part in target.relative_to(CONTENT_DIR).parts):
        abort(404)

    return target


def sort_key(name: str):
    """Естественная сортировка: «2 sep» раньше «10 sep»."""
    parts = re.split(r"(\d+)", name.strip().casefold())
    return [int(p) if p.isdigit() else p for p in parts]


def is_readable(path: Path) -> bool:
    return path.suffix.lower() == ".md" or path.suffix.lower() in SOURCE_SUFFIXES


def describe_folder(path: Path) -> str:
    """Короткая подпись для папки: сколько внутри заметок и вложенных папок."""
    notes = folders = 0
    try:
        for item in path.rglob("*"):
            if any(part.startswith(".") for part in item.relative_to(path).parts):
                continue
            if item.is_dir():
                folders += 1
            elif is_readable(item):
                notes += 1
    except OSError:
        return "папка"

    bits = []
    if notes:
        bits.append(f"{notes} {plural(notes, 'заметка', 'заметки', 'заметок')}")
    if folders:
        bits.append(f"{folders} {plural(folders, 'папка', 'папки', 'папок')}")
    return ", ".join(bits) or "пусто"


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def list_dir(path: Path, rel: str) -> list[dict]:
    folders, files = [], []

    for item in sorted(path.iterdir(), key=lambda p: sort_key(p.name)):
        if item.name.startswith("."):
            continue

        child = f"{rel}/{item.name}" if rel else item.name

        if item.is_dir():
            folders.append({
                "name": item.name.strip(),
                "path": child,
                "kind": "folder",
                "meta": describe_folder(item),
            })
        elif item.is_file() and is_readable(item):
            is_note = item.suffix.lower() == ".md"
            files.append({
                "name": (item.stem if is_note else item.name).strip(),
                "path": child,
                "kind": "note" if is_note else "source",
                "meta": "заметка" if is_note else item.suffix.lstrip(".").lower(),
            })

    return folders + files


def build_crumbs(filepath: str) -> list[dict]:
    crumbs, acc = [], ""
    for part in filepath.split("/"):
        if not part:
            continue
        acc = f"{acc}/{part}" if acc else part
        crumbs.append({"name": part.strip(), "path": acc})
    return crumbs


# --------------------------------------------------------------------------
# маршруты
# --------------------------------------------------------------------------

@app.route("/")
def index():
    root_items = []
    if CONTENT_DIR.is_dir():
        root_items = list_dir(CONTENT_DIR, "")
    return render_template("index.html", items=root_items[:6])


@app.route("/browse")
@app.route("/browse/<path:filepath>")
def browse_lower(filepath: str = ""):
    return redirect(url_for("Browse", filepath=filepath) if filepath
                    else url_for("Browse"), code=301)


@app.route("/Browse")
@app.route("/Browse/")
@app.route("/Browse/<path:filepath>")
def Browse(filepath: str = ""):
    filepath = filepath.strip("/")
    current = resolve_safe(filepath)

    if current.is_dir():
        return render_template(
            "browse.html",
            items=list_dir(current, filepath),
            crumbs=build_crumbs(filepath),
            title=filepath.rsplit("/", 1)[-1].strip() if filepath else "Файлы",
        )

    if not current.is_file() or not is_readable(current):
        abort(404)

    crumbs = build_crumbs(filepath)
    parent = filepath.rsplit("/", 1)[0] if "/" in filepath else ""

    if current.suffix.lower() == ".md":
        text = current.read_text(encoding="utf-8", errors="replace")
        md = build_markdown()
        html = md.convert(text)
        toc = flatten_toc(getattr(md, "toc_tokens", []))
        return render_template(
            "note.html",
            content=html,
            title=extract_title(text, current.stem.strip()),
            crumbs=crumbs,
            parent=parent,
            toc=toc if len(toc) >= 3 else [],
        )

    source = current.read_text(encoding="utf-8", errors="replace")
    try:
        lexer = get_lexer_for_filename(current.name, stripall=False)
    except ClassNotFound:
        lexer = TextLexer()
    html = highlight(source, lexer, HtmlFormatter(cssclass="codehilite"))

    return render_template(
        "note.html",
        content=html,
        title=current.name.strip(),
        crumbs=crumbs,
        parent=parent,
        toc=[],
        is_source=True,
    )


@app.route("/about")
def about():
    return render_template("about.html")


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


@app.context_processor
def inject_nav():
    return {"current_path": request.path}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
