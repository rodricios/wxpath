#!/usr/bin/env python3
"""
Pre-process README.md with template variables from docs_config.yml.

This script replaces template variables in README.md with values from
docs_config.yml, allowing README.md to use the same variables as MkDocs.

Usage:
    python scripts/preprocess_readme.py [--output README.md]

If --output is not specified, processes README.md in place.
"""
import argparse
import re
from pathlib import Path

import yaml


def load_config(config_path: Path) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def replace_variables(content: str, config: dict) -> str:
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


def main():
    parser = argparse.ArgumentParser(
        description='Pre-process README.md with template variables'
    )
    parser.add_argument(
        '--input',
        type=Path,
        default=Path('README.md'),
        help='Input README.md file (default: README.md)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output file (default: overwrites input)'
    )
    parser.add_argument(
        '--config',
        type=Path,
        default=Path('docs_config.yml'),
        help='Config file (default: docs_config.yml)'
    )
    
    args = parser.parse_args()
    
    # Load config
    if not args.config.exists():
        print(f"Error: Config file not found: {args.config}")
        return 1
    
    config = load_config(args.config)
    
    # Read README
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}")
        return 1
    
    with open(args.input, 'r') as f:
        content = f.read()
    
    # Replace variables
    processed_content = replace_variables(content, config)
    
    # Write output
    output_path = args.output or args.input
    with open(output_path, 'w') as f:
        f.write(processed_content)
    
    print(f"Processed {args.input} -> {output_path}")
    return 0


if __name__ == '__main__':
    exit(main())
