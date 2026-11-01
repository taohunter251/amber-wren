from __future__ import annotations

import re

_FENCE = re.compile(r"```(?:[a-zA-Z]+)?\s*\n(.*?)```", re.DOTALL)
_EXPORT = re.compile(r"export\s+default\s+function\s*([A-Za-z_$][\w$]*)?\s*\(\s*THREE\s*\)")
_CODE_START = ("function", "const", "let", "var", "export", "//", "/*", "'use", '"use')

WRAP = """
export default function generate(THREE) {
  const inner = __inner(THREE);
  const pivot = new THREE.Group();
  pivot.add(inner);
  pivot.rotation.set(%(rx)s, %(ry)s, 0);
  const root = new THREE.Group();
  root.add(pivot);
  root.updateMatrixWorld(true);
  const parts = [];
  root.traverse((o) => {
    if ((o.isMesh || o.isLine || o.isPoints) && !o.isInstancedMesh && o.geometry && o.matrixWorld.determinant() > 0) parts.push(o);
  });
  const bake = new Set(parts);
  for (const o of parts) {
    if (o.children.some((c) => !bake.has(c))) { bake.delete(o); continue; }
    o.geometry = o.geometry.clone();
    o.geometry.applyMatrix4(o.matrixWorld);
    o.removeFromParent();
    o.position.set(0, 0, 0);
    o.quaternion.set(0, 0, 0, 1);
    o.scale.set(1, 1, 1);
    root.add(o);
  }
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  const size = new THREE.Vector3();
  const center = new THREE.Vector3();
  box.getSize(size);
  box.getCenter(center);
  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  const s = 0.99 / maxDim;
  root.scale.setScalar(s);
  root.position.set(-center.x * s, -center.y * s, -center.z * s);
  return root;
}
"""


def extract(text: str | None) -> str | None:
    if not text:
        return None
    blocks = [b for b in _FENCE.findall(text) if "export default" in b]
    src = max(blocks, key=len) if blocks else text
    if "export default" not in src:
        return None
    lines = src.strip().splitlines()
    while lines and not lines[0].lstrip().startswith(_CODE_START):
        lines.pop(0)
    return "\n".join(lines).strip() or None


def wrap(js: str, ry: str = "0", rx: str = "0") -> str | None:
    m = _EXPORT.search(js)
    if not m or "__inner" in js:
        return None
    inner = js[:m.start()] + "function __inner(THREE)" + js[m.end():]
    return inner.rstrip() + "\n" + WRAP % {"rx": rx, "ry": ry}


FLAT = ("  pivot.updateMatrixWorld(true);\n"
        "  const box0 = new THREE.Box3().setFromObject(pivot);\n"
        "  const size0 = new THREE.Vector3();\n"
        "  box0.getSize(size0);\n"
        "  if (size0.y < 0.5 * Math.max(size0.x, size0.z)) pivot.rotation.set(0.261799, 0, 0);\n")


def final(js: str) -> str | None:
    out = wrap(js)
    return None if out is None else out.replace("  pivot.rotation.set(0, 0, 0);\n", FLAT, 1)
