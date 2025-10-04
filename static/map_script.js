// map_script.js — clean, single implementation

function getInitialView(){
  try{
    const s = localStorage.getItem('mapDefaultView');
    if(s){ const o = JSON.parse(s); if(o && isFinite(o.lat) && isFinite(o.lon)) return {lat:o.lat, lon:o.lon, zoom:o.zoom||6}; }
  }catch(e){}
  return {lat:51.5014, lon:-0.1419, zoom:6};
}

const iv = getInitialView();
// disable the default leaflet zoom control — we'll provide a custom floating control
const map = L.map('map', { zoomControl: false }).setView([iv.lat, iv.lon], iv.zoom);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors' }).addTo(map);

let blastLayers = [];
let latestRequestId = 0;
let activeController = null;

function calcEnergyAndRingsLocal(diameter_m, velocity_kms, density){
  const r = diameter_m/2;
  const vol = (4/3)*Math.PI*Math.pow(r,3);
  const mass = density*vol;
  const v = velocity_kms*1000;
  const E = 0.5*mass*v*v;
  const mt = E/4.184e15;
  const r20km = 1.2*Math.cbrt(mt);
  const r5km  = 3.2*Math.cbrt(mt);
  const r1km  = 7.0*Math.cbrt(mt);
  return {E, mt, rings_m: [r20km*1000, r5km*1000, r1km*1000]};
}

async function calcEnergyAndRings(diameter_m, velocity_kms, density, signal){
  try{
    const url = `/api/energy?diameter_m=${encodeURIComponent(diameter_m)}&velocity_kms=${encodeURIComponent(velocity_kms)}&density_kg_m3=${encodeURIComponent(density)}`;
    const ctrl = new AbortController();
    const timeout = setTimeout(()=>ctrl.abort(), 8000);
    const res = await fetch(url, { signal: signal || ctrl.signal });
    clearTimeout(timeout);
    if(!res.ok) throw new Error('server calc failed');
    const js = await res.json();
    if(js && js.rings_m) return { E: js.E || null, mt: js.mt, rings_m: js.rings_m };
    throw new Error('invalid server response');
  }catch(err){
    return calcEnergyAndRingsLocal(diameter_m, velocity_kms, density);
  }
}

const densityByPlaceType = { city:10000, town:3000, suburb:4000, village:500, hamlet:200, borough:8000, neighbourhood:6000, isolated_dwelling:50 };

function prettyNumber(n){ return n == null ? 'n/a' : Number(n).toLocaleString(undefined, {maximumFractionDigits:0}); }

async function getElevation(lat, lon, signal){
  const url = `https://api.open-elevation.com/api/v1/lookup?locations=${lat},${lon}`;
  try{
    const controller = new AbortController();
    const timeout = setTimeout(()=>controller.abort(), 10000);
    const res = await fetch(url, { signal: signal || controller.signal });
    clearTimeout(timeout);
    if(!res.ok) return null;
    const js = await res.json();
    return js.results?.[0]?.elevation ?? null;
  }catch(e){ return null; }
}

