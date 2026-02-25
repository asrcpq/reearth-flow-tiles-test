import zipfile
import re
import logging
import shutil
import os

class Node:
    def __init__(self, name, attr):
        self.name = name
        self.attr = attr
        self.children = []
    def only_node_child(self):
        assert len(self.children) == 1, "Node does not have exactly one child"
        child = self.children[0]
        assert isinstance(child, Node), "Child is not a Node"
        return child
    def only_text_child(self):
        assert len(self.children) == 1, "Node does not have exactly one child"
        child = self.children[0]
        assert isinstance(child, str), "Child is not a text node"
        return child
    def build_tag(self):
        if self.attr:
            return f"<{self.name} {self.attr}>"
        else:
            return f"<{self.name}>"
    def build(self):
        result = []

        # compact representation if no child nodes (optional)
        if len(self.children) == 0 or all(isinstance(child, str) for child in self.children):
            result.append(self.build_tag())
            for child in self.children:
                result.append(child)
            result.append(f"</{self.name}>\n")
            return ''.join(result)

        result.append(self.build_tag() + "\n")
        for child in self.children:
            if isinstance(child, Node):
                result.append(child.build())
            else:
                result.append(child)
        result.append(f"</{self.name}>\n")
        return ''.join(result)

class Xml:
    def __init__(self, s):
        self.i = 0
        s = s.strip()
        # strip BOM
        if s.startswith('\ufeff'):
            s = s[1:]
        if s.startswith('<?xml'):
            self.header, s = s.split('?>', 1)
            self.header += '?>'
        else:
            self.header = ''
        self.root = self._parse(s.strip())
    def build(self):
        result = []
        result.append(self.header)
        result.append(self.root.build())
        return ''.join(result)
    def _parse(self, xml):
        if self.i >= len(xml) or xml[self.i] != '<':
            return None
        self.i += 1
        end = xml.find('>', self.i)
        tag = xml[self.i:end]
        # allow newline in tag
        tagName, rest = re.match(r'([^\s/>]+)(.*)', tag, re.DOTALL).groups()
        self.i = end + 1
        # Handle self-closing tags
        if rest.rstrip().endswith('/'):
            return Node(tagName.strip(), rest.rstrip()[:-1].strip())
        node = Node(tagName.strip(), rest.strip())
        while self.i < len(xml):
            if xml[self.i:self.i+2] == '</':
                i2 = xml.find('>', self.i) + 1
                assert xml[self.i+2:i2-1] == tagName, f"Mismatched tag: {xml[self.i+2:i2-1]} != {tagName}"
                self.i = i2
                break
            elif xml[self.i] == '<':
                node.children.append(self._parse(xml))
            else:
                text_end = xml.find('<', self.i)
                text = xml[self.i:text_end].strip()
                if text:
                    node.children.append(text)
                self.i = text_end
        return node

def collect_gml_id_recurse(node):
    result = set()
    if isinstance(node, str):
        return result
    for attr in node.attr.split():
        if attr.startswith("gml:id="):
            gml_id = attr.split('=', 1)[1].strip('"')
            result.add(gml_id)
    for child in node.children:
        result.update(collect_gml_id_recurse(child))
    return result

def get_gml_id(node):
    """Extract gml:id from a node's attributes, or None."""
    if isinstance(node, str):
        return None
    for attr in node.attr.split():
        if attr.startswith("gml:id="):
            return attr.split('=', 1)[1].strip('"')
    return None

def is_subfeature(node):
    """A sub-feature has gml:id and is not a gml: geometry element."""
    return isinstance(node, Node) and get_gml_id(node) is not None and not node.name.startswith("gml:")

def contains_subfeature(node):
    """Check if node or any descendant is a sub-feature."""
    if isinstance(node, str):
        return False
    if is_subfeature(node):
        return True
    return any(contains_subfeature(c) for c in node.children)

