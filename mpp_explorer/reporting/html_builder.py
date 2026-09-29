from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
THREE_JS_PATH = ASSETS_DIR / "three.min.js"
ORBIT_CONTROLS_PATH = ASSETS_DIR / "OrbitControls.js"

HTML_TEMPLATE = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Programme 3D Visualisation</title>
  <style>
    :root {{
      --bg-a: #09111f;
      --bg-b: #120e2b;
      --bg-c: #1b2b46;
      --panel: rgba(10, 16, 29, 0.78);
      --panel-border: rgba(180, 210, 255, 0.22);
      --text: #e9f1ff;
      --muted: #9bb0cc;
      --accent: #49d4ff;
      --task: #72c6ff;
      --project: #ffc857;
      --resource: #78f29d;
      --dep: #ff8c66;
      --hier: #7f90ff;
      --assign: #60e6b9;
      --contains: #8ea3bb;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; height: 100%; overflow: hidden; background: radial-gradient(circle at 20% 20%, var(--bg-c), var(--bg-a) 45%, #05080f 100%); color: var(--text); font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif; }}
    #view {{ position: fixed; inset: 0; }}
    #hud {{
      position: fixed;
      top: 14px;
      left: 14px;
      width: 360px;
      max-height: calc(100% - 28px);
      overflow: auto;
      padding: 14px;
      border-radius: 14px;
      background: var(--panel);
      border: 1px solid var(--panel-border);
      backdrop-filter: blur(8px);
      box-shadow: 0 18px 42px rgba(0, 0, 0, 0.45);
    }}
    h1 {{ margin: 0 0 6px 0; font-size: 18px; letter-spacing: 0.4px; }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .row {{ margin-top: 10px; display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; }}
    .legend {{ margin-top: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px; }}
    .swatch {{ width: 11px; height: 11px; border-radius: 50%; display: inline-block; margin-right: 6px; }}
    input[type=\"search\"] {{
      width: 100%;
      margin-top: 10px;
      border-radius: 8px;
      border: 1px solid rgba(190, 220, 255, 0.3);
      background: rgba(255, 255, 255, 0.06);
      color: var(--text);
      padding: 9px 10px;
      outline: none;
    }}
    button {{
      border: 0;
      border-radius: 8px;
      padding: 8px 10px;
      background: linear-gradient(135deg, #2f7eff, #41b5ff);
      color: white;
      cursor: pointer;
      font-weight: 600;
    }}
    button:hover {{ filter: brightness(1.07); }}
    .chips {{ margin-top: 10px; display: flex; gap: 6px; flex-wrap: wrap; }}
    .chip {{ padding: 4px 8px; font-size: 11px; border-radius: 999px; border: 1px solid rgba(200, 220, 255, 0.25); color: var(--muted); }}
    #tooltip {{
      position: fixed;
      pointer-events: none;
      display: none;
      padding: 8px 10px;
      border-radius: 8px;
      background: rgba(0, 0, 0, 0.82);
      color: white;
      font-size: 12px;
      max-width: 360px;
      border: 1px solid rgba(255, 255, 255, 0.2);
      z-index: 30;
    }}
    #selection {{ margin-top: 12px; font-size: 12px; line-height: 1.45; }}
    .kv {{ display: grid; grid-template-columns: 110px 1fr; gap: 8px; margin-bottom: 3px; }}
    .key {{ color: var(--muted); }}
  </style>
