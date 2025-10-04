(function () {
  try {
    var LUNAR_DISTANCE_KM = 384400;

    var fileInput  = document.getElementById('fileInput');
    var viewToggle = document.getElementById('viewToggle');
    var statusEl   = document.getElementById('status');

    var listView = document.getElementById('listView');
    var tableView = document.getElementById('tableView');

    var listEl = document.getElementById('asteroidList');
    var tableBody = document.querySelector('#asteroidTable tbody');

    if (!fileInput || !viewToggle || !statusEl || !listEl || !tableBody) {
      throw new Error('Missing required DOM elements. Check IDs in index.html.');
    }

  function setStatus(msg) { statusEl.textContent = msg; }
    function esc(s) { return String(s).replace(/[&<>"']/g, function (m) {
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;', "'":'&#39;'}[m]);
    });}
    function toNum(v) { var n = Number(v); return isFinite(n) ? n : null; }
    function fmtScore(x) { return x == null || isNaN(x) ? 'n/a' : Number(x).toExponential(3); }
    function fmtNum(x, digits, suffix) {
      if (suffix === undefined) suffix = '';
      if (x == null || isNaN(x)) return '—';
      if (!digits) return Math.round(x).toLocaleString() + suffix;
      return Number(x).toFixed(digits) + suffix;
    }
    function str(v) { return (v === null || v === undefined) ? '' : String(v); }

    function has(obj, key) { return obj && Object.prototype.hasOwnProperty.call(obj, key); }

    // -------- mapping helpers (no optional chaining) ----------
    function medianDiameterKm(neo) {
      if (!neo || !neo.estimated_diameter || !neo.estimated_diameter.kilometers) return null;
      var d = neo.estimated_diameter.kilometers;
      var min = Number(d.estimated_diameter_min);
      var max = Number(d.estimated_diameter_max);
      if (!isFinite(min) || !isFinite(max)) return null;
      return (min + max) / 2;
    }

    function closestEarthApproach(neo) {
      if (!neo || !Array.isArray(neo.close_approach_data)) return null;
      var passes = neo.close_approach_data.filter(function (ca) {
        var ob = (ca && ca.orbiting_body) ? String(ca.orbiting_body).toLowerCase() : '';
        return ob === 'earth';
      });
      if (!passes.length) return null;

      var best = null;
      for (var i = 0; i < passes.length; i++) {
        var ca = passes[i];
        var miss = ca && ca.miss_distance ? Number(ca.miss_distance.kilometers) : NaN;
        if (!isFinite(miss)) continue;
        if (!best || miss < best.missKm) {
          var vel = (ca && ca.relative_velocity) ? Number(ca.relative_velocity.kilometers_per_second) : NaN;
          best = {
            missKm: miss,
            date: (ca.close_approach_date_full || ca.close_approach_date || ''),
            velKps: vel
          };
        }
      }
      return best;
    }

    function mapNeoToRow(neo) {
      var dKm = medianDiameterKm(neo);
      var ca  = closestEarthApproach(neo);
      var missKm = ca ? ca.missKm : null;
      var velKps = (ca && isFinite(ca.velKps)) ? ca.velKps : null;
      var hazardScore = (dKm != null && missKm != null && missKm > 0) ? (dKm / missKm) : null;

      return {
        id: neo && neo.id,
        name: (neo && (neo.name || neo.designation || neo.neo_reference_id)) || null,
        jpl_url: neo && neo.nasa_jpl_url,
        approach_date: ca ? ca.date : null,
        diameter_km: dKm,
        miss_distance_km: missKm,
        velocity_kps: velKps,
        hazard_score: hazardScore,
        _raw: neo
      };
    }

    // -------- state ----------
    var records = [];

    // -------- UI events ----------
    viewToggle.addEventListener('change', function () {
      var showTable = !!viewToggle.checked;
      listView.classList.toggle('hidden', showTable);
      tableView.classList.toggle('hidden', !showTable);
    });

    // filter control + spinner
    var filterSelect = document.getElementById('filterSelect');
    var filterSpinner = document.getElementById('filterSpinner');
    var fetchSpinner = document.getElementById('fetchSpinner');
    var fetchButton = document.getElementById('fetchButton');
  function showFilterSpinner() { if (filterSpinner) filterSpinner.classList.remove('hidden'); console.log('[DEBUG] showFilterSpinner'); }
  function hideFilterSpinner() { if (filterSpinner) filterSpinner.classList.add('hidden'); console.log('[DEBUG] hideFilterSpinner'); }
  function showFetchSpinner() { if (fetchSpinner) fetchSpinner.classList.remove('hidden'); console.log('[DEBUG] showFetchSpinner'); }
  function hideFetchSpinner() { if (fetchSpinner) fetchSpinner.classList.add('hidden'); console.log('[DEBUG] hideFetchSpinner'); }

  console.log('[DEBUG] script init — DOM OK');
  // Ensure spinners / overlay are hidden on startup (force-hide)
  try {
    hideFetchSpinner();
    hideFilterSpinner();
    hideLoading();
    console.log('[DEBUG] initial hide of fetch/filter spinners and loading overlay complete');
  } catch (e) {
    console.warn('[DEBUG] initial hide failed (element missing?):', e);
  }
  fileInput.addEventListener('change', function (e) {
      var file = (e.target.files && e.target.files[0]) ? e.target.files[0] : null;
      if (!file) return;
  console.log('[DEBUG] file selected:', file.name);
  setStatus('Loading ' + file.name + '…');
  showFetchSpinner();
      var reader = new FileReader();
      reader.onload = function () {
        try {
          var text = String(reader.result || '');
          var lower = file.name.toLowerCase();
          if (lower.indexOf('.json') !== -1) {
            records = parseJson(text);
          } else if (lower.indexOf('.csv') !== -1) {
            records = parseCsv(text);
          } else {
            throw new Error('Unsupported file type. Please use JSON or CSV.');
          }

          console.log('✅ Final records to render:', Array.isArray(records) ? records.length : records, records);

          if (!Array.isArray(records)) throw new Error('Parsed data is not an array.');
          if (!records.length) {
            setStatus('No rows found after parsing.');
            hideFetchSpinner();
            render([]);
            return;
          }
          
          records.sort((a, b) => (b.hazard_score || 0) - (a.hazard_score || 0));

          console.log('[DEBUG] parse complete - items:', records.length);
          setStatus('Loaded ' + records.length + ' hazardous NEOs. Showing in file order (most → least hazardous).');
          hideFetchSpinner();
          applyFilterAndRender();
        } catch (err) {
          console.error(err);
          setStatus('❌ ' + err.message);
          hideFetchSpinner();
          render([]);
        }
      };
      reader.onerror = function (err) {
        console.error('[DEBUG] file read error', err);
        setStatus('❌ Error reading file.');
        hideFetchSpinner();
      };
      reader.readAsText(file);
    });

    // -------- rendering ----------
    function render(rows) {
      renderList(rows);
      renderTable(rows);
    }

    function renderList(rows) {
      listEl.innerHTML = '';
      for (var i = 0; i < rows.length; i++) {
        var r = rows[i];
        var li = document.createElement('li');

        var name = str(r.name) || str(r.designation) || str(r.id) || '—';
        var score = toNum(r.hazard_score);
        var diameterKm = toNum(r.diameter_km);
        var missKm = toNum(r.miss_distance_km);
        var velKps = toNum(r.velocity_kps);
        var date = str(r.approach_date) || '—';
        var ld = (missKm != null) ? (missKm / LUNAR_DISTANCE_KM) : null;

        li.innerHTML =
          '<div><strong>' + esc(name) + '</strong>' +
          '<span class="badge">Rank ' + (i + 1) + ' / ' + rows.length + '</span></div>' +
          '<div class="meta"><strong>Hazard score:</strong> ' + fmtScore(score) + '</div>' +
          '<div class="meta"><strong>Median diameter:</strong> ' + fmtNum(diameterKm, 3, ' km') +
          ' | <strong>Closest miss:</strong> ' + fmtNum(missKm, 0, ' km') +
          (ld != null ? ' (' + ld.toFixed(2) + ' LD)' : '') +
          (velKps != null ? ' | <strong>Velocity:</strong> ' + velKps.toFixed(2) + ' km/s' : '') +
          '</div>' +
          '<div class="meta"><strong>Approach date:</strong> ' + esc(date) +
          (r.jpl_url ? ' | <a href="' + esc(r.jpl_url) + '" target="_blank" rel="noopener">JPL</a>' : '') +
          (r.id ? ' | <a href="/meteors/visualize/' + esc(r.id) + '">Visualize</a>' : '') +
          '</div>';

        listEl.appendChild(li);
      }
    }

    function renderTable(rows) {
      tableBody.innerHTML = '';
      for (var i = 0; i < rows.length; i++) {
        var r = rows[i];

        var name = str(r.name) || str(r.designation) || str(r.id) || '—';
        var score = toNum(r.hazard_score);
        var diameterKm = toNum(r.diameter_km);
        var missKm = toNum(r.miss_distance_km);
        var ld = (missKm != null) ? (missKm / LUNAR_DISTANCE_KM) : null;
        var velKps = toNum(r.velocity_kps);
        var date = str(r.approach_date) || '—';

        var tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' + (i + 1) + '</td>' +
          '<td>' + esc(name) + '</td>' +
          '<td>' + fmtScore(score) + '</td>' +
          '<td>' + fmtNum(diameterKm, 3) + '</td>' +
          '<td>' + fmtNum(missKm, 0) + '</td>' +
          '<td>' + (ld != null ? ld.toFixed(2) : '—') + '</td>' +
          '<td>' + (velKps != null ? velKps.toFixed(2) : '—') + '</td>' +
          '<td>' + esc(date) + '</td>' +
          '<td>' + (r.jpl_url ? '<a href="' + esc(r.jpl_url) + '" target="_blank" rel="noopener">Link</a>' : '—') +
          (r.id ? ' | <a href="/meteors/visualize/' + esc(r.id) + '">Visualize</a>' : '') + '</td>';
        tableBody.appendChild(tr);
      }
    }

      // -------- date auto-update + loading overlay --------
      var startDateInput = document.getElementById('startDate');
      var endDateInput = document.getElementById('endDate');
      var loadingOverlay = document.getElementById('loadingOverlay');

      function showLoading() { if (loadingOverlay) loadingOverlay.classList.remove('hidden'); }
      function hideLoading() { if (loadingOverlay) loadingOverlay.classList.add('hidden'); }

      // debounce helper
      function debounce(fn, wait) {
        var t = null;
        return function () {
          var args = arguments;
          clearTimeout(t);
          t = setTimeout(function () { fn.apply(null, args); }, wait);
        };
      }

      function clampAndUpdateEndDate() {
        if (!startDateInput || !endDateInput) return;
        var startVal = startDateInput.value;
        var maxVal = startDateInput.max || '';
        if (maxVal && startVal > maxVal) {
          startVal = maxVal;
          startDateInput.value = maxVal;
        }
        // compute end = start + 7 days and update end input only (do NOT auto-submit)
        try {
          var s = new Date(startVal + 'T00:00:00');
          if (!isNaN(s)) {
            var e = new Date(s.getTime() + 7 * 24 * 3600 * 1000);
            var ye = e.getFullYear();
            var me = String(e.getMonth() + 1).padStart(2, '0');
            var de = String(e.getDate()).padStart(2, '0');
            var endStr = ye + '-' + me + '-' + de;
            endDateInput.value = endStr;
          }
        } catch (err) { /* ignore */ }
        // Let the user press Fetch to submit — avoids accidental navigation loops
        setStatus('End date updated. Press Fetch to load data for the selected range.');
      }

      // shorter debounce for the end-date update so it feels responsive
      var debouncedClamp = debounce(clampAndUpdateEndDate, 120);
      if (startDateInput) startDateInput.addEventListener('change', debouncedClamp);

      // show inline fetch spinner when the user manually submits via the Fetch button
      var dateForm = document.getElementById('dateForm');
      if (dateForm) {
        dateForm.addEventListener('submit', function (ev) {
          ev.preventDefault();
          console.log('[DEBUG] Fetch button clicked — performing AJAX fetch');
          // user explicitly clicked fetch — allow AJAX and proceed
          window.__ALLOW_AJAX_FETCH__ = true;
          if (fetchButton) fetchButton.disabled = true;
          showFetchSpinner();

          var startVal = (startDateInput && startDateInput.value) ? startDateInput.value : '';
          var q = '?start_date=' + encodeURIComponent(startVal);
          var url = '/available_meteors.json' + q;
          if (!window.__ALLOW_AJAX_FETCH__) {
            console.log('[DEBUG] AJAX fetch blocked because __ALLOW_AJAX_FETCH__ is false');
            setStatus('Press Fetch to load data.');
            hideFetchSpinner();
            if (fetchButton) fetchButton.disabled = false;
            return;
          }
          console.log('[DEBUG] AJAX URL:', url);

          // use AbortController to guard against hanging requests
          var controller = new AbortController();
          var signal = controller.signal;
          var timeoutMs = 20000; // 20s
          var timeoutId = setTimeout(function () {
            console.warn('[DEBUG] AJAX fetch timeout — aborting');
            controller.abort();
          }, timeoutMs);

          fetch(url, { method: 'GET', headers: { 'Accept': 'application/json' }, signal: signal })
            .then(function (res) {
              clearTimeout(timeoutId);
              return res.json().then(function (j) { return { ok: res.ok, body: j }; });
            })
            .then(function (result) {
              if (!result.ok) {
                console.error('[DEBUG] server returned error', result.body);
                setStatus('❌ Server error: ' + (result.body && result.body.error ? result.body.error : 'unknown'));
                hideFetchSpinner();
                if (fetchButton) fetchButton.disabled = false;
                return;
              }
              console.log('[DEBUG] AJAX fetched items:', Array.isArray(result.body) ? result.body.length : typeof result.body);
              records = result.body || [];
              // normalize: if these look like NeoWs full objects map them
              if (records.length && records[0] && records[0].estimated_diameter && records[0].close_approach_data) {
                console.log('[DEBUG] mapping NeoWs objects to flat rows (client)');
                records = records.map(mapNeoToRow);
              }
              // sort and apply filter
              records.sort(function (a, b) { return (b.hazard_score || 0) - (a.hazard_score || 0); });
              setStatus('Loaded ' + records.length + ' hazardous NEOs (from server).');
              applyFilterAndRender();
              hideFetchSpinner();
              if (fetchButton) fetchButton.disabled = false;
            })
            .catch(function (err) {
              clearTimeout(timeoutId);
              if (err && err.name === 'AbortError') {
                console.error('[DEBUG] AJAX fetch aborted (timeout)');
                setStatus('❌ Request timed out. Try again.');
              } else {
                console.error('[DEBUG] AJAX fetch error', err);
                setStatus('❌ Network error');
              }
              hideFetchSpinner();
              if (fetchButton) fetchButton.disabled = false;
            });
        });
      }

      // hide loading unless form submission actually occurs (for file uploads etc)
      window.addEventListener('pageshow', function () {
        hideLoading();
        hideFetchSpinner();
        if (fetchButton) fetchButton.disabled = false;
      });

    // If server injected initial data, use it
    try {
      if (window.__INITIAL_ERROR__) {
          console.log('[DEBUG] server-initialized error:', window.__INITIAL_ERROR__);
          setStatus('❌ ' + window.__INITIAL_ERROR__);
        }
        if (window.__INITIAL_FETCHED__) {
          console.log('[DEBUG] server indicated it fetched data (INITIAL_FETCHED=true)');
        }

        if (window.__INITIAL_FETCHED__ && window.__INITIAL_ASTEROIDS__ && Array.isArray(window.__INITIAL_ASTEROIDS__)) {
          console.log('[DEBUG] server-initialized asteroids injected:', window.__INITIAL_ASTEROIDS__.length);
          var injected = window.__INITIAL_ASTEROIDS__;
        // Detect if these are NeoWs-like full objects
        if (injected.length && looksLikeNeoWs(injected[0])) {
          records = injected.map(mapNeoToRow);
        } else {
          // assume already flat rows
          records = injected;
        }

    records.sort(function (a, b) { return (b.hazard_score || 0) - (a.hazard_score || 0); });
  console.log('[DEBUG] applied sort to injected records');
  setStatus('Loaded ' + records.length + ' hazardous NEOs (from server).');
  applyFilterAndRender();
      }
    } catch (err) {
      console.error('Error applying injected data:', err);
    }

    // -------- parsing ----------
    function looksLikeNeoWs(record) {
      return !!(record &&
                typeof record === 'object' &&
                has(record, 'estimated_diameter') &&
                has(record, 'close_approach_data') &&
                Array.isArray(record.close_approach_data));
    }

    function parseJson(text) {
      var data = JSON.parse(text);

      if (!Array.isArray(data) && data && Array.isArray(data.data)) {
        console.log('ℹ️ Using data.data array');
        data = data.data;
      }
      if (!Array.isArray(data) && data && Array.isArray(data.near_earth_objects)) {
        console.log('ℹ️ Using data.near_earth_objects array');
        data = data.near_earth_objects;
      }

      if (!Array.isArray(data)) {
        console.warn('⚠️ JSON root is not an array. Got:', data);
        return [];
      }
      if (data.length === 0) {
        console.warn('⚠️ JSON array is empty.');
        return [];
      }

      var anyNeo = false;
      for (var i = 0; i < data.length; i++) {
        if (looksLikeNeoWs(data[i])) { anyNeo = true; break; }
      }

      if (anyNeo) {
        console.log('ℹ️ Detected NeoWs-like records. Total items:', data.length);
        // Filter to hazardous and map to flat shape
        var mapped = [];
        for (var j = 0; j < data.length; j++) {
          var item = data[j];
          if (item && item.is_potentially_hazardous_asteroid === true) {
            mapped.push(mapNeoToRow(item));
          }
        }
        console.log('ℹ️ Hazardous count:', mapped.length, 'Example mapped row:', mapped[0]);
        return mapped;
      }

      console.log('ℹ️ Assuming records already in flat shape.');
      return data;
    }

    function parseCsv(text) {
      var lines = String(text || '').trim().split(/\r?\n/);
      if (!lines.length) return [];
      var headers = lines.shift().split(',').map(function (h) { return h.trim(); });
      var rows = [];
      for (var i = 0; i < lines.length; i++) {
        var parts = lines[i].split(',').map(function (x) { return x.trim(); });
        var obj = {};
        for (var k = 0; k < headers.length; k++) obj[headers[k]] = parts[k];
        ['hazard_score','diameter_km','miss_distance_km','velocity_kps'].forEach(function (key) {
          if (obj[key] !== undefined && obj[key] !== '') obj[key] = Number(obj[key]);
        });
        rows.push(obj);
      }
      return rows;
    }

    // -------- filter handling (client-side) --------
    function applyFilterAndRender() {
      if (!Array.isArray(records)) return;
      if (!filterSelect) { render(records); return; }
      var key = filterSelect.value;
      // shallow copy then sort
      showFilterSpinner();
      setTimeout(function () {
        var copy = records.slice();
        if (key === 'hazard_score') {
          copy.sort(function (a, b) { return (b.hazard_score || 0) - (a.hazard_score || 0); });
        } else if (key === 'size') {
          copy.sort(function (a, b) { return (b.diameter_km || 0) - (a.diameter_km || 0); });
        } else if (key === 'miss_distance') {
          copy.sort(function (a, b) { return (a.miss_distance_km || Infinity) - (b.miss_distance_km || Infinity); });
        } else if (key === 'time_to_impact') {
          // approximated by approach_date (earlier date = sooner impact)
          copy.sort(function (a, b) {
            var da = a.approach_date ? Date.parse(a.approach_date) : Infinity;
            var db = b.approach_date ? Date.parse(b.approach_date) : Infinity;
            return da - db;
          });
        }
        render(copy);
        hideFilterSpinner();
      }, 40); // tiny timeout so spinner shows briefly for large lists
    }

    if (filterSelect) filterSelect.addEventListener('change', applyFilterAndRender);

    console.log('✅ script.js loaded (compat mode)');
  } catch (outerErr) {
    // If anything fails very early (e.g., syntax), put it on the page
    var status = document.getElementById('status');
    if (status) status.textContent = '❌ Startup error: ' + outerErr.message;
    console.error('Startup error:', outerErr);
  }
})();