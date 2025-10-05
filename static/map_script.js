// Boot Leaflet
const map = L.map('map', { zoomControl: true }).setView([51.5074, -0.1278], 6);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

// Ensure correct sizing after header layout
window.addEventListener('load', () => setTimeout(() => map.invalidateSize(), 50));

let blastLayers = [];

// Physics
function calcEnergyAndRings(diameter_m, velocity_kms, density){
  const r = diameter_m/2;
  const vol = (4/3)*Math.PI*Math.pow(r,3);
  const mass = density*vol;
  const v = velocity_kms*1000; // m/s
  const E = 0.5*mass*v*v;      // J
  const mt = E/4.184e15;       // megatons TNT

  // Cube-root scaling for overpressure bands
  const r20km = 1.2*Math.cbrt(mt); // km, 20 psi severe
  const r5km  = 3.2*Math.cbrt(mt); // km, 5 psi moderate
  const r1km  = 7.0*Math.cbrt(mt); // km, 1 psi light

  return {E, mt, rings_m:[r20km*1000, r5km*1000, r1km*1000]};
}

const densityByPlaceType = {
  city: 10000, metropolis: 12000, town: 3000, suburb: 4000,
  borough: 8000, quarter: 6000, village: 500, hamlet: 200,
  isolated_dwelling: 50, neighbourhood: 6000, neighbourhoods: 6000
};

function prettyNumber(n){ return Number(n).toLocaleString(undefined, {maximumFractionDigits:0}); }
function areaKm2(r_m){ return Math.PI * Math.pow(r_m/1000, 2); }

async function getElevation(lat, lon){
  try {
    const url = `https://api.open-elevation.com/api/v1/lookup?locations=${lat},${lon}`;
    const res = await fetch(url);
    if(!res.ok) return null;
    const js = await res.json();
    return js.results?.[0]?.elevation ?? null;
  } catch { return null; }
}

async function getPlaceInfo(lat, lon){
  try {
    const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}&zoom=10&addressdetails=1`;
    const res = await fetch(url, { headers: { "Accept": "application/json" }});
    if(!res.ok) return { name:'Unknown', placeType:'city', density:3000 };
    const js = await res.json();
    const name = js.name || js.display_name?.split(",")[0] || "Nearest place";
    const type = (js.type || js.category || "city").toLowerCase();
    const density = densityByPlaceType[type] ?? 3000;
    return { name, placeType: type, density };
  } catch { return { name:'Unknown', placeType:'city', density:3000 }; }
}

function drawRings(lat, lon, rings_m){
  const colors = ["red","orange","yellow"];
  const layers = [];
  rings_m.forEach((r, i) => {
    layers.push(L.circle([lat, lon], {
      radius: r, color: colors[i], weight: 2, fillOpacity: 0.1
    }).addTo(map));
  });
  return layers;
}

// Social sharing
function buildShareURL(lat, lon, mt){
  const base = window.location.href.split('?')[0];
  const url = `${base}?lat=${lat.toFixed(4)}&lon=${lon.toFixed(4)}&energy=${mt.toFixed(2)}`;
  const text = `Asteroid impact at ${lat.toFixed(2)}, ${lon.toFixed(2)} with energy ${mt.toFixed(2)} Mt TNT!`;
  return {
    twitter:  `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`,
    facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`,
    linkedin: `https://www.linkedin.com/shareArticle?mini=true&url=${encodeURIComponent(url)}&title=${encodeURIComponent(text)}`,
    whatsapp: `https://api.whatsapp.com/send?text=${encodeURIComponent(text + " " + url)}`
  };
}

// Click to simulate
map.on('click', async (e) => {
  const lat = e.latlng.lat, lon = e.latlng.lng;
  blastLayers.forEach(l => map.removeLayer(l));
  blastLayers = [];

  // Read asteroid parameters from the injected global if present, otherwise fall back to query params or defaults
  const params = window.__ASTEROID_PARAMS__ || {};
  const q = (k)=> parseFloat(new URLSearchParams(window.location.search).get(k));
  const d = (params.initial_diameter_m || q('d') || q('diam') || 140);
  const v = (params.initial_velocity_kms || q('v') || q('vel') || 19);
  const rho = (params.initial_density_kg_m3 || q('rho') || q('dens') || 3000);

  const [elev, place] = await Promise.all([
    getElevation(lat, lon).catch(() => null),
    getPlaceInfo(lat, lon).catch(() => ({name:"Unknown", placeType:"city", density:3000}))
  ]);

  const {E, mt, rings_m} = calcEnergyAndRings(d, v, rho);
  blastLayers = drawRings(lat, lon, rings_m);

  const pop20 = Math.round(areaKm2(rings_m[0]) * place.density);
  const pop5  = Math.round(areaKm2(rings_m[1]) * place.density);
  const pop1  = Math.round(areaKm2(rings_m[2]) * place.density);

  const share = buildShareURL(lat, lon, mt);
  const shareHtml = `
    <div class="share-buttons" style="margin-top:8px;font-size:0.9em">
      <b>Share:</b><br>
      <a href="${share.twitter}" target="_blank">🐦 Twitter</a> |
      <a href="${share.facebook}" target="_blank">📘 Facebook</a> |
      <a href="${share.linkedin}" target="_blank">💼 LinkedIn</a> |
      <a href="${share.whatsapp}" target="_blank">📱 WhatsApp</a>
    </div>
  `;

  const html = `
    <b>Impact Point</b><br>
    ${lat.toFixed(4)}, ${lon.toFixed(4)}<br>
    Elevation: ${elev===null ? "n/a" : elev + " m"}<br>
    Nearest: ${place.name} <span class="muted">(${place.placeType})</span><br>
    Assumed pop. density: ${prettyNumber(place.density)} / km²<br><br>

    <b>Asteroid</b><br>
    Energy: ${mt.toFixed(2)} Mt TNT<br>
    20 psi radius: ${(rings_m[0]/1000).toFixed(1)} km<br>
    5 psi radius: ${(rings_m[1]/1000).toFixed(1)} km<br>
    1 psi radius: ${(rings_m[2]/1000).toFixed(1)} km<br><br>

    <b>Estimated population affected</b><br>
    20 psi (severe): ~${prettyNumber(pop20)}<br>
    5  psi (moderate): ~${prettyNumber(pop5)}<br>
    1  psi (light): ~${prettyNumber(pop1)}<br><br>
    ${shareHtml}
  `;
  L.popup().setLatLng(e.latlng).setContent(html).openOn(map);
});

// Optional: auto-load scenario from query string (?lat&lon&d&v&rho)
function qp(k){ return new URLSearchParams(window.location.search).get(k); }
const qlat = parseFloat(qp('lat')), qlon = parseFloat(qp('lon'));
window.addEventListener('load', () => {
  // If the server injected asteroid params, use them to pre-run a scenario when coords are provided
  const params = window.__ASTEROID_PARAMS__ || {};
  const qd = parseFloat(qp('d') || qp('diam'));
  const qv = parseFloat(qp('v') || qp('vel'));
  const qrho = parseFloat(qp('rho') || qp('dens'));

  // If query values present, we allow them to influence the run; otherwise server-injected values are used by click handler
  if (!isNaN(qlat) && !isNaN(qlon)) {
    map.setView([qlat, qlon], 9);
    map.fire('click', { latlng: L.latLng(qlat, qlon) });
  }
});

