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
  <title>Programme 3D Gantt</title>
  <style>
    :root {{
      --bg-a: #11233f;
      --bg-b: #1a1f44;
      --bg-c: #2b4a75;
      --panel: rgba(10, 16, 29, 0.8);
      --panel-border: rgba(180, 210, 255, 0.24);
      --text: #e9f1ff;
      --muted: #9bb0cc;
      --critical: #ff5e5e;
      --near: #ffbe56;
      --normal: #72c6ff;
      --completed: #78f29d;
      --summary: #a0adbd;
      --baseline: #c5d6ee;
      --bottleneck: #ff47b3;
    }}

    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      height: 100%;
      overflow: hidden;
      background: radial-gradient(circle at 20% 20%, var(--bg-c), var(--bg-a) 45%, #08101d 100%);
      color: var(--text);
      font-family: \"Segoe UI\", Tahoma, Geneva, Verdana, sans-serif;
    }}

    #view {{ position: fixed; inset: 0; }}
    #hud {{
      position: fixed;
      top: 14px;
      left: 14px;
      width: 390px;
      max-height: calc(100% - 28px);
      overflow: auto;
      padding: 14px;
      border-radius: 14px;
      background: var(--panel);
      border: 1px solid var(--panel-border);
      backdrop-filter: blur(8px);
      box-shadow: 0 18px 42px rgba(0, 0, 0, 0.45);
    }}

    h1 {{ margin: 0 0 6px 0; font-size: 18px; }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .row {{ margin-top: 10px; display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; }}
    .chips {{ margin-top: 10px; display: flex; gap: 6px; flex-wrap: wrap; }}
    .chip {{ padding: 4px 8px; font-size: 11px; border-radius: 999px; border: 1px solid rgba(200,220,255,0.25); color: var(--muted); }}

    input[type=\"search\"], select {{
      width: 100%;
      margin-top: 10px;
      border-radius: 8px;
      border: 1px solid rgba(190,220,255,0.3);
      background: rgba(255,255,255,0.06);
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

    #tooltip {{
      position: fixed;
      pointer-events: none;
      display: none;
      padding: 8px 10px;
      border-radius: 8px;
      background: rgba(0, 0, 0, 0.82);
      color: white;
      font-size: 12px;
      max-width: 420px;
      border: 1px solid rgba(255,255,255,0.2);
      z-index: 30;
    }}

    #selection {{ margin-top: 12px; font-size: 12px; line-height: 1.45; }}
    .legend {{ margin-top: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px; }}
    .swatch {{ width: 11px; height: 11px; border-radius: 50%; display: inline-block; margin-right: 6px; }}
  </style>