async function getPlaceInfo(lat, lon, signal){
  const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}&zoom=10&addressdetails=1&accept-language=en`;
  try{
    const res = await fetch(url, { headers: { 'Accept':'application/json' }, signal });
    if(!res.ok) return { name:'Unknown', placeType:'unknown', pop_density:0 };
    const js = await res.json();
    const address = js.address || {};
    const display = js.display_name || '';
    const type = (js.type || js.category || '').toLowerCase();
    const isWater = Boolean(address.ocean || address.water || /sea|ocean|bay|gulf|strait/i.test(display) || type==='water' || type==='ocean');
    if(isWater) return { name:'Ocean / water', placeType:'ocean', pop_density:0 };
    const name = js.name || display.split(',')[0] || 'Nearest place';
    const placeType = (js.type || js.category || 'city').toLowerCase();
    const pop_density = densityByPlaceType[placeType] ?? 1000;
    return { name, placeType, pop_density };
  }catch(e){ return { name:'Unknown', placeType:'unknown', pop_density:0 }; }
}

function drawRings(lat, lon, rings_m){
  const colors=['red','orange','yellow'];
  const layers = [];
  rings_m.forEach((r,i)=>{ layers.push(L.circle([lat,lon], { radius:r, color:colors[i], weight:2, fillOpacity:0.1 }).addTo(map)); });
  return layers;
}

function areaKm2(r_m){ return Math.PI * Math.pow(r_m/1000, 2); }

// Removed wiring for input-panel zoom/save/clear buttons (UI moved to floating control)
function createFloatingZoomControl(){
  const ctrl = document.createElement('div');
  ctrl.className = 'floating-zoom-control';
  ctrl.innerHTML = `
    <button class="fz-btn" id="fz-zoom-in">+</button>
    <button class="fz-btn" id="fz-zoom-out">−</button>
  `;
  document.body.appendChild(ctrl);
  document.getElementById('fz-zoom-in').addEventListener('click', ()=>map.zoomIn());
  document.getElementById('fz-zoom-out').addEventListener('click', ()=>map.zoomOut());
}
createFloatingZoomControl();

map.on('click', async (e)=>{
  const lat=e.latlng.lat, lon=e.latlng.lng;
  latestRequestId += 1; const myId = latestRequestId;
  if(activeController) try{ activeController.abort(); }catch(_){ }
  activeController = new AbortController(); const signal = activeController.signal;

  blastLayers.forEach(l=>map.removeLayer(l)); blastLayers = []; map.closePopup();
  const d = parseFloat(document.getElementById('diam').value || '0');
  const v = parseFloat(document.getElementById('vel').value || '0');
  const rho = parseFloat(document.getElementById('dens').value || '3000');
  const temp = L.circleMarker([lat,lon], { radius:6, color:'#333' }).addTo(map);
  let removedTemp = false;

  try{
    const [elev, place] = await Promise.all([ getElevation(lat, lon, signal), getPlaceInfo(lat, lon, signal) ]);
    if(myId !== latestRequestId){ if(!removedTemp) map.removeLayer(temp); return; }

    const {E, mt, rings_m} = await calcEnergyAndRings(d, v, rho, signal);
    blastLayers = drawRings(lat, lon, rings_m);
    const pop20 = place.pop_density ? Math.round(areaKm2(rings_m[0]) * place.pop_density) : null;
    const pop5  = place.pop_density ? Math.round(areaKm2(rings_m[1]) * place.pop_density) : null;
    const pop1  = place.pop_density ? Math.round(areaKm2(rings_m[2]) * place.pop_density) : null;
    if(!removedTemp){ map.removeLayer(temp); removedTemp = true; }

    const html = `
      <b>Impact Point</b><br>
      ${lat.toFixed(4)}, ${lon.toFixed(4)}<br>
      Elevation: ${elev===null ? 'n/a' : elev + ' m'}<br>
      Nearest: ${place.name} <span class="muted">(${place.placeType})</span><br>
      Assumed population density: ${place.pop_density ? (prettyNumber(place.pop_density) + ' / km²') : 'N/A (ocean)'}<br><br>

      <b>Asteroid</b><br>
      Energy: ${mt===null ? 'n/a' : mt.toFixed(2)} Mt TNT<br>
      20 psi radius: ${(rings_m[0]/1000).toFixed(1)} km<br>
      5 psi radius: ${(rings_m[1]/1000).toFixed(1)} km<br>
      1 psi radius: ${(rings_m[2]/1000).toFixed(1)} km<br><br>

      <b>Estimated population affected</b><br>
      20 psi (severe): ~${pop20===null ? 'N/A' : prettyNumber(pop20)}<br>
      5  psi (moderate): ~${pop5===null ? 'N/A' : prettyNumber(pop5)}<br>
      1  psi (light): ~${pop1===null ? 'N/A' : prettyNumber(pop1)}
    `;

    L.popup().setLatLng(e.latlng).setContent(html).openOn(map);
  }catch(err){
    if(err && err.name === 'AbortError'){ if(!removedTemp) map.removeLayer(temp); return; }
    console.error(err);
    if(!removedTemp) map.removeLayer(temp);
    L.popup().setLatLng(e.latlng).setContent('Error fetching elevation/place info. Try again.').openOn(map);
  }
});