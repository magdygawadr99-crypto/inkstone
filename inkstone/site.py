"""Quick and dirty: every content/*.md becomes public/<name>/index.html."""
import os
import string
import sys

from .markdown import Markdown

PAGE = string.Template(
    """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>$title</title></head>
<body>
<h1>$title</h1>
$content
<p><a href="/">index</a></p>
</body>
</html>
"""
)


def build(src, out):
    md = Markdown()
    links = []
    content = os.path.join(src, "content")
    for name in sorted(os.listdir(content)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(content, name), encoding="utf-8") as f:
            text = f.read()
        # first line is "# Title" by convention, for now
        title = text.split("\n", 1)[0].lstrip("# ").strip() or name
        url = os.path.join(name[:-3], "index.html")
        target = os.path.join(out, url)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(PAGE.substitute(title=title, content=md.convert(text)))
        links.append(f'<li><a href="/{url}">{title}</a></li>')
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        body = "<ul>\n" + "\n".join(links) + "\n</ul>"
        f.write(PAGE.substitute(title="Index", content=body))
    return len(links)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "."
    print(build(src, os.path.join(src, "public")), "pages")
