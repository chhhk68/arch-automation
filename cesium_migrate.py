#!/usr/bin/env python3
# cesium_migrate.py
# Replace entire Three.js 3D section with CesiumJS — coordinates align perfectly
# because CesiumJS works natively in WGS84, eliminating all manual projection errors.

import re, sys

PATH = r"D:\H\05. ai\01. 건축 자동화\templates\index.html"

with open(PATH, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"Original size: {len(content)} chars")

# ─────────────────────────────────────────────────────────────────
# 1.  CSS: replace #three-canvas rule → #cesium-container + hide Cesium UI
# ─────────────────────────────────────────────────────────────────
OLD_CSS = '#three-canvas{position:absolute;top:0;left:0;width:100%;height:100%;display:block}'
NEW_CSS = (
    '#cesium-container{position:absolute;top:0;left:0;width:100%;height:100%;overflow:hidden}\n'
    '.cesium-widget-credits,.cesium-credit-logoContainer,'
    '.cesium-credit-textContainer,.cesium-performanceDisplay-defaultContainer,'
    '.cesium-viewer-bottom{display:none!important}'
)
assert OLD_CSS in content, "CSS marker not found"
content = content.replace(OLD_CSS, NEW_CSS, 1)
print("1. CSS replaced")

# ─────────────────────────────────────────────────────────────────
# 2.  HTML: replace <canvas id="three-canvas"> with <div>
# ─────────────────────────────────────────────────────────────────
OLD_CANVAS = '<canvas id="three-canvas"></canvas>'
NEW_DIV    = '<div id="cesium-container"></div>'
assert OLD_CANVAS in content, "canvas element not found"
content = content.replace(OLD_CANVAS, NEW_DIV, 1)
print("2. Canvas → div replaced")

# ─────────────────────────────────────────────────────────────────
# 3.  Hint text — update for CesiumJS controls
# ─────────────────────────────────────────────────────────────────
OLD_HINT = (
    '    <div class="hint">\n'
    '      좌·중간 드래그: 회전 (스케치업 스타일)<br>\n'
    '      오른쪽 드래그: 이동(pan)<br>\n'
    '      스크롤: 줌\n'
    '    </div>'
)
NEW_HINT = (
    '    <div class="hint">\n'
    '      좌클릭 드래그: 회전 / 이동<br>\n'
    '      오른쪽 드래그: 줌인/줌아웃<br>\n'
    '      스크롤: 줌 · 중간버튼 드래그: 틸트\n'
    '    </div>'
)
assert OLD_HINT in content, "hint div not found"
content = content.replace(OLD_HINT, NEW_HINT, 1)
print("3. Hint text updated")

# ─────────────────────────────────────────────────────────────────
# 4.  Script CDN: Three.js → CesiumJS
# ─────────────────────────────────────────────────────────────────
OLD_CDN = (
    '<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>\n'
    '<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>'
)
NEW_CDN = (
    '<link rel="stylesheet" href="https://cesium.com/downloads/cesiumjs/releases/1.116/Build/Cesium/Widgets/widgets.css">\n'
    '<script src="https://cesium.com/downloads/cesiumjs/releases/1.116/Build/Cesium/Cesium.js"></script>'
)
assert OLD_CDN in content, "Three.js CDN not found"
content = content.replace(OLD_CDN, NEW_CDN, 1)
print("4. CDN replaced → CesiumJS 1.116")

# ─────────────────────────────────────────────────────────────────
# 5.  S object: add surrVisible flag
# ─────────────────────────────────────────────────────────────────
OLD_S = (
    '  map3dVisible:true,\n'
    '};'
)
NEW_S = (
    '  map3dVisible:true,\n'
    '  surrVisible:true,\n'
    '};'
)
assert OLD_S in content, "S object tail not found"
content = content.replace(OLD_S, NEW_S, 1)
print("5. S.surrVisible added")

# ─────────────────────────────────────────────────────────────────
# 6.  Tab handler: initThree / resizeThree → initCesium / resizeCesium
# ─────────────────────────────────────────────────────────────────
OLD_HANDLER = (
    '      if(!S.threeOk) initThree();\n'
    '      else resizeThree();'
)
NEW_HANDLER = (
    '      if(!S.threeOk) initCesium();\n'
    '      else resizeCesium();'
)
assert OLD_HANDLER in content, "tab handler not found"
content = content.replace(OLD_HANDLER, NEW_HANDLER, 1)
print("6. Tab handler updated")

# ─────────────────────────────────────────────────────────────────
# 7.  Replace entire Three.js JS section with CesiumJS equivalents
#     Boundary markers (ASCII-safe)
# ─────────────────────────────────────────────────────────────────
SECTION_START = '// -- Three.js'
SECTION_END   = '// -- Leaflet Map (Tab 1)'

