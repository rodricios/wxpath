#!/usr/bin/env python3
"""
Update mkdocs.yml and README.md from docs_config.yml.

This script reads template variables from docs_config.yml and updates:
1. mkdocs.yml - replaces placeholder values
2. README.md - replaces template variables ({{ variable }})

Usage:
    python scripts/update_docs_from_config.py
"""
import re
from pathlib import Path

import yaml


def load_config(config_path: Path) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def update_mkdocs_yml(mkdocs_path: Path, config: dict):
    """Update mkdocs.yml with values from config."""
    with open(mkdocs_path, 'r') as f:
        content = f.read()
    
    # Define replacements
    replacements = {
        'site_name: wxpath': f"site_name: {config['project']['name']}",
        'site_description: Declarative web crawling with XPath': 
            f"site_description: {config['project']['description']}",
        'site_author: Rodrigo Palacios': f"site_author: {config['project']['author']}",
        'site_url: https://rodricios.github.io/wxpath/': 
            f"site_url: {config['github']['pages_url']}",
        'repo_name: wxpath': f"repo_name: {config['project']['name']}",
        'repo_url: https://github.com/rodricios/wxpath': f"repo_url: {config['github']['url']}",
        'link: https://github.com/rodricios/wxpath': f"link: {config['github']['url']}",
    }
    
    # Apply replacements
    for old, new in replacements.items():
        content = content.replace(old, new)
    
    with open(mkdocs_path, 'w') as f:
        f.write(content)
    
    print(f"Updated {mkdocs_path}")


def replace_variables_in_readme(content: str, config: dict) -> str:
    """
    Replace template variables in content with values from config.
    
    Supports both {{ variable }} and {{ nested.variable }} syntax.
    """
    def replace_match(match):
        var_path = match.group(1).strip()
        parts = var_path.split('.')
        
        # Navigate through nested dict
        value = config
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
                if value is None:
                    return match.group(0)  # Return original if not found
            else:
                return match.group(0)  # Return original if not found
        
        return str(value)
    
    # Pattern to match {{ variable }} or {{ nested.variable }}
    pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}'
    return re.sub(pattern, replace_match, content)


def update_readme(readme_path: Path, config: dict):
    """Update README.md with values from config."""
    with open(readme_path, 'r') as f:
        content = f.read()
    
    processed_content = replace_variables_in_readme(content, config)
    
    with open(readme_path, 'w') as f:
        f.write(processed_content)
    
    print(f"Updated {readme_path}")


def main():
    root = Path(__file__).parent.parent
    config_path = root / 'docs_config.yml'
    mkdocs_path = root / 'mkdocs.yml'
    readme_path = root / 'README.md'
    
    # Load config
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        return 1
    
    config = load_config(config_path)
    
    # Update mkdocs.yml
    if mkdocs_path.exists():
        update_mkdocs_yml(mkdocs_path, config)
    else:
        print(f"Warning: {mkdocs_path} not found, skipping")
    
    # Update README.md
    if readme_path.exists():
        update_readme(readme_path, config)
    else:
        print(f"Warning: {readme_path} not found, skipping")
    
    print("Done!")
    return 0


if __name__ == '__main__':
    exit(main())