</head>
<body>
  <div id=\"view\"></div>
  <div id=\"tooltip\"></div>

  <aside id=\"hud\">
    <h1>Programme 3D Gantt</h1>
    <div class=\"muted\">Deterministic schedule terrain with float, cost, and bottleneck overlays</div>

    <input id=\"search\" type=\"search\" placeholder=\"Search task name, ID, or WBS...\" />

    <div class=\"row\">
      <div class=\"muted\">Z axis</div>
      <select id=\"zMode\">
        <option value=\"float\">float</option>
        <option value=\"cost\">cost</option>
        <option value=\"work\">work</option>
        <option value=\"bottleneck\">bottleneck_score</option>
        <option value=\"baseline\">baseline_variance</option>
      </select>
    </div>

    <div class=\"chips\">
      <label class=\"chip\"><input id=\"showDependencies\" type=\"checkbox\" checked /> dependencies</label>
      <label class=\"chip\"><input id=\"showBaseline\" type=\"checkbox\" checked /> baseline</label>
      <label class=\"chip\"><input id=\"criticalOnly\" type=\"checkbox\" /> critical only</label>
      <label class=\"chip\"><input id=\"showBottlenecks\" type=\"checkbox\" checked /> bottlenecks</label>
    </div>

    <div class=\"row\">
      <button id=\"cameraIso\" type=\"button\">Isometric</button>
      <button id=\"cameraFront\" type=\"button\">Front</button>
      <button id=\"cameraTop\" type=\"button\">Top</button>
    </div>

    <div class=\"legend\">
      <div><span class=\"swatch\" style=\"background:var(--critical)\"></span>Critical</div>
      <div><span class=\"swatch\" style=\"background:var(--near)\"></span>Near Critical</div>
      <div><span class=\"swatch\" style=\"background:var(--normal)\"></span>Normal</div>
      <div><span class=\"swatch\" style=\"background:var(--completed)\"></span>Completed</div>
      <div><span class=\"swatch\" style=\"background:var(--summary)\"></span>Summary</div>
      <div><span class=\"swatch\" style=\"background:var(--baseline)\"></span>Baseline</div>
    </div>

    <div id=\"selection\" class=\"muted\">Click a task for details.</div>
  </aside>

  <script>
{three_js_source}
  </script>
  <script>
{orbit_controls_source}
  </script>
  <script>
    const PAYLOAD = {payload_json};

    const container = document.getElementById('view');
    const tooltip = document.getElementById('tooltip');
    const details = document.getElementById('selection');

    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x18263a, 0.0017);

    const camera = new THREE.PerspectiveCamera(58, window.innerWidth / window.innerHeight, 0.1, 20000);
    camera.position.set(240, 220, 300);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    container.appendChild(renderer.domElement);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.minDistance = 30;
    controls.maxDistance = 50000;

    scene.add(new THREE.AmbientLight(0xffffff, 0.86));
    const keyLight = new THREE.DirectionalLight(0xb6d8ff, 1.22);
    keyLight.position.set(220, 380, 240);
    scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight(0x9effde, 0.62);
    rimLight.position.set(-300, -150, -220);
    scene.add(rimLight);

    const stars = [];
    for (let i = 0; i < 650; i += 1) {{
      stars.push((Math.random() - 0.5) * 6000, (Math.random() - 0.5) * 5000, (Math.random() - 0.5) * 6000);
    }}
    const starField = new THREE.Points(
      new THREE.BufferGeometry(),
      new THREE.PointsMaterial({ color: 0xb5d4ff, size: 1.2, transparent: true, opacity: 0.5 })
    );
    starField.geometry.setAttribute('position', new THREE.Float32BufferAttribute(stars, 3));
    scene.add(starField);

    const tasks = PAYLOAD.tasks || [];
    const deps = PAYLOAD.dependencies || [];

    function parseDateSafe(value) {{
      if (!value) return null;
      if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
      const text = String(value).trim();
      if (!text) return null;

      // Prefer ISO-like forms first.
      const isoCandidate = text.length >= 10 ? text.slice(0, 10) : text;
      const isoDate = new Date(isoCandidate + 'T00:00:00');
      if (!Number.isNaN(isoDate.getTime())) return isoDate;

      // Fallback for dd/mm/yyyy and mm/dd/yyyy-like values, optionally with time text.
      const m = text.match(/(\\d{{1,2}})\\/(\\d{{1,2}})\\/(\\d{{2,4}})/);
      if (m) {{
        const a = Number(m[1]);
        const b = Number(m[2]);
        const yRaw = Number(m[3]);
        const y = yRaw < 100 ? (2000 + yRaw) : yRaw;

        const dayFirst = new Date(y, b - 1, a);
        if (!Number.isNaN(dayFirst.getTime()) && dayFirst.getDate() === a && dayFirst.getMonth() === (b - 1)) {{
          return dayFirst;
        }}

        const monthFirst = new Date(y, a - 1, b);
        if (!Number.isNaN(monthFirst.getTime()) && monthFirst.getDate() === b && monthFirst.getMonth() === (a - 1)) {{
          return monthFirst;
        }}
      }}

      const fallback = new Date(text);
      return Number.isNaN(fallback.getTime()) ? null : fallback;
    }}

    const startDate = parseDateSafe(PAYLOAD.timeAxis.start) || new Date();
    const finishDate = parseDateSafe(PAYLOAD.timeAxis.finish) || startDate;
    const totalDays = Math.max(1, (finishDate - startDate) / (1000 * 60 * 60 * 24));

    const laneHeight = 18;
    const laneThickness = 3.2;
    const laneDepth = 3.4;
    const trackDepthStep = 4.8;
    const desiredTimelineSpan = 1200;
    const xScale = Math.min(4.2, Math.max(0.18, desiredTimelineSpan / totalDays));
    const zScale = 38;
    let fittedDistance = 340;

    const idToState = new Map();
    const meshList = [];
    const edgeList = [];

    const depGroup = new THREE.Group();
    scene.add(depGroup);
    const baselineGroup = new THREE.Group();
    scene.add(baselineGroup);
    const labelGroup = new THREE.Group();
    scene.add(labelGroup);

    function xForDate(isoDate) {{
      const d = parseDateSafe(isoDate) || startDate;
      const dayOffset = (d - startDate) / (1000 * 60 * 60 * 24);
      const safeOffset = Number.isFinite(dayOffset) ? dayOffset : 0;
      return (safeOffset - totalDays / 2) * xScale;
    }}

    function barColor(task) {{
      if (task.is_summary) return 0xa0adbd;
      if (safeNumber(task.percent_complete, 0) >= 100) return 0x78f29d;
      if (task.is_critical) return 0xff5e5e;
      if (task.is_near_critical) return 0xffbe56;
      return 0x72c6ff;
    }}

    function safeNumber(value, fallback = 0) {{
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : fallback;
    }}

    function valueForMode(task, mode) {{
      if (mode === 'cost') return Math.max(0, safeNumber(task.cost, 0));
      if (mode === 'work') return Math.max(0, safeNumber(task.work, 0));
      if (mode === 'bottleneck') return Math.max(0, safeNumber(task.bottleneck_score, 0));
      if (mode === 'baseline') return Math.abs(safeNumber(task.finish_variance_days, 0));
      return Math.max(0, safeNumber(task.total_float_days, 0));
    }}

    function normaliseValues(mode) {{
      const raw = tasks.map(task => valueForMode(task, mode));
      const finiteRaw = raw.map(value => Number.isFinite(value) ? value : 0);
      const maxV = Math.max(...finiteRaw, 1);
      return finiteRaw.map(value => value / maxV);
    }}

    function shortTaskText(task) {{
      const idText = String(task.id || task.unique_id || '').trim();
      const labelText = String(task.label || '').trim();
      if (!labelText) return idText || 'Task';
      const compact = labelText.length > 26 ? `${labelText.slice(0, 23)}...` : labelText;
      return idText ? `${idText}: ${compact}` : compact;
    }}

    function createLabelSprite(text, barWidth) {{
      const canvas = document.createElement('canvas');
      const width = 768;
      const height = 128;
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) return null;

      ctx.fillStyle = 'rgba(7, 12, 20, 0.78)';
      ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = 'rgba(185, 215, 255, 0.82)';
      ctx.lineWidth = 4;
      ctx.strokeRect(2, 2, width - 4, height - 4);

      ctx.font = '700 44px Segoe UI, Tahoma, sans-serif';
      ctx.fillStyle = '#f1f7ff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, width / 2, height / 2);

      const texture = new THREE.CanvasTexture(canvas);
      texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
      texture.needsUpdate = true;

      const material = new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        depthTest: true,
        depthWrite: false,
      });

      const sprite = new THREE.Sprite(material);
      const scaleX = Math.min(78, Math.max(16, barWidth * 0.9));
      sprite.scale.set(scaleX, 4.4, 1);
      return sprite;
    }}

    function computeTaskLayouts(mode) {{
      const normalised = normaliseValues(mode);
      const layouts = tasks.map((task, index) => {{
        const startX = xForDate(task.start || PAYLOAD.timeAxis.start);
        const finishX = xForDate(task.finish || task.start || PAYLOAD.timeAxis.start);
        const level = safeNumber(task.outline_level, 0);
        return {{
          task,
          index,
          startX,
          finishX,
          width: Math.max(1.4, Math.abs(finishX - startX)),
          level,
          zMetric: Math.max(0, safeNumber(normalised[index], 0)),
          track: 0,
        }};
      }});

      const byLevel = new Map();
      layouts.forEach(layout => {{
        const key = layout.level;
        if (!byLevel.has(key)) byLevel.set(key, []);
        byLevel.get(key).push(layout);
      }});

      byLevel.forEach(levelLayouts => {{
        levelLayouts.sort((a, b) =>
          (a.startX - b.startX)
          || (a.finishX - b.finishX)
          || (safeNumber(a.task.unique_id, 0) - safeNumber(b.task.unique_id, 0))
        );

        const trackEnds = [];
        levelLayouts.forEach(layout => {{
          let selected = -1;
          for (let track = 0; track < trackEnds.length; track += 1) {{
            if (layout.startX >= trackEnds[track] + 1.5) {{
              selected = track;
              break;
            }}
          }}
          if (selected === -1) {{
            selected = trackEnds.length;
            trackEnds.push(layout.finishX);
          }} else {{
            trackEnds[selected] = Math.max(trackEnds[selected], layout.finishX);
          }}
          layout.track = selected;
        }});
      }});

      return layouts;
    }}

    function buildTaskMeshes() {{
      const mode = document.getElementById('zMode').value;
      const layouts = computeTaskLayouts(mode);

      layouts.forEach(layout => {{
        const task = layout.task;
        const y = (layout.level * laneHeight) - 60;
        const z = (layout.track * trackDepthStep) + (layout.zMetric * zScale);
        const barDepth = laneDepth + layout.zMetric * zScale;

        const geom = new THREE.BoxGeometry(layout.width, laneThickness, barDepth);
        const mat = new THREE.MeshStandardMaterial({
          color: barColor(task),
          transparent: true,
          opacity: safeNumber(task.percent_complete, 0) >= 100 ? 0.72 : 0.95,
          roughness: 0.4,
          metalness: 0.15,
          emissive: safeNumber(task.bottleneck_score, 0) >= 0.7 ? 0xff47b3 : 0x111111,
          emissiveIntensity: safeNumber(task.bottleneck_score, 0) >= 0.7 ? 0.25 : 0.08,
        });

        const mesh = new THREE.Mesh(geom, mat);
        mesh.position.set((layout.startX + layout.finishX) / 2, y, z + barDepth / 2);
        scene.add(mesh);

        const label = createLabelSprite(shortTaskText(task), layout.width);
        if (label) {{
          label.position.set(mesh.position.x, y + 3.1, z + barDepth + 2.2);
          labelGroup.add(label);
        }}

        const state = {{ task, mesh, label, pinned: false }};
        idToState.set(task.unique_id, state);
        meshList.push(state);

        if (task.baseline_start && task.baseline_finish) {{
          const bStart = xForDate(task.baseline_start);
          const bFinish = xForDate(task.baseline_finish);
          const bWidth = Math.max(0.8, Math.abs(bFinish - bStart));
          const bMesh = new THREE.Mesh(
            new THREE.BoxGeometry(bWidth, laneThickness * 0.65, 1.2),
            new THREE.MeshStandardMaterial({ color: 0xc5d6ee, transparent: true, opacity: 0.26 })
          );
          bMesh.position.set((bStart + bFinish) / 2, y - 0.2, z + 0.7);
          baselineGroup.add(bMesh);
          state.baseline = bMesh;
        }}
      }});
    }}

    function buildDependencies() {{
      depGroup.clear();
      edgeList.length = 0;

      deps.forEach(dep => {{
        const source = idToState.get(dep.predecessor_unique_id);
        const target = idToState.get(dep.successor_unique_id);
        if (!source || !target) return;

        const a = source.mesh.position;
        const b = target.mesh.position;
        const midX = (a.x + b.x) * 0.5;
        const lift = 10 + Math.abs(b.x - a.x) * 0.08;
        const curve = new THREE.QuadraticBezierCurve3(
          new THREE.Vector3(a.x, a.y, a.z + 2),
          new THREE.Vector3(midX, Math.max(a.y, b.y) + lift, Math.max(a.z, b.z) + 10),
          new THREE.Vector3(b.x, b.y, b.z + 2),
        );

        const points = curve.getPoints(20);
        const geo = new THREE.BufferGeometry().setFromPoints(points);
        const color = dep.is_critical ? 0xff5e5e : 0x8ea3bb;
        const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.65 }));
        depGroup.add(line);
        edgeList.push({ line, dep });
      }});
    }}

    function buildLanes() {{
      const levels = new Set(tasks.map(task => Number(task.outline_level || 0)));
      const validLevels = Array.from(levels)
        .map(level => safeNumber(level, 0))
        .filter(level => Number.isFinite(level));
      const laneMat = new THREE.LineBasicMaterial({ color: 0x4f5f76, transparent: true, opacity: 0.4 });
      const laneHalfWidth = Math.max(totalDays * xScale * 0.55, 120);
      validLevels.forEach(level => {{
        const y = (level * laneHeight) - 60;
        const geom = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(-laneHalfWidth, y, 0),
          new THREE.Vector3(laneHalfWidth, y, 0),
        ]);
        scene.add(new THREE.Line(geom, laneMat));
      }});
    }}

    function fitCameraToVisible() {{
      const visibleMeshes = meshList.filter(state => state.mesh.visible).map(state => state.mesh);
      if (!visibleMeshes.length) return;

      const bounds = new THREE.Box3();
      visibleMeshes.forEach(mesh => bounds.expandByObject(mesh));

      const center = bounds.getCenter(new THREE.Vector3());
      const size = bounds.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z, 40);
      const fov = THREE.MathUtils.degToRad(camera.fov);
      const fitDistance = (maxDim * 0.72) / Math.tan(fov / 2);
      fittedDistance = Math.max(fitDistance, 120);

      controls.target.copy(center);
      camera.position.set(
        center.x + fittedDistance * 0.85,
        center.y + fittedDistance * 0.62,
        center.z + fittedDistance * 0.95
      );
      controls.maxDistance = Math.max(controls.maxDistance, fittedDistance * 8);
      camera.near = Math.max(0.1, fittedDistance / 400);
      camera.far = Math.max(20000, fittedDistance * 20);
      camera.updateProjectionMatrix();
      controls.update();
    }}

    buildLanes();
    buildTaskMeshes();
    buildDependencies();

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    function pickTask(event) {{
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const intersections = raycaster.intersectObjects(meshList.map(state => state.mesh));
      if (!intersections.length) return null;
      const mesh = intersections[0].object;
      return meshList.find(state => state.mesh === mesh) || null;
    }}

    function showDetails(state) {{
      const task = state.task;
      details.innerHTML = `
        <div><strong>${task.label || task.id}</strong></div>
        <div class=\"muted\">ID ${task.id || ''} | WBS ${task.wbs || ''}</div>
        <div>Start: ${task.start || ''}</div>
        <div>Finish: ${task.finish || ''}</div>
        <div>Total float: ${task.total_float_days ?? ''} days</div>
        <div>Cost: ${task.cost ?? ''}</div>
        <div>Bottleneck score: ${task.bottleneck_score ?? 0}</div>
      `;
    }}

    renderer.domElement.addEventListener('mousemove', event => {{
      const state = pickTask(event);
      if (!state) {{
        tooltip.style.display = 'none';
        return;
      }}
      tooltip.style.display = 'block';
      tooltip.style.left = `${event.clientX + 14}px`;
      tooltip.style.top = `${event.clientY + 10}px`;
      tooltip.textContent = `${state.task.label || state.task.id} | float ${state.task.total_float_days}`;
    }});

    renderer.domElement.addEventListener('click', event => {{
      const state = pickTask(event);
      if (!state) return;
      showDetails(state);
      controls.target.lerp(state.mesh.position, 0.35);
    }});

    renderer.domElement.addEventListener('dblclick', event => {{
      const state = pickTask(event);
      if (!state) return;
      state.pinned = !state.pinned;
      state.mesh.material.wireframe = state.pinned;
    }});

    document.getElementById('showDependencies').addEventListener('change', event => {{
      depGroup.visible = event.target.checked;
    }});

    document.getElementById('showBaseline').addEventListener('change', event => {{
      baselineGroup.visible = event.target.checked;
    }});

    function applyFilters() {{
      const criticalOnly = document.getElementById('criticalOnly').checked;
      const showBottlenecks = document.getElementById('showBottlenecks').checked;
      const search = document.getElementById('search').value.trim().toLowerCase();

      meshList.forEach(state => {{
        const task = state.task;
        let visible = true;
        if (criticalOnly && !task.is_critical) visible = false;

        if (search) {{
          const label = (task.label || '').toLowerCase();
          const id = (task.id || '').toLowerCase();
          const wbs = String(task.wbs || '').toLowerCase();
          if (!(label.includes(search) || id.includes(search) || wbs.includes(search))) visible = false;
        }}

        state.mesh.visible = visible;
        state.mesh.material.emissiveIntensity = showBottlenecks
          ? (safeNumber(task.bottleneck_score, 0) >= 0.7 ? 0.25 : 0.08)
          : 0.02;
        if (state.label) state.label.visible = visible;
        if (state.baseline) state.baseline.visible = visible && baselineGroup.visible;
      }});

      fitCameraToVisible();
    }}

    document.getElementById('criticalOnly').addEventListener('change', applyFilters);
    document.getElementById('showBottlenecks').addEventListener('change', applyFilters);
    document.getElementById('search').addEventListener('input', applyFilters);

    document.getElementById('zMode').addEventListener('change', () => window.location.reload());

    document.getElementById('cameraIso').addEventListener('click', () => {{
      const t = controls.target;
      camera.position.set(t.x + fittedDistance * 0.85, t.y + fittedDistance * 0.62, t.z + fittedDistance * 0.95);
    }});
    document.getElementById('cameraFront').addEventListener('click', () => {{
      const t = controls.target;
      camera.position.set(t.x, t.y, t.z + fittedDistance * 1.2);
    }});
    document.getElementById('cameraTop').addEventListener('click', () => {{
      const t = controls.target;
      camera.position.set(t.x, t.y + fittedDistance * 1.15, t.z);
    }});

    window.addEventListener('resize', () => {{
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    }});

    applyFilters();

    function animate() {{
      requestAnimationFrame(animate);
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


def build_gantt_html(payload: dict[str, object]) -> str:
  payload_json = json.dumps(payload, ensure_ascii=False)
  # Avoid str.format on the full template because JavaScript object literals
  # (for example: { antialias: true }) are valid content but invalid format fields.
  template = HTML_TEMPLATE.replace("{{", "{").replace("}}", "}")
  template = template.replace("{three_js_source}", _load_three_js_source())
  template = template.replace("{orbit_controls_source}", _load_orbit_controls_source())
  template = template.replace("{payload_json}", payload_json)
  return template