def find_path_to(node, target_id):
    """Find path from node to descendant with target gml:id. Returns list of nodes or None."""
    if isinstance(node, str):
        return None
    if get_gml_id(node) == target_id:
        return [node]
    for child in node.children:
        path = find_path_to(child, target_id)
        if path is not None:
            return [node] + path
    return None

def prune_to_targets(node, target_ids):
    """Prune tree: keep paths to targets and non-feature siblings; remove the rest.
    Returns True if any target found."""
    path_node_ids = set()
    for tid in target_ids:
        path = find_path_to(node, tid)
        if path:
            path_node_ids.update(id(n) for n in path)
    if not path_node_ids:
        return False
    def _prune(n):
        new_children = []
        for child in n.children:
            if isinstance(child, str):
                new_children.append(child)
            elif id(child) in path_node_ids:
                _prune(child)
                new_children.append(child)
            elif not contains_subfeature(child):
                new_children.append(child)
        n.children = new_children
    _prune(node)
    return True

def filter_appearance_members(root, referred_gmlids):
    """Filter appearance members to only include targets in referred_gmlids.
    Returns set of referred image URIs."""
    count = [0, 0]  # kept, removed
    referred_images = set()
    for toplevel in root.children:
        assert isinstance(toplevel, Node), "CityModel child is not a Node"
        if toplevel.name == "app:appearanceMember":
            appearance = toplevel.only_node_child()
            assert appearance.name == "app:Appearance", "Unexpected tag in appearanceMember"
            for member in appearance.children:
                assert isinstance(member, Node), "Appearance child is not a Node"
                if member.name == "app:surfaceDataMember":
                    member2 = member.only_node_child()
                    new_children = []
                    member_referred = False
                    referred_images2 = set()
                    for child in member2.children:
                        assert isinstance(child, Node), "surfaceDataMember grandchild is not a Node"
                        if child.name != "app:target":
                            if child.name == "app:imageURI":
                                referred_images2.add(child.only_text_child())
                            new_children.append(child)
                            continue
                        uri = None
                        for attr in child.attr.split():
                            if attr.startswith("uri="):
                                uri = attr.split('=', 1)[1].strip('"')
                                break
                        else:
                            uri = child.only_text_child()
                        if uri.removeprefix('#') in referred_gmlids:
                            member_referred = True
                            count[0] += 1
                            new_children.append(child)
                        else:
                            count[1] += 1
                    if member_referred:
                        referred_images.update(referred_images2)
                    member2.children = new_children
            # Remove surfaceDataMembers with no remaining targets
            appearance.children = [
                m for m in appearance.children
                if not isinstance(m, Node) or m.name != "app:surfaceDataMember"
                or any(isinstance(c, Node) and c.name == "app:target" for c in m.only_node_child().children)
            ]
    print("<app:target> kept:", count[0], "removed:", count[1])
    for image in referred_images:
        print("referred image:", image)
    return referred_images

def filter_gml_content(content, gml_ids):
    """Filter GML content to only include specific gml:id members.
    Supports both top-level and nested gml:ids."""
    text = content.decode('utf-8')
    xml = Xml(text)
    root = xml.root

    gml_ids = set(gml_ids)
    # Round #1: filter cityObjectMember nodes and collect referred gml:ids inside them
    count = [0, 0]  # kept, removed
    new_toplevels = []
    referred_gmlids = set()
    assert root.name == "core:CityModel", f"Unexpected root tag: {root.name}"
    for toplevel in root.children:
        assert isinstance(toplevel, Node), "CityModel child is not a Node"
        if toplevel.name != "core:cityObjectMember":
            new_toplevels.append(toplevel)
            continue
        cityobject = toplevel.only_node_child()
        top_id = get_gml_id(cityobject)
        if top_id in gml_ids:
            # Top-level match
            count[0] += 1
        elif prune_to_targets(cityobject, gml_ids):
            # Nested match found, tree pruned
            count[0] += 1
        else:
            count[1] += 1
            continue
        referred_gmlids.update(collect_gml_id_recurse(cityobject))
        new_toplevels.append(toplevel)
    root.children = new_toplevels
    print("<core:cityObjectMember> kept:", count[0], "removed:", count[1])
    print("referred gml:ids:", len(referred_gmlids))

    # Round #2: filter appearanceMember nodes based on referred gml:ids
    referred_images = filter_appearance_members(root, referred_gmlids)

    return xml.build().encode(), referred_images

