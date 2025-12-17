import zipfile
import re
import logging
import shutil

class Node:
    def __init__(self, tag, text):
        self.tag = tag
        self.text = text
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
        if self.text:
            return f"<{self.tag} {self.text}>"
        else:
            return f"<{self.tag}>"
    def build(self):
        result = []

        # compact representation if no child nodes (optional)
        if len(self.children) == 0 or all(isinstance(child, str) for child in self.children):
            result.append(self.build_tag())
            for child in self.children:
                result.append(child)
            result.append(f"</{self.tag}>\n")
            return ''.join(result)

        result.append(self.build_tag() + "\n")
        for child in self.children:
            if isinstance(child, Node):
                result.append(child.build())
            else:
                result.append(child)
        result.append(f"</{self.tag}>\n")
        return ''.join(result)

class Xml:
    def __init__(self, s):
        self.i = 0
        s = s.strip()
        if s.startswith('<?xml'):
            self.header, s = s.split('?>', 1)
            self.header += '?>'
        else:
            self.header = ''
        print("header:", self.header, "rest length:", len(s))
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
        tagName, rest = re.match(r'([^\s/>]+)(.*)', tag).groups()
        self.i = end + 1
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
    for attr in node.text.split():
        if attr.startswith("gml:id="):
            gml_id = attr.split('=', 1)[1].strip('"')
            result.add(gml_id)
    for child in node.children:
        result.update(collect_gml_id_recurse(child))
    return result

def filter_gml_content(content, gml_ids):
    """Filter GML content to only include specific gml:id members."""
    text = content.decode('utf-8')
    xml = Xml(text)
    root = xml.root

    # Round #1: filter cityObjectMember nodes and collect referred gml:ids inside them
    count = [0, 0]  # kept, removed
    new_toplevels = []
    referred_gmlids = set()
    assert root.tag == "core:CityModel", f"Unexpected root tag: {root.tag}"
    for toplevel in root.children:
        assert isinstance(toplevel, Node), "CityModel child is not a Node"
        if toplevel.tag == "core:cityObjectMember":
            assert len(toplevel.children) == 1, "Unexpected structure in cityObjectMember"
            cityobject = toplevel.children[0]
            assert isinstance(cityobject, Node), "cityObjectMember child is not a Node"
            for attr in cityobject.text.split():
                if attr.startswith("gml:id="):
                    gml_id = attr.split('=', 1)[1].strip('"')
                    if gml_id in gml_ids:
                        count[0] += 1
                        break
            else:
                count[1] += 1
                continue
            referred_gmlids.update(collect_gml_id_recurse(cityobject))
            new_toplevels.append(toplevel)
        else:
            new_toplevels.append(toplevel)
    root.children = new_toplevels
    filtered_text = xml.build()
    print("<core:cityObjectMember> kept:", count[0], "removed:", count[1])
    print("referred gml:ids:", len(referred_gmlids))

    # Round #2: filter appearanceMember nodes based on referred gml:ids
    count = [0, 0]  # kept, removed
    referred_images = set()
    for toplevel in root.children:
        assert isinstance(toplevel, Node), "CityModel child is not a Node"
        if toplevel.tag == "app:appearanceMember":
            appearance = toplevel.only_node_child()
            assert appearance.tag == "app:Appearance", "Unexpected tag in appearanceMember"
            for member in appearance.children:
                assert isinstance(member, Node), "Appearance child is not a Node"
                if member.tag == "app:surfaceDataMember":
                    # we need to process two tags under surfaceDataMember: X3DMaterial and ParameterizedTexture
                    member2 = member.only_node_child()
                    new_children = []
                    member_referred = False
                    referred_images2 = set()
                    for child in member2.children:
                        assert isinstance(child, Node), "surfaceDataMember grandchild is not a Node"
                        if child.tag != "app:target":
                            if child.tag == "app:imageURI":
                                referred_images2.add(child.only_text_child())
                            new_children.append(child)
                            continue
                        # find children like <app:target>#fme-gen-833a934e-0449-4161-8b79-3e632df34a4b</app:target>
                        # or <app:target uri="#fme-gen-7efa16e4-50f2-4799-bea8-79e99ef207b3">...</app:target>
                        uri = None
                        for attr in child.text.split():
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
    print("<app:target> kept:", count[0], "removed:", count[1])
    for image in referred_images:
        print("referred image:", image)

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

def extract_zip_to_structure(src_zip, artifacts_base, testcase_base, name, tree):
    """Extract zip to artifacts (codelists/schemas) and testcase (filtered GML files)."""
    artifact_dir = artifacts_base / "citymodel" / src_zip.stem
    artifact_dir.mkdir(parents=True, exist_ok=True)
    testcase_dir = testcase_base / name / "citymodel"
    try:
        shutil.rmtree(testcase_dir)
    except FileNotFoundError:
        pass

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
            if should_include_path(path, tree) and not (path.startswith("codelists/") or path.startswith("schemas/")):
                zf.extract(item, testcase_dir)
                

if __name__ == "__main__":
    import tomllib, sys
    from pathlib import Path
    config_path = Path(sys.argv[1]).resolve()
    with config_path.open("rb") as f:
        config = tomllib.load(f)
    BASE_DIR = Path(__file__).parent.parent / "reearth-flow/engine/plateau-tiles-test"
    test_name = config_path.parent.relative_to(BASE_DIR / "testcases").as_posix()
    citymodel_path = Path(__file__).parent / "data"
    artifacts_base = BASE_DIR / "artifacts"
    testcase_base = BASE_DIR / "testcases"
    src_zip = citymodel_path / config["citygml_zip_name"]
    extract_zip_to_structure(src_zip, artifacts_base, testcase_base, test_name, config["filter"]["tree"])