#!/usr/bin/env python3
"""Build local skill archives. No upload, account access, or publication. Standard library only."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "dual-session-exec"


def skill_files():
    files = []
    for path in sorted(SKILL.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Skill must not contain symlinks: {path.name}")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            relative = path.relative_to(SKILL)
            allowed = (relative.as_posix() in {"SKILL.md", "LICENSE", "agents/openai.yaml"}
                       or len(relative.parts) == 2 and
                       ((relative.parts[0] == "scripts" and path.suffix == ".py")
                        or (relative.parts[0] == "references" and path.suffix == ".md")))
            if not allowed:
                raise ValueError(f"Unexpected file in skill package: {relative}")
            files.append(path)
    return files


def archive(path, files, entrypoint=None):
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as package:
        for source in files:
            name = "dual-session-exec/" + source.relative_to(SKILL).as_posix()
            data = entrypoint.encode("utf-8") if entrypoint is not None and source.name == "SKILL.md" else source.read_bytes()
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 27, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            package.writestr(info, data)


def build(out, author=None, market_draft=False):
    metadata = json.loads((ROOT / "publishing/marketplace.json").read_text(encoding="utf-8"))
    decisions_path = ROOT / "publishing/release-decisions.json"
    decisions = json.loads(decisions_path.read_text(encoding="utf-8")) if decisions_path.exists() else {}
    license_name = decisions.get("license", "undecided")
    pricing = decisions.get("pricing", {"mode": "undecided"})
    pricing_mode = pricing.get("mode", "undecided")
    author = author if author is not None else metadata.get("author")
    if author is not None and (not isinstance(author, str) or not author.strip()):
        raise ValueError("author must be a nonempty, confirmed publication name")
    if license_name == "MIT":
        if not (ROOT / "LICENSE").is_file() or not (SKILL / "LICENSE").is_file():
            raise ValueError("MIT release requires LICENSE in both project and skill directories")
        if (ROOT / "LICENSE").read_bytes() != (SKILL / "LICENSE").read_bytes():
            raise ValueError("Project and packaged LICENSE files must match")
    files = skill_files()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    archive(out / "dual-session-exec-1.0.0-portable.zip", files)
    pending = (["author"] if author is None else [])
    if license_name == "undecided":
        pending.append("license")
    if pricing_mode == "undecided":
        pending.append("pricing")
    pending.append("target-release acceptance")
    status = {"version": "1.0.0", "publication_status": "draft_not_published" if market_draft or author is None else "candidate_not_published",
              "author": author, "license": license_name, "pricing": pricing_mode, "pricing_details": pricing,
              "user_decisions_confirmed": author is not None and license_name != "undecided" and pricing_mode != "undecided",
              "workbuddy_archive_created": False,
              "workbuddy_archive_file": None, "workbuddy_archive_kind": None,
              "market_metadata_complete": False, "missing_market_metadata": ["author"] if author is None else [],
              "submission_ready": False, "review_submitted": False, "published": False, "platform_pricing_applied": False,
              "live_host_e2e": "not_assessed_by_builder",
              "validation_note": "Build does not execute host tests; see README.md for supported hosts.",
              "pending": pending}
    if author is not None or market_draft:
        metadata["author"] = author
        body = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2]
        frontmatter = "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in metadata.items()) + "\n---"
        filename = ("dual-session-exec-1.0.0-workbuddy-draft.zip" if market_draft
                    else "dual-session-exec-1.0.0-workbuddy.zip")
        archive(out / filename, files, frontmatter + body)
        (out / "MARKET_METADATA.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        status["workbuddy_archive_created"] = True
        status["workbuddy_archive_file"] = filename
        status["workbuddy_archive_kind"] = "draft" if market_draft else "candidate"
        required = ("name", "display_name", "display_name_en", "description",
                    "description_zh", "description_en", "version", "author")
        status["missing_market_metadata"] = [key for key in required
                                             if not isinstance(metadata.get(key), str) or not metadata[key].strip()]
        status["market_metadata_complete"] = not status["missing_market_metadata"]
    shutil.copy2(ROOT / "NOTICE.md", out / "NOTICE.md")
    if (ROOT / "LICENSE").is_file():
        shutil.copy2(ROOT / "LICENSE", out / "LICENSE")
    if decisions_path.exists():
        shutil.copy2(decisions_path, out / "RELEASE_DECISIONS.json")
    (out / "release-status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}
    (out / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in hashes.items()), encoding="utf-8")
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="New output directory; never overwrite an existing release")
    parser.add_argument("--author", help="Confirmed author/brand override; defaults to marketplace.json")
    parser.add_argument("--market-draft", action="store_true", help="Build a named DRAFT market ZIP, keeping unknown author null; never submission-ready")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.out, args.author, args.market_draft), ensure_ascii=False))
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
