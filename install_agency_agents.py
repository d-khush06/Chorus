"""
Agency-Agents Installer for Google Antigravity on Windows / Cross-platform.
Converts markdown persona files from msitarzewski/agency-agents into Antigravity Skills.
"""

import os
import sys
import re
import argparse
import shutil
import subprocess
from pathlib import Path

DEFAULT_DIVISIONS_CORE = [
    'engineering',
    'security',
    'design',
    'testing',
    'product'
]

ALL_DIVISIONS = [
    'academic', 'design', 'engineering', 'finance', 'game-development',
    'gis', 'healthcare', 'marketing', 'paid-media', 'product',
    'project-management', 'research', 'sales', 'security',
    'spatial-computing', 'specialized', 'strategy', 'support', 'testing'
]

def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')

def parse_agent_md(file_path: Path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    parts = content.split('---', 2)
    name = ""
    desc = ""
    body = content

    if len(parts) >= 3:
        frontmatter = parts[1]
        body = parts[2].strip()

        # extract name:
        m_name = re.search(r'^name:\s*(.+)$', frontmatter, re.MULTILINE)
        if m_name:
            name = m_name.group(1).strip().strip("'\"")

        # extract description (may be multiline):
        m_desc = re.search(r'^description:\s*(.+?)(?=\n[a-zA-Z0-9_-]+:|\Z)', frontmatter, re.MULTILINE | re.DOTALL)
        if m_desc:
            desc = " ".join(m_desc.group(1).split()).strip().strip("'\"")

    if not name:
        stem = file_path.stem
        # Strip division prefix if present (e.g. engineering-frontend-developer -> frontend-developer)
        name = stem.replace('-', ' ').title()

    if not desc:
        desc = f"Specialized AI agent persona for {name}."

    return name, desc, body

def get_source_repo() -> Path:
    temp_dir = Path(os.path.expandvars(r'%TEMP%\agency-agents'))
    if temp_dir.exists() and (temp_dir / 'engineering').exists():
        return temp_dir

    print("Cloning msitarzewski/agency-agents to temp directory...")
    subprocess.run(
        ["git", "clone", "--depth", "1", "https://github.com/msitarzewski/agency-agents.git", str(temp_dir)],
        check=True
    )
    return temp_dir

def install_skills(source_repo: Path, dest_dir: Path, divisions: list[str]) -> int:
    dest_dir.mkdir(parents=True, exist_ok=True)
    installed_count = 0

    print(f"Installing to: {dest_dir}")
    print(f"Divisions selected: {', '.join(divisions)}")

    for div in divisions:
        div_dir = source_repo / div
        if not div_dir.exists():
            continue

        md_files = list(div_dir.glob("*.md"))
        for md_file in md_files:
            name, desc, body = parse_agent_md(md_file)
            slug = "agency-" + slugify(name)

            skill_folder = dest_dir / slug
            skill_folder.mkdir(parents=True, exist_ok=True)

            skill_file = skill_folder / "SKILL.md"
            # Escape single quotes in description
            escaped_desc = desc.replace("'", "''")

            content = f"""---
name: {slug}
description: '{escaped_desc}'
---

{body}
"""
            with open(skill_file, 'w', encoding='utf-8') as f:
                f.write(content)

            installed_count += 1

    return installed_count

def main():
    parser = argparse.ArgumentParser(description="Install Agency Agents into Antigravity")
    parser.add_argument('--scope', choices=['global', 'project'], default='global',
                        help="Where to install: global (~/.gemini/config/skills) or project (.agents/skills)")
    parser.add_argument('--divisions', nargs='+', default=['core'],
                        help="Divisions to install: 'core' (engineering, security, design, testing, product), 'all', or specific division names")
    parser.add_argument('--list', action='store_true', help="List all available divisions and agent counts")

    args = parser.parse_args()
    source_repo = get_source_repo()

    if args.list:
        print("\nAvailable Divisions in Agency-Agents:")
        print("-----------------------------------")
        total = 0
        for div in ALL_DIVISIONS:
            div_dir = source_repo / div
            if div_dir.exists():
                count = len(list(div_dir.glob("*.md")))
                total += count
                print(f"  - {div:<20}: {count} agents")
        print(f"\nTotal agents available: {total}\n")
        return

    selected_divisions = []
    if 'all' in args.divisions:
        selected_divisions = ALL_DIVISIONS
    elif 'core' in args.divisions:
        selected_divisions = DEFAULT_DIVISIONS_CORE
    else:
        selected_divisions = args.divisions

    # Resolve destination
    if args.scope == 'global':
        user_home = Path(os.path.expanduser('~'))
        dest = user_home / '.gemini' / 'config' / 'skills'
    else:
        # project directory
        dest = Path.cwd() / '.agents' / 'skills'

    count = install_skills(source_repo, dest, selected_divisions)
    print(f"\n[SUCCESS] Installed {count} Antigravity skills into: {dest}")
    print("\nHow to use in Antigravity chat:")
    print("  'Use the agency-frontend-developer skill to review our React UI'")
    print("  'Use the agency-backend-architect skill to design the video analysis pipeline'")
    print("  'Use the agency-code-reviewer skill to audit pipeline_runner.py'\n")

if __name__ == '__main__':
    main()
