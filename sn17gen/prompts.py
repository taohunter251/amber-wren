RULES = """Module contract (violations are rejected by a static validator):
- Return ONLY JavaScript. One export: `export default function generate(THREE) { ... return root; }`, synchronous.
- THREE exists only as that parameter. Helpers that need it take a parameter named exactly `THREE`. Never alias THREE, never `THREE[expr]`, never reference THREE at top level.
- Forbidden anywhere, even as local variable names: import, require, Math.random, Date, performance, fetch, XMLHttpRequest, WebSocket, window, document, navigator, self, global, globalThis, module, process, eval, Function, setTimeout, setInterval, setImmediate, queueMicrotask, crypto, Proxy, Reflect, WeakRef, Worker, localStorage.
- Allowed THREE members: Group, Object3D, Mesh, InstancedMesh, Line, LineSegments, Points; BufferGeometry, BufferAttribute, Float32BufferAttribute, Uint16BufferAttribute, Uint32BufferAttribute; BoxGeometry, SphereGeometry, CylinderGeometry, CapsuleGeometry, ConeGeometry, TorusGeometry, TorusKnotGeometry, PlaneGeometry, CircleGeometry, RingGeometry, TetrahedronGeometry, OctahedronGeometry, DodecahedronGeometry, IcosahedronGeometry, PolyhedronGeometry, ExtrudeGeometry, LatheGeometry, ShapeGeometry, TubeGeometry, EdgesGeometry; MeshStandardMaterial, MeshPhysicalMaterial, MeshBasicMaterial, LineBasicMaterial, PointsMaterial; DataTexture (procedural data only; geometry needs uv); Vector2, Vector3, Vector4, Matrix3, Matrix4, Quaternion, Euler, Box3, Sphere, Color, MathUtils (not seededRandom/generateUUID); Shape, Path, Curve, CurvePath, CatmullRomCurve3, CubicBezierCurve3, QuadraticBezierCurve3, LineCurve3, EllipseCurve, ArcCurve, SplineCurve; constants such as DoubleSide, FrontSide, SRGBColorSpace, RepeatWrapping, RGBAFormat, UnsignedByteType, LinearFilter, NearestFilter.
- Forbidden THREE APIs: loaders, ShaderMaterial, RawShaderMaterial, MeshLambertMaterial, MeshPhongMaterial, CanvasTexture, morph targets, animation.
- Limits: <=200 draw calls (meshes), <=250,000 vertices, <=50,000 instances, scene depth <=32, <=4 MiB of texture data in total (one 1024x1024 RGBA DataTexture is already 4 MiB; use 256x256 or 512x512), <=50 KB of string+numeric literals, <=5 s, deterministic (no randomness; derive variation from indices with sin/cos hashes).
- Practical budget: the software renderer times out on heavy scenes, so stay under about 60,000 vertices, 120 meshes and 5,000 instances. Make each DataTexture at most 512x512, create it once and reuse it, and use at most 6. Spend detail where the cameras see it.
- Never put a unary minus or plus directly before `**` (`-x ** 2` is a syntax error); write `-(x ** 2)`.
- Y is up. Build at natural scale; the result is re-centered and scaled into [-0.5, 0.5] automatically."""

JUDGING = """How the result is judged: the module is rendered on a white background (and a mid-gray one) by a camera on the +Z side looking at the origin: from 30 degrees to the right (+X) of +Z, 30 degrees to the left, from about 30 degrees above, and slightly from below; plus the right, back, left and top views. The camera is perspective with a 49.1 degree field of view at 2.0 units from the origin. A vision-language model compares each render with the reference photo and prefers the model that looks more like the same object: overall shape and proportions, colors and materials, distinctive parts and their counts, and a complete, plausible object from every side. It penalises missing or extra parts, floating parts, wrong colors, washed-out or blackened materials, and anything that is not the object (floors, pedestals, boxes, frames).
Pose: place the object so that the camera on +Z, slightly above, sees it the way the photo shows it (same side facing the viewer, same upright/lying/profile pose and left-right direction). Do not canonicalise it: an object that lies, leans or runs diagonally in the photo keeps that lie, lean or diagonal in the X-Y plane. A long object photographed from the side (boat, car, train, shoe, sandal, knife, pen, animal in profile) runs along X, never toward the camera. Objects photographed face-on or lying flat (boards, plates, trays, coins, clocks, signs, cards, book covers) present that face toward +Z, so the front views see the face and not a thin edge. This rule overrides any other "+Z forward" convention. Model only the object itself, never the floor, background, shadows or reflections."""

