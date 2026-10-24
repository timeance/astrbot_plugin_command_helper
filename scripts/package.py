"""Build an installable ZIP containing only runtime files and user documentation."""

import hashlib
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "LICENSE",
    "README.md",
    "_conf_schema.json",
    "main.py",
    "matching.py",
    "metadata.yaml",
    "phcraft.py",
    "requirements.txt",
)


def build() -> Path:
    metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
    name = re.search(r"^name:\s*(\w+)\s*$", metadata, re.MULTILINE).group(1)
    version = re.search(r"^version:\s*([0-9.]+)\s*$", metadata, re.MULTILINE).group(1)
    output = ROOT / "dist" / f"{name}-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for filename in FILES:
            archive.write(ROOT / filename, f"{name}/{filename}")
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {f"{name}/{filename}" for filename in FILES}
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n", encoding="ascii")
    return output


if __name__ == "__main__":
    print(build())
