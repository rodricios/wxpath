"""MkDocs macros module for loading template variables from docs_config.yml."""
import yaml
from pathlib import Path


def define_env(env):
    """
    Define environment variables for mkdocs-macros-plugin.
    
    This function loads variables from docs_config.yml and makes them
    available in all markdown files processed by MkDocs.
    """
    # Load config file (docs_config.yml is in the project root, one level up from docs/)
    config_path = Path(__file__).parent.parent / 'docs_config.yml'
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Make variables available in markdown templates
    # Access as {{ github.username }}, {{ project.name }}, etc.
    env.variables['github'] = config.get('github', {})
    env.variables['project'] = config.get('project', {})
    
    # Also add flattened versions for convenience
    for key, value in config.items():
        if isinstance(value, dict):
            for subkey, subvalue in value.items():
                env.variables[f'{key}_{subkey}'] = subvalue
        else:
            env.variables[key] = value