CRAFT = """Craft:
- Decompose the object into its real parts. Get the silhouette and proportions right first, then add the distinctive details (bevels, rims, seams, handles, holes, rivets, markings) and reproduce the exact count of every repeated part. Where the photo shows a label, logo or printed pattern, paint it as a simple DataTexture in the right colours and place it on the right face.
- Use LatheGeometry for round profiles, ExtrudeGeometry (with bevel) for flat shapes with outlines, TubeGeometry for bent rods/cables/handles, smooth sphere/capsule segments for organic forms; scale spheres non-uniformly for ellipsoids.
- Use MeshStandardMaterial/MeshPhysicalMaterial with the photo's actual colors (hex), sensible roughness, metalness only for metal and at most 0.6 (higher renders black under the judge's light; carry the metal shade in the colour, e.g. silver #b8b8b8, metalness 0.5, roughness 0.3). MeshBasicMaterial only for small glowing parts. Match the photo's hue and saturation: do not lighten, grey out or darken colours. Avoid pure white (use at most about #e6e6e6, it vanishes on the white background) and pure black (use #1c1c1c to #2a2a2a). Use small procedural DataTextures for visible patterns (wood grain, fabric, rust, print) when they matter. Keep parts opaque unless the photo shows them transparent. Glass/clear plastic: transparent: true with opacity 0.35-0.6, a visible tint and visible edges or rims (do not use transmission; it renders very slowly).
- Keep surfaces closed; avoid thin floating planes, z-fighting and parts poking through each other.
- Wheels turn with their axle: for a vehicle shown from the side (length along X, axles along Z) tyres keep the default TorusGeometry orientation and CylinderGeometry hubs need rotation.x = Math.PI / 2; for a vehicle facing +Z (axles along X) tyres need rotation.y = Math.PI / 2 and hubs rotation.z = Math.PI / 2."""

GEN_SYSTEM = ("You are an expert technical artist who rebuilds objects from a single reference photo as procedural Three.js models.\n\n"
              + JUDGING + "\n\n" + CRAFT + "\n\n" + RULES
              + "\n\nDetail: write a thorough module, about 6,000-8,000 tokens of code. Spend the length on what the photo shows: "
    "every distinct part, accurate profiles and proportions, bevels, rims, seams and panel lines, buttons, keys, screws, "
    "holes, feet and hinges, and painted or printed patterns (procedural DataTextures or thin surface geometry). "
    "Use helper functions and loops so the length goes into detail, not repetition.")

GEN_USER = "Reference photo attached. Write the complete Three.js module for this object. Output only the JavaScript."

REFINE_USER = """Attached: (1) the reference photo, (2) a 2x2 sheet of renders of your current module on white: exactly the judge's four cameras: top-left from 30 degrees right of front, top-right from 30 degrees left of front, bottom-left from slightly below the front, bottom-right from above the front.
Compare them with the photo. List to yourself what already matches the photo (keep it unchanged) and the largest visible differences (pose/orientation, shape, proportions, part counts, colors and saturation, labels, missing or wrong parts), then fix only those differences.
Return the complete improved module (only JavaScript).

Current module:
```js
%s
```"""

REPAIR_USER = """Your module was rejected by the validator or renderer:
%s

Fix the problem and return the complete module (only JavaScript).

Module:
```js
%s
```"""

