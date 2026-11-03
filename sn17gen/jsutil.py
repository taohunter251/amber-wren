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


BOX = "  root.updateMatrixWorld(true);\n  const box = new THREE.Box3().setFromObject(root);\n"
BAKE = """  root.updateMatrixWorld(true);
  {
    const KEEP = new Set(["position", "normal", "uv", "uv1", "uv2", "color"]);
    const mergeable = (o) => {
      const g = o.geometry;
      if (!g || !g.isBufferGeometry || Object.keys(g.morphAttributes || {}).length) return false;
      if (Object.keys(g.attributes).some((k) => !KEEP.has(k)) || !g.attributes.position) return false;
      return o.count * g.attributes.position.count <= 3000000 && (!Array.isArray(o.material) || g.groups.length > 0);
    };
    const merge = (o) => {
      const g = o.geometry, n = g.attributes.position.count, idx = g.index;
      const names = Object.keys(g.attributes);
      const col = o.instanceColor;
      if (col && !names.includes("color")) names.push("color");
      const out = {};
      for (const k of names) {
        const a = g.attributes[k];
        out[k] = new Float32Array(o.count * n * (a ? a.itemSize : 3));
      }
      const tri = idx ? idx.count : n;
      const multiIdx = Array.isArray(o.material) ? g.groups.reduce((a, gr) => a + Math.min(gr.count, tri - gr.start), 0) : tri;
      const index = new Uint32Array(o.count * multiIdx);
      const flips = [];
      const m = new THREE.Matrix4(), im = new THREE.Matrix4(), nm = new THREE.Matrix3();
      const v = new THREE.Vector3(), c = new THREE.Color();
      for (let i = 0; i < o.count; i++) {
        o.getMatrixAt(i, im);
        m.multiplyMatrices(o.matrixWorld, im);
        nm.getNormalMatrix(m);
        const flip = m.determinant() < 0;
        const base = i * n;
        for (let j = 0; j < n; j++) {
          v.fromBufferAttribute(g.attributes.position, j).applyMatrix4(m);
          out.position.set([v.x, v.y, v.z], (base + j) * 3);
          if (g.attributes.normal) {
            v.fromBufferAttribute(g.attributes.normal, j).applyMatrix3(nm).normalize();
            out.normal.set([v.x, v.y, v.z], (base + j) * 3);
          }
          for (const k of names) {
            if (k === "position" || k === "normal" || k === "color") continue;
            const a = g.attributes[k];
            for (let s = 0; s < a.itemSize; s++) out[k][(base + j) * a.itemSize + s] = a.getComponent(j, s);
          }
          if (out.color) {
            const a = g.attributes.color;
            if (a) c.fromBufferAttribute(a, j); else c.setRGB(1, 1, 1);
            if (col) c.multiply(new THREE.Color().fromBufferAttribute(col, i));
            out.color.set([c.r, c.g, c.b], (base + j) * 3);
          }
        }
        flips.push(flip);
      }
      const multi = Array.isArray(o.material);
      const groups = multi ? g.groups : [{ start: 0, count: tri, materialIndex: 0 }];
      const geo = new THREE.BufferGeometry();
      let w = 0;
      for (const gr of groups) {
        const end = Math.min(gr.start + gr.count, tri), from = w;
        for (let i = 0; i < o.count; i++) {
          const base = i * n, flip = flips[i];
          for (let t = gr.start; t + 2 < end; t += 3) {
            const a0 = idx ? idx.getX(t) : t, a1 = idx ? idx.getX(t + 1) : t + 1, a2 = idx ? idx.getX(t + 2) : t + 2;
            index[w++] = base + a0;
            index[w++] = base + (flip ? a2 : a1);
            index[w++] = base + (flip ? a1 : a2);
          }
        }
        if (multi) geo.addGroup(from, w - from, gr.materialIndex);
      }
      for (const k of names) {
        const a = g.attributes[k];
        geo.setAttribute(k, new THREE.BufferAttribute(out[k], a ? a.itemSize : 3));
      }
      geo.setIndex(new THREE.BufferAttribute(index.subarray(0, w), 1));
      const fix = (mt) => { if (col && !mt.vertexColors) { mt = mt.clone(); mt.vertexColors = true; } return mt; };
      const mat = Array.isArray(o.material) ? o.material.map(fix) : fix(o.material);
      const mesh = new THREE.Mesh(geo, mat);
      mesh.castShadow = o.castShadow; mesh.receiveShadow = o.receiveShadow; mesh.renderOrder = o.renderOrder;
      return mesh;
    };
    const parts = [], inst = [];
    let ok = true, verts = 0;
    root.traverse((o) => {
      if ((o.isMesh || o.isLine || o.isPoints) && o.geometry && o.geometry.attributes.position) verts += o.geometry.attributes.position.count;
    });
    root.traverse((o) => {
      if (o === root || o.isGroup || (o.isObject3D && o.type === "Object3D")) return;
      if (o.isInstancedMesh) { if (mergeable(o)) inst.push(o); return; }
      const plain = (o.isMesh || o.isLineSegments || o.isLine || o.isPoints) && !o.isSkinnedMesh
        && o.geometry && o.geometry.isBufferGeometry && !Object.keys(o.geometry.morphAttributes || {}).length
        && o.matrixWorld.determinant() > 0;
      if (plain) parts.push([o, o.matrixWorld.clone()]); else ok = false;
    });
    inst.sort((a, b) => a.count * a.geometry.attributes.position.count - b.count * b.geometry.attributes.position.count);
    for (const o of inst) {
      const add = (o.count - 1) * o.geometry.attributes.position.count;
      if (verts + add <= 240000) { verts += add; parts.push([o, null]); }
    }
    if (ok && parts.length) {
      const flat = [];
      for (const [o, m] of parts) {
        if (m === null) { flat.push(merge(o)); continue; }
        o.geometry = o.geometry.clone().applyMatrix4(m);
        o.position.set(0, 0, 0); o.rotation.set(0, 0, 0); o.scale.set(1, 1, 1);
        flat.push(o);
      }
      for (const [o, m] of parts) if (m === null) o.removeFromParent();
      for (const o of flat) { o.removeFromParent(); root.add(o); }
      let left = false;
      pivot.traverse((o) => { if (o.isMesh || o.isLine || o.isPoints) left = true; });
      if (!left) root.remove(pivot);
      root.updateMatrixWorld(true);
    }
  }
  const box = new THREE.Box3().setFromObject(root);
"""


def final(js: str) -> str | None:
    out = wrap(js)
    return None if out is None else out.replace("  pivot.rotation.set(0, 0, 0);\n", FLAT, 1)


def output(js: str) -> str | None:
    out = final(js)
    return None if out is None else out.replace(BOX, BAKE, 1)