def should_include_path(path, tree):
    """Check if a path should be included based on tree structure."""
    for prefix, items in tree.items():
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            continue

        if not path.startswith(prefix):
            continue

        rest = path[len(prefix):]
        for item in items:
            if rest.startswith(item):
                return True

    return False

def create_symlinks_to_artifacts(testcase_dir, artifact_dir):
    """Create symlinks for codelists and schemas in testcase dir pointing to artifacts."""
    testcase_dir.mkdir(parents=True, exist_ok=True)

    # Calculate relative path from testcase_dir to artifact_dir
    rel_artifact_dir = os.path.relpath(artifact_dir, testcase_dir)

    # Create symlinks for codelists and schemas
    for dirname in ["codelists", "schemas"]:
        link_path = testcase_dir / dirname
        target_path = f"{rel_artifact_dir}/{dirname}"

        # Remove existing symlink or directory
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()

        # Create symlink
        link_path.symlink_to(target_path)

def extract_zip_to_structure(src_zip, artifacts_base, testcase_base, name, tree):
    """Extract zip to artifacts (codelists/schemas) and testcase (filtered GML files)."""
    artifact_dir = artifacts_base / "citymodel" / src_zip.stem
    artifact_dir.mkdir(parents=True, exist_ok=True)
    testcase_dir = testcase_base / name / "citymodel"
    try:
        shutil.rmtree(testcase_dir)
    except FileNotFoundError:
        pass

    # Create symlinks to codelists and schemas in artifacts
    create_symlinks_to_artifacts(testcase_dir, artifact_dir)

    with zipfile.ZipFile(src_zip, 'r') as zf:
        def extract(path, data = None):
            out_path = testcase_dir / path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if data is None:
                data = zf.read(path)
            out_path.write_bytes(data)
        for item in zf.infolist():
            path = item.filename

            # Skip directories
            if path.endswith('/'):
                continue

            # Extract codelists/ and schemas/ to artifacts
            if path.startswith("codelists/") or path.startswith("schemas/"):
                zf.extract(item, artifact_dir)
                continue

            # Extract and filter GML files to testcase/citymodel/
            if path in tree and isinstance(tree[path], list):
                gml_ids = tree[path]
                content = zf.read(path)
                filtered_content, referred_images = filter_gml_content(content, gml_ids)
                for image in referred_images:
                    image_path = path.rsplit('/', 1)[0] + f'/{image}'
                    extract(image_path)
                extract(path, filtered_content)
                continue

            # Extract matching files to testcase/citymodel/
            if should_include_path(path, tree):
                zf.extract(item, testcase_dir)
                

if __name__ == "__main__":
    import tomllib, sys
    from pathlib import Path
    config_path = Path(sys.argv[1]).resolve()
    with config_path.open("rb") as f:
        config = tomllib.load(f)
    TESTING_DATA_DIR = Path(__file__).parent.parent / "reearth-flow/engine/testing/data"
    test_name = config_path.parent.relative_to(TESTING_DATA_DIR / "testcases").as_posix()
    citymodel_path = Path(__file__).parent / "data"
    artifacts_base = TESTING_DATA_DIR / "fixtures/plateau-citymodel"
    testcase_base = TESTING_DATA_DIR / "testcases"
    zip_name = config["citygml_zip_name"].rsplit("_op_", 1)[0] + "_op.zip"
    src_zip = citymodel_path / zip_name
    extract_zip_to_structure(src_zip, artifacts_base, testcase_base, test_name, config["filter"]["tree"])