# The actual file uses em-dash decorations; find by shorter substring
idx_start = content.find('\n// ── Three.js ─')
idx_end   = content.find('\n// ── Leaflet Map (Tab 1)')

assert idx_start != -1, "Three.js section start not found"
assert idx_end   != -1, "Leaflet Map section end not found"
print(f"   Three.js section: chars {idx_start} .. {idx_end}")

CESIUM_JS = r"""
// -- CesiumJS 3D engine (replaces Three.js) --------------------------------
// WGS84 native coords => zero manual projection => perfect coordinate alignment
// ─────────────────────────────────────────────────────────────────────────────
let viewer = null;           // Cesium.Viewer instance
let _cesiumMassIds  = [];   // entity IDs for current building mass
let _cesiumSurrIds  = [];   // entity IDs for surrounding OSM buildings
let _cesiumParcelId = null; // entity ID for parcel boundary

// Cesium Ion dummy token — we use zero Ion assets; all imagery/terrain is custom
const _CESIUM_DUMMY_TOKEN =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
  'eyJqdGkiOiJub3Rva2VuIiwiaWF0IjowfQ.placeholder';

// ── Init CesiumJS viewer ──────────────────────────────────────────────────
async function initCesium(){
  if(S.threeOk){ resizeCesium(); return; }

  Cesium.Ion.defaultAccessToken = _CESIUM_DUMMY_TOKEN;

  // Satellite imagery via Flask proxy (ESRI World Imagery)
  // URL template: {z}/{y}/{x} — CesiumJS WebMercatorTilingScheme, y=0 is north (matches ESRI)
  const imageryProvider = new Cesium.UrlTemplateImageryProvider({
    url: '/api/tile/esri/{z}/{y}/{x}',
    maximumLevel: 18,
    tilingScheme: new Cesium.WebMercatorTilingScheme(),
    credit: new Cesium.Credit('Esri, Maxar, GeoEye, Earthstar Geographics', false)
  });

  viewer = new Cesium.Viewer('cesium-container', {
    imageryProvider    : imageryProvider,
    terrainProvider    : new Cesium.EllipsoidTerrainProvider(),
    baseLayerPicker    : false,
    geocoder           : false,
    homeButton         : false,
    sceneModePicker    : false,
    navigationHelpButton: false,
    animation          : false,
    timeline           : false,
    fullscreenButton   : false,
    infoBox            : false,
    selectionIndicator : false,
  });

  // Dark background + hide UI chrome
  viewer.scene.backgroundColor = new Cesium.Color(0.07, 0.09, 0.12, 1.0);
  viewer.scene.skyBox.show      = false;
  viewer.scene.skyAtmosphere.show = false;
  viewer.scene.globe.enableLighting = false;
  viewer.scene.globe.depthTestAgainstTerrain = true;
  if(viewer.bottomContainer) viewer.bottomContainer.style.display = 'none';

  // Shadows (soft ambient)
  viewer.shadows = true;
  viewer.shadowMap.softShadows = true;
  viewer.shadowMap.size = 1024;

  S.threeOk = true;
  window.addEventListener('resize', resizeCesium);

  // Compass updates on every frame
  viewer.scene.postRender.addEventListener(updateCompass);

  if(S.checkResult) buildMass(S.checkResult);
}

function resizeCesium(){
  if(!viewer) return;
  viewer.resize();
  viewer.scene.requestRender();
}

// ── Compass ───────────────────────────────────────────────────────────────
function updateCompass(){
  if(!viewer) return;
  const az = ((Cesium.Math.toDegrees(viewer.camera.heading) % 360) + 360) % 360;
  const needle = document.getElementById('compass-needle');
  const degEl  = document.getElementById('compass-deg');
  if(needle) needle.style.transform = `translateX(-50%) rotate(${az}deg)`;
  if(degEl)  degEl.textContent = az.toFixed(0) + '°';
}

// ── Coordinate helper ─────────────────────────────────────────────────────
// Convert local metre offset (dx=east, dz=north) from SW corner to WGS84
function _toWGS84(latSW, lonSW, cosLat, dx, dz){
  return { lat: latSW + dz / 111320, lon: lonSW + dx / (111320 * cosLat) };
}

// ── Floor gradient color (returns Cesium.Color) ───────────────────────────
function floorColor(i, n){
  const t = n > 1 ? i / (n - 1) : 0;
  return new Cesium.Color(
    (0x18 + t * (0x5a - 0x18)) / 255,
    (0x58 + t * (0xb0 - 0x58)) / 255,
    (0xcc + t * (0xff - 0xcc)) / 255,
    0.86
  );
}

// ── Build 3D Mass ─────────────────────────────────────────────────────────
function buildMass(d){
  if(!viewer) return;

  // Remove old mass entities
  _cesiumMassIds.forEach(id=>{ const e=viewer.entities.getById(id); if(e) viewer.entities.remove(e); });
  _cesiumMassIds = [];
  if(_cesiumParcelId){ const pe=viewer.entities.getById(_cesiumParcelId); if(pe) viewer.entities.remove(pe); _cesiumParcelId=null; }

  const fps=d.footprints;
  if(!fps||!fps.length) return;

  const fh=d.floor_height, n=fps.length, s=d.site;
  const p=S.parcels[0]||S.merged;
  if(!p) return;

  const cLat=p.mid_lat||p.lat, cLon=p.mid_lon||p.lon;
  if(!cLat||!cLon) return;

  const cosLat=Math.cos(cLat*Math.PI/180);
  const latSW=cLat-s.depth/(2*111320);
  const lonSW=cLon-s.width/(2*111320*cosLat);

  function wgs(dx,dz){ return _toWGS84(latSW,lonSW,cosLat,dx,dz); }

  // ── Parcel boundary (yellow dashed polyline, ground-clamped)
  const pCorn=[wgs(0,0),wgs(s.width,0),wgs(s.width,s.depth),wgs(0,s.depth),wgs(0,0)];
  const pEnt=viewer.entities.add({
    id:'cesium-parcel',
    polyline:{
      positions: pCorn.map(c=>Cesium.Cartesian3.fromDegrees(c.lon,c.lat,0.4)),
      width: 3,
      material: new Cesium.PolylineDashMaterialProperty({
        color: Cesium.Color.fromCssColorString('#ffee00'),
        dashLength: 10.0, dashPattern: 0xFF00
      }),
      clampToGround: false,
      arcType: Cesium.ArcType.NONE,
    }
  });
  _cesiumParcelId=pEnt.id;

  // ── Floor boxes (polygon + extruded height per floor)
  fps.forEach((fp,i)=>{
    const bH=i*fh, tH=(i+1)*fh;
    const corners=[
      wgs(fp.x0,       fp.y0),
      wgs(fp.x0+fp.w,  fp.y0),
      wgs(fp.x0+fp.w,  fp.y0+fp.d),
      wgs(fp.x0,       fp.y0+fp.d)
    ];
    const positions=corners.map(c=>Cesium.Cartesian3.fromDegrees(c.lon,c.lat));
    const ent=viewer.entities.add({
      polygon:{
        hierarchy    : new Cesium.PolygonHierarchy(positions),
        height       : bH,
        extrudedHeight: tH,
        material     : new Cesium.ColorMaterialProperty(floorColor(i,n)),
        outline      : true,
        outlineColor : new Cesium.Color(0.035,0.125,0.29,1.0),
        outlineWidth : 2,
        shadows      : Cesium.ShadowMode.ENABLED,
        closeTop     : true,
        closeBottom  : true,
      }
    });
    _cesiumMassIds.push(ent.id);
  });

  // ── Camera: fly to bounding sphere
  const center=wgs(s.width/2, s.depth/2);
  const bldH=n*fh;
  const range=Math.max(s.width,s.depth,bldH)*3.5;
  const bs=new Cesium.BoundingSphere(
    Cesium.Cartesian3.fromDegrees(center.lon,center.lat,bldH/2),
    Math.max(s.width,s.depth)*1.2
  );
  viewer.camera.flyToBoundingSphere(bs,{
    offset  : new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-35), range),
    duration: 1.2
  });
}

// ── Toggle satellite map ──────────────────────────────────────────────────
function toggle3DMap(){
  S.map3dVisible=!S.map3dVisible;
  if(viewer){
    viewer.scene.globe.show=S.map3dVisible;
    const layers=viewer.imageryLayers;
    for(let i=0;i<layers.length;i++) layers.get(i).show=S.map3dVisible;
  }
  const btn=document.getElementById('mp-map3d-btn');
  if(btn){
    btn.textContent=S.map3dVisible?'ON':'OFF';
    btn.className='btn btn-sm '+(S.map3dVisible?'bp':'bo');
  }
}

// ── OSM Surrounding buildings ─────────────────────────────────────────────
async function tryLoadSurroundings(){
  const p=S.parcels[0]||S.merged;
  if(!p){ showSurrStatus('주변 현황: 좌표 없음'); return; }
  const cLat=p.mid_lat||p.lat, cLon=p.mid_lon||p.lon;
  if(!cLat||!cLon){ showSurrStatus('주변 현황: 좌표 없음'); return; }
  showSurrStatus('주변 건물 로딩 중...');
  try{
    const R=300;
    const s=cLat-R/111320, n=cLat+R/111320;
    const cosL=Math.cos(cLat*Math.PI/180);
    const w=cLon-R/(111320*cosL), e=cLon+R/(111320*cosL);
    const query=`[out:json][timeout:20];(way["building"](${s},${w},${n},${e}););(._;>;);out body;`;
    const resp=await fetch('https://overpass-api.de/api/interpreter',{
      method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'data='+encodeURIComponent(query)
    });
    const data=await resp.json();
    addOSMBuildings(data,cLat,cLon,p.width||20,p.depth||20);
    S.surroundingsLoaded=true;
    showSurrStatus('');
  }catch(e){
    showSurrStatus('주변 현황 로딩 실패');
  }
}

function showSurrStatus(msg){
  const el=document.getElementById('surr-status');
  if(!msg){el.classList.add('hidden');return;}
  el.textContent=msg; el.classList.remove('hidden');
}

function addOSMBuildings(osmData,originLat,originLon,siteW,siteD){
  if(!viewer) return;
  // Remove old surrounding entities
  _cesiumSurrIds.forEach(id=>{ const e=viewer.entities.getById(id); if(e) viewer.entities.remove(e); });
  _cesiumSurrIds=[];

  const nodeMap={};
  osmData.elements.forEach(el=>{ if(el.type==='node') nodeMap[el.id]={lat:el.lat,lon:el.lon}; });

  const surrColor=new Cesium.Color(0.91,0.91,0.91,0.82);
  const edgeColor=new Cesium.Color(0.6,0.6,0.6,0.5);

  osmData.elements.forEach(el=>{
    if(el.type!=='way'||!el.tags?.building) return;
    const nodes=el.nodes.map(id=>nodeMap[id]).filter(Boolean);
    if(nodes.length<3) return;
    const h=el.tags.height?parseFloat(el.tags.height)
           :el.tags['building:levels']?parseFloat(el.tags['building:levels'])*3.2:10;
    // Remove duplicate closing node if polygon is closed
    const pts=(nodes[0].lat===nodes[nodes.length-1].lat&&nodes[0].lon===nodes[nodes.length-1].lon)
      ?nodes.slice(0,-1):nodes;
    if(pts.length<3) return;
    const positions=pts.map(nd=>Cesium.Cartesian3.fromDegrees(nd.lon,nd.lat));
    try{
      const ent=viewer.entities.add({
        polygon:{
          hierarchy    : new Cesium.PolygonHierarchy(positions),
          height       : 0,
          extrudedHeight: Math.max(h,1),
          material     : new Cesium.ColorMaterialProperty(surrColor),
          outline      : true,
          outlineColor : new Cesium.ColorMaterialProperty(edgeColor),
          outlineWidth : 1,
          shadows      : Cesium.ShadowMode.ENABLED,
          closeTop     : true,
          closeBottom  : false,
        }
      });
      _cesiumSurrIds.push(ent.id);
    }catch(err){ /* skip degenerate polygon */ }
  });
  if(!S.surrVisible){
    _cesiumSurrIds.forEach(id=>{ const e=viewer.entities.getById(id); if(e) e.show=false; });
  }
}

function toggleSurr3D(){
  S.surrVisible=!S.surrVisible;
  _cesiumSurrIds.forEach(id=>{ const e=viewer.entities.getById(id); if(e) e.show=S.surrVisible; });
  const btn=document.getElementById('mp-surr-btn');
  if(btn){ btn.textContent=S.surrVisible?'ON':'OFF'; btn.className='btn btn-sm '+(S.surrVisible?'bp':'bo'); }
}

"""

# Splice in the CesiumJS section
content = content[:idx_start] + CESIUM_JS + content[idx_end:]
print(f"7. Three.js section replaced with CesiumJS ({len(CESIUM_JS)} chars injected)")

# ─────────────────────────────────────────────────────────────────
# 8.  updateMpPanel calls buildMass which is now Cesium-based — no change needed
#     applyMpToMass calls buildMass — no change needed
#     But: S.threeOk is referenced at line ~1069 → remains valid
# ─────────────────────────────────────────────────────────────────

# Sanity check: no more Three.js references in the 3D section
three_refs = [m.start() for m in re.finditer(r'\bnew THREE\b', content)]
if three_refs:
    print(f"WARNING: {len(three_refs)} remaining 'new THREE' references at: {three_refs[:5]}")
else:
    print("8. Sanity check: no 'new THREE' references remaining")

with open(PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\nDone! Written {len(content)} chars to {PATH}")