</head>
<body>
  <div id=\"view\"></div>
  <div id=\"tooltip\"></div>

  <aside id=\"hud\">
    <h1>Programme 3D Map</h1>
    <div class=\"muted\">Interactive structure, dependencies, and resource assignment network</div>

    <input id=\"search\" type=\"search\" placeholder=\"Search task, resource, or ID...\" />
    <div class=\"row\">
      <div class=\"muted\">Auto-layout</div>
      <button id=\"stabilise\" type=\"button\">Stabilise</button>
    </div>

    <div class=\"chips\">
      <label class=\"chip\"><input id=\"showHierarchy\" type=\"checkbox\" checked /> hierarchy</label>
      <label class=\"chip\"><input id=\"showDependency\" type=\"checkbox\" checked /> dependency</label>
      <label class=\"chip\"><input id=\"showAssignment\" type=\"checkbox\" checked /> assignment</label>
      <label class=\"chip\"><input id=\"showContains\" type=\"checkbox\" checked /> contains</label>
    </div>

    <div class=\"legend\">
      <div><span class=\"swatch\" style=\"background:var(--project)\"></span>Project Node</div>
      <div><span class=\"swatch\" style=\"background:var(--task)\"></span>Task Node</div>
      <div><span class=\"swatch\" style=\"background:var(--resource)\"></span>Resource Node</div>
      <div><span class=\"swatch\" style=\"background:var(--hier)\"></span>Hierarchy Edge</div>
      <div><span class=\"swatch\" style=\"background:var(--dep)\"></span>Dependency Edge</div>
      <div><span class=\"swatch\" style=\"background:var(--assign)\"></span>Assignment Edge</div>
    </div>

    <div id=\"selection\" class=\"muted\">Click a node for details.</div>
  </aside>

  <script>
{three_js_source}
  </script>
  <script>
{orbit_controls_source}
  </script>
  <script>
    const GRAPH = {graph_json};
    const container = document.getElementById('view');
    const tooltip = document.getElementById('tooltip');
    const details = document.getElementById('selection');
    const searchBox = document.getElementById('search');

    const edgeToggles = {{
      hierarchy: document.getElementById('showHierarchy'),
      dependency: document.getElementById('showDependency'),
      assignment: document.getElementById('showAssignment'),
      contains: document.getElementById('showContains'),
    }};

    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x04070d, 0.0028);

    const camera = new THREE.PerspectiveCamera(58, window.innerWidth / window.innerHeight, 0.1, 8000);
    camera.position.set(0, 120, 360);

    const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.outputEncoding = THREE.sRGBEncoding;
    container.appendChild(renderer.domElement);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.minDistance = 30;
    controls.maxDistance = 2000;

    const ambient = new THREE.AmbientLight(0xffffff, 0.58);
    scene.add(ambient);

    const keyLight = new THREE.DirectionalLight(0x9cc6ff, 1.0);
    keyLight.position.set(200, 320, 180);
    scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight(0x88ffd7, 0.45);
    rimLight.position.set(-220, -120, -180);
    scene.add(rimLight);

    const starField = new THREE.Points(
      new THREE.BufferGeometry(),
      new THREE.PointsMaterial({{ color: 0x95bfff, size: 1.2, transparent: true, opacity: 0.55 }})
    );
    const stars = [];
    for (let i = 0; i < 1500; i += 1) {{
      stars.push((Math.random() - 0.5) * 4000, (Math.random() - 0.5) * 3200, (Math.random() - 0.5) * 4000);
    }}
    starField.geometry.setAttribute('position', new THREE.Float32BufferAttribute(stars, 3));
    scene.add(starField);

    const kindColor = {{
      project: 0xffc857,
      task: 0x72c6ff,
      resource: 0x78f29d,
    }};

    const edgeColor = {{
      hierarchy: 0x7f90ff,
      dependency: 0xff8c66,
      assignment: 0x60e6b9,
      contains: 0x8ea3bb,
    }};

    const nodeState = GRAPH.nodes.map((node, index) => {{
      const radius = node.kind === 'project' ? 11 : node.kind === 'resource' ? 6.2 : 4.7;
      const geometry = new THREE.SphereGeometry(radius, 22, 22);
      const material = new THREE.MeshStandardMaterial({{
        color: kindColor[node.kind] ?? 0xffffff,
        metalness: 0.28,
        roughness: 0.36,
        emissive: kindColor[node.kind] ?? 0x222222,
        emissiveIntensity: 0.12,
      }});
      const mesh = new THREE.Mesh(geometry, material);

      const spread = Math.cbrt(GRAPH.nodes.length) * 70;
      mesh.position.set(
        (Math.random() - 0.5) * spread,
        (Math.random() - 0.5) * spread,
        (Math.random() - 0.5) * spread
      );
      scene.add(mesh);

      return {{
        index,
        node,
        mesh,
        velocity: new THREE.Vector3(0, 0, 0),
        pinned: false,
      }};
    }});

    const idToIndex = new Map(nodeState.map((n) => [n.node.id, n.index]));

    const edgeState = [];
    for (const edge of GRAPH.edges) {{
      const sourceIndex = idToIndex.get(edge.source);
      const targetIndex = idToIndex.get(edge.target);
      if (sourceIndex === undefined || targetIndex === undefined) continue;

      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(new Array(6).fill(0), 3));
      const material = new THREE.LineBasicMaterial({{
        color: edgeColor[edge.kind] ?? 0xffffff,
        transparent: true,
        opacity: edge.kind === 'contains' ? 0.22 : 0.52,
      }});
      const line = new THREE.Line(geometry, material);
      scene.add(line);

      edgeState.push({{ edge, sourceIndex, targetIndex, line }});
    }}

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let hovered = null;
    let selected = null;

    function updateEdgeVisibility() {{
      for (const e of edgeState) {{
        const enabled = edgeToggles[e.edge.kind]?.checked ?? true;
        e.line.visible = enabled;
      }}
    }}

    for (const checkbox of Object.values(edgeToggles)) {{
      checkbox.addEventListener('change', updateEdgeVisibility);
    }}
    updateEdgeVisibility();

    function stabiliseLayout(iterations = 180) {{
      for (let i = 0; i < iterations; i += 1) {{
        simulationStep();
      }}
    }}
    document.getElementById('stabilise').addEventListener('click', () => stabiliseLayout(320));

    function simulationStep() {{
      const repulsion = 9200;
      const spring = 0.0035;
      const damping = 0.88;
      const centerPull = 0.0009;

      for (let i = 0; i < nodeState.length; i += 1) {{
        for (let j = i + 1; j < nodeState.length; j += 1) {{
          const a = nodeState[i];
          const b = nodeState[j];
          const diff = new THREE.Vector3().subVectors(a.mesh.position, b.mesh.position);
          let distSq = diff.lengthSq() + 0.01;
          if (distSq > 240000) continue;
          const force = repulsion / distSq;
          diff.normalize().multiplyScalar(force);
          if (!a.pinned) a.velocity.add(diff);
          if (!b.pinned) b.velocity.sub(diff);
        }}
      }}

      for (const e of edgeState) {{
        if (!e.line.visible) continue;
        const a = nodeState[e.sourceIndex];
        const b = nodeState[e.targetIndex];
        const diff = new THREE.Vector3().subVectors(b.mesh.position, a.mesh.position);
        const dist = Math.max(1, diff.length());

        const targetLength = e.edge.kind === 'dependency' ? 78 : e.edge.kind === 'assignment' ? 66 : 58;
        const stretch = dist - targetLength;
        diff.normalize().multiplyScalar(stretch * spring);

        if (!a.pinned) a.velocity.add(diff);
        if (!b.pinned) b.velocity.sub(diff);
      }}

      for (const state of nodeState) {{
        if (!state.pinned) {{
          state.velocity.addScaledVector(state.mesh.position, -centerPull);
          state.velocity.multiplyScalar(damping);
          state.mesh.position.add(state.velocity);
        }}
      }}
    }}

    function updateLines() {{
      for (const e of edgeState) {{
        const a = nodeState[e.sourceIndex].mesh.position;
        const b = nodeState[e.targetIndex].mesh.position;
        const pos = e.line.geometry.attributes.position.array;
        pos[0] = a.x; pos[1] = a.y; pos[2] = a.z;
        pos[3] = b.x; pos[4] = b.y; pos[5] = b.z;
        e.line.geometry.attributes.position.needsUpdate = true;
      }}
    }}

    function nodeSummary(node) {{
      const attrs = node.attributes || {{}};
      return `
        <div class=\"kv\"><div class=\"key\">Kind</div><div>${{node.kind}}</div></div>
        <div class=\"kv\"><div class=\"key\">Label</div><div>${{node.label || ''}}</div></div>
        <div class=\"kv\"><div class=\"key\">ID</div><div>${{node.id}}</div></div>
        <div class=\"kv\"><div class=\"key\">WBS</div><div>${{attrs.wbs || ''}}</div></div>
        <div class=\"kv\"><div class=\"key\">Start</div><div>${{attrs.start || ''}}</div></div>
        <div class=\"kv\"><div class=\"key\">Finish</div><div>${{attrs.finish || ''}}</div></div>
        <div class=\"kv\"><div class=\"key\">Complete</div><div>${{attrs.percent_complete || ''}}</div></div>
      `;
    }}

    function setSelected(state) {{
      selected = state;
      details.innerHTML = state ? nodeSummary(state.node) : '<span class=\"muted\">Click a node for details.</span>';

      for (const n of nodeState) {{
        n.mesh.scale.setScalar(n === state ? 1.4 : 1.0);
        n.mesh.material.emissiveIntensity = n === state ? 0.36 : 0.12;
      }}

      if (state) {{
        const target = state.mesh.position;
        controls.target.lerp(target, 0.35);
      }}
    }}

    function pickNode(event) {{
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(pointer, camera);
      const intersections = raycaster.intersectObjects(nodeState.map((n) => n.mesh));
      if (!intersections.length) return null;

      const mesh = intersections[0].object;
      return nodeState.find((state) => state.mesh === mesh) ?? null;
    }}

    renderer.domElement.addEventListener('mousemove', (event) => {{
      hovered = pickNode(event);
      if (hovered) {{
        tooltip.style.display = 'block';
        tooltip.style.left = `${{event.clientX + 14}}px`;
        tooltip.style.top = `${{event.clientY + 10}}px`;
        tooltip.textContent = `${{hovered.node.label || hovered.node.id}} (${{hovered.node.kind}})`;
      }} else {{
        tooltip.style.display = 'none';
      }}
    }});

    renderer.domElement.addEventListener('dblclick', (event) => {{
      const picked = pickNode(event);
      if (!picked) return;
      picked.pinned = !picked.pinned;
      picked.mesh.material.wireframe = picked.pinned;
    }});

    renderer.domElement.addEventListener('click', (event) => {{
      const picked = pickNode(event);
      setSelected(picked);
    }});

    searchBox.addEventListener('input', () => {{
      const q = searchBox.value.trim().toLowerCase();
      if (!q) {{
        setSelected(null);
        return;
      }}
      const found = nodeState.find((n) => {{
        const label = (n.node.label || '').toLowerCase();
        const id = (n.node.id || '').toLowerCase();
        const taskId = String(n.node.attributes?.id || '').toLowerCase();
        const wbs = String(n.node.attributes?.wbs || '').toLowerCase();
        return label.includes(q) || id.includes(q) || taskId.includes(q) || wbs.includes(q);
      }});
      if (found) setSelected(found);
    }});

    window.addEventListener('resize', () => {{
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    }});

    stabiliseLayout(260);

    function animate() {{
      requestAnimationFrame(animate);
      simulationStep();
      updateLines();
      controls.update();
      renderer.render(scene, camera);
    }}
    animate();
  </script>
</body>
</html>
"""


@lru_cache(maxsize=1)
def _load_three_js_source() -> str:
    return _load_asset(THREE_JS_PATH)


@lru_cache(maxsize=1)
def _load_orbit_controls_source() -> str:
    return _load_asset(ORBIT_CONTROLS_PATH)


def _load_asset(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing required asset: {path}. Both three.min.js and OrbitControls.js are expected beside this module in reporting/assets/."
        )
    return path.read_text(encoding="utf-8")


def build_viewer_html(payload: dict) -> str:
    graph_json = json.dumps(payload, ensure_ascii=False)
    return HTML_TEMPLATE.format(
        three_js_source=_load_three_js_source(),
        orbit_controls_source=_load_orbit_controls_source(),
        graph_json=graph_json,
    )
