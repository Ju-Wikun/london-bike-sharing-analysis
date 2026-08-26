"""Package only the six navigation views and their local chart runtime."""
from html.parser import HTMLParser
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


class ViewParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.views = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "button" and "data-page" in attributes:
            self.views.append(attributes["data-page"])


def package_pages(source: Path, destination: Path) -> list[str]:
    parser = ViewParser()
    parser.feed((source / "index.html").read_text(encoding="utf-8"))
    if len(set(parser.views)) != 6:
        raise ValueError("Expected exactly six distinct public dashboard views")
    files = ["index.html", *parser.views, "vendor/echarts.min.js", "vendor/LICENSE.txt"]
    for name in files:
        path = (source / name).resolve()
        if not path.is_relative_to(source.resolve()) or not path.is_file():
            raise ValueError(f"Invalid public asset: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    (destination / ".nojekyll").touch()
    return files


if __name__ == "__main__":
    files = package_pages(ROOT / "dashboards", ROOT / "output" / "pages")
    print(f"Packaged {len(files)} files for GitHub Pages")
