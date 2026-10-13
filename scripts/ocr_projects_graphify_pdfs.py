#!/usr/bin/env python3
"""OCR a staged, image-only PDF into private, resumable page text files."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / ".local-graphify" / "full" / "source"
OUTPUT = ROOT / ".local-graphify" / "full" / "ocr"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", help="PDF path relative to the staged projects corpus")
    parser.add_argument("--pages", type=int, default=0, help="Process at most this many pages in this run")
    args = parser.parse_args()
    file = (STAGE / args.pdf).resolve()
    if not file.is_relative_to(STAGE.resolve()) or not file.is_file() or file.suffix.lower() != ".pdf":
        raise SystemExit("PDF must be a staged source file")
    key = hashlib.sha256(args.pdf.encode()).hexdigest()[:12]
    destination = OUTPUT / key
    destination.mkdir(parents=True, exist_ok=True)
    document = fitz.open(file)
    processed = 0
    for index in range(len(document)):
        page_file = destination / f"page-{index + 1:04d}.txt"
        if page_file.exists():
            continue
        page = document[index]
        text = page.get_text().strip()
        if not text:
            png = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False).tobytes("png")
            result = subprocess.run(
                ["tesseract", "stdin", "stdout", "-l", "jpn+kor+eng", "--psm", "6"],
                input=png, capture_output=True, timeout=90, check=True
            )
            text = result.stdout.decode("utf-8", errors="replace").strip()
        page_file.write_text(text + "\n", encoding="utf8")
        processed += 1
        if processed % 5 == 0:
            print(f"{args.pdf}: OCR {processed} new / {len(document)} total pages", flush=True)
        if args.pages and processed >= args.pages:
            break
    completed = sum(1 for index in range(len(document)) if (destination / f"page-{index + 1:04d}.txt").exists())
    (destination / "status.json").write_text(json.dumps({
        "source_file": args.pdf, "pages": len(document), "pages_with_text": completed,
        "complete": completed == len(document), "ocr_language": "jpn+kor+eng"
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"{args.pdf}: {completed}/{len(document)} pages available in {destination}", flush=True)


if __name__ == "__main__":
    main()