PICK_SYSTEM = "You are a specialized 3D model evaluation system. Always respond with valid JSON only."

PANEL_USER = """Image 1 is the reference photo of the target object. Images 2 to %d each show one candidate 3D model rendered from the same four front viewpoints (30 degrees right, 30 degrees left, slightly below, from above). Candidate k is image k+1.

For every candidate, judge how faithful a 3D reproduction of the reference it is: the right kind of object, overall shape and proportions, pose, distinctive parts and their counts, colors and materials.

Penalty 0-10 per candidate:
0 = Perfect match to reference
3 = Minor issues (slight shape differences, missing small details)
5 = Moderate issues (wrong style, significant details missing, wrong colors on key parts)
7 = Major issues (wrong category but related)
10 = Completely wrong object

Output JSON only: {"penalties": [<one number per candidate, in order>]}"""


GEN_USER_ALT = ("Reference photo attached. Write the complete Three.js module for this object. Start from the proportions: "
                "measure the width, height and depth of every major part relative to the whole object and write them as "
                "named constants, then build every part from them. Output only the JavaScript.")


STRUCTURE_CHECK = ("Before changing anything, go over the photo part by part and check the model against it: the "
                   "overall width : height : depth, every part's shape, size and position, and the exact count of every "
                   "repeated part (legs, handles, cushions, petals, rings, spokes, buttons). Name the structure that makes "
                   "the object recognisable (for example X-shaped folding legs, two moulded side handles, thin double "
                   "rings, plump rolled arms) and make sure the model has that structure and not a simpler substitute.")
FINAL_REFINE_USER = REFINE_USER.replace("Return the complete improved module",
                                        STRUCTURE_CHECK + "\nReturn the complete improved module", 1)


JUDGE_SYSTEM = (
    "You are a specialized 3D model evaluation system.\n"
    "Analyze visual quality and prompt adherence with expert precision.\n"
    "Always respond with valid JSON only."
)
JUDGE_USER = (
    "You see two 3D models rendered from {angle_desc}.\n"
    "The reference image shows the target object.\n\n"
    "Which model is a more faithful 3D reproduction of the reference?\n\n"
    "Penalty 0-10:\n"
    "0 = Perfect match to reference\n"
    "3 = Minor issues (slight shape differences, missing small details)\n"
    "5 = Moderate issues (wrong style, significant details missing)\n"
    "7 = Major issues (wrong category but related, e.g. chair vs stool)\n"
    "10 = Completely wrong object\n\n"
    'Output: {{"penalty_1": <0-10>, "penalty_2": <0-10>, "issues": "<brief>"}}'
)
JUDGE_VIEWS = ((30, 0, "slightly left of the front"), (330, 0, "slightly right of the front"),
               (0, 15, "the front, from slightly below"), (0, -30, "the front, from slightly above"))


EXTRA_REFINES = (
    "Attached: (1) the reference photo, (2) a 2x2 sheet of renders of your current module on white: exactly the judge's four cameras: top-left from 30 degrees right of front, top-right from 30 degrees left of front, bottom-left from slightly below the front, bottom-right from above the front.\nCompare them with the photo. List to yourself what already matches the photo (keep it unchanged) and the largest visible differences (pose/orientation, shape, proportions, part counts, colors and saturation, labels, missing or wrong parts), then fix only those differences.\nReturn the complete improved module (only JavaScript).\n\nCurrent module:\n```js\n%s\n```",
    "Attached: (1) the reference photo, (2) a 2x2 sheet of renders of your current module on white: exactly the judge's four cameras: top-left from 30 degrees right of front, top-right from 30 degrees left of front, bottom-left from slightly below the front, bottom-right from above the front.\nCompare them with the photo. List to yourself what already matches the photo (keep it unchanged) and the largest visible differences (pose/orientation, shape, proportions, part counts, colors and saturation, labels, missing or wrong parts), then fix only those differences.\nReturn the complete improved module (only JavaScript).\n\nCurrent module:\n```js\n%s\n```",
)
