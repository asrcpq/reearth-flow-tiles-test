import sys
import re

def parse_dependency_blocks(content):
    """Parse TOML dependencies and return list of (start, end, name, dict) tuples"""
    blocks = []
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]
        # Match dependency definition: name = { ... }
        match = re.match(r'^([a-zA-Z0-9_-]+)\s*=\s*\{(.*)$', line)
        if match:
            name = match.group(1)
            rest = match.group(2)
            start_line = i

            # Check if it's single-line (ends with })
            if '}' in rest:
                # Single-line dependency
                content_str = rest[:rest.rindex('}')]
                blocks.append((start_line, i, name, content_str))
            else:
                # Multi-line dependency - find closing brace
                content_parts = [rest]
                i += 1
                while i < len(lines):
                    if '}' in lines[i]:
                        content_parts.append(lines[i][:lines[i].index('}')])
                        blocks.append((start_line, i, name, '\n'.join(content_parts)))
                        break
                    content_parts.append(lines[i])
                    i += 1
        i += 1

    return blocks

def parse_dependency_content(content_str):
    """Parse dependency content into a dict"""
    deps = {}
    # Match key = "value" pairs
    for match in re.finditer(r'([a-zA-Z0-9_-]+)\s*=\s*"([^"]*)"', content_str):
        deps[match.group(1)] = match.group(2)

    # Match features array
    features_match = re.search(r'features\s*=\s*\[(.*?)\]', content_str, re.DOTALL)
    if features_match:
        features_str = features_match.group(1)
        features = [f.strip().strip('"') for f in features_str.split(',') if f.strip()]
        deps['features'] = features

    return deps

def build_dependency_line(name, deps, is_multiline):
    """Rebuild dependency line from dict - always as inline table"""
    parts = []
    for key, value in deps.items():
        if key == 'features':
            features_str = ', '.join([f'"{f}"' for f in value])
            parts.append(f'{key} = [{features_str}]')
        else:
            parts.append(f'{key} = "{value}"')
    return f'{name} = {{ {", ".join(parts)} }}'

def update_toml_file(file_path, git_url, branch=None):
    with open(file_path, 'r') as f:
        content = f.read()

    lines = content.split('\n')
    blocks = parse_dependency_blocks(content)

    # Process blocks in reverse to maintain line positions
    for start_line, end_line, name, content_str in reversed(blocks):
        deps = parse_dependency_content(content_str)

        # Only process if it matches our git URL
        if 'git' not in deps or git_url not in deps['git']:
            continue

        is_multiline = start_line != end_line

        if branch:
            # Branch mode: replace tag with branch
            if 'tag' in deps:
                deps['branch'] = branch
                del deps['tag']
        else:
            # Local mode: replace git+tag/branch with path
            if 'git' in deps:
                del deps['git']
            if 'tag' in deps:
                del deps['tag']
            if 'branch' in deps:
                del deps['branch']
            deps['path'] = f'../../plateau-gis-converter/{name}'

        # Rebuild the dependency line
        new_content = build_dependency_line(name, deps, is_multiline)

        # Replace the lines
        lines[start_line:end_line+1] = new_content.split('\n')

    with open(file_path, 'w') as f:
        f.write('\n'.join(lines))

git_url = "https://github.com/reearth/plateau-gis-converter"
toml_path = "/Users/tsq/Projects/reearth-flow/engine/Cargo.toml"

if len(sys.argv) > 1:
    # Branch mode
    branch = sys.argv[1]
    update_toml_file(toml_path, git_url, branch=branch)
else:
    # Local mode
    update_toml_file(toml_path, git_url, branch=None)
