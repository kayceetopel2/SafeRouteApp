"""
SafeRoute FastAPI Prototype for LM Studio + Edge Gallery
Author: [Your Name]
Description:
Local functional prototype demonstrating SafeRoute AI logic
with a lightweight FastAPI web UI for offline simulation.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import random, json, time
import requests
import sqlite3
import threading
import math
from typing import List, Tuple, Optional

# Overpass helper: fetch way geometry by name near a point
def fetch_way_geometry(way_name, around_lat=None, around_lon=None, radius=2000):
    """Query Overpass API to find a way with a given name near the provided lat/lon.
    Returns an array of [lat, lon] pairs if found, otherwise None.
    """
    try:
        # Build a bounding area around the point if provided
        bbox_clause = ''
        if around_lat is not None and around_lon is not None:
            # small bbox in degrees (~radius meters) — approximate
            delta = radius / 111320.0
            south = around_lat - delta
            north = around_lat + delta
            west = around_lon - delta
            east = around_lon + delta
            bbox_clause = f'({south},{west},{north},{east})'

        # Overpass QL: try several name variants (exact, contains) and return the closest way
        candidates = []
        # exact match
        queries = [f"way{bbox_clause}[\"highway\"][\"name\"~\"^{way_name}$\", i]; out geom;",
                   f"way{bbox_clause}[\"highway\"][\"name\"~\"{way_name}\", i]; out geom;",
                   f"way{bbox_clause}[\"highway\"][\"name\"~\"{way_name.split()[0]}\", i]; out geom;"]
        url = 'https://overpass-api.de/api/interpreter'
        headers = {'User-Agent': 'SafeRoutePrototype/1.0'}
        for q in queries:
            query = f"""
            [out:json][timeout:25];
            {q}
            """
            try:
                r = requests.post(url, data={'data': query}, headers=headers, timeout=15)
                r.raise_for_status()
                data = r.json()
                if 'elements' in data and len(data['elements'])>0:
                    for el in data['elements']:
                        if el.get('type') == 'way' and 'geometry' in el:
                            geom = el['geometry']
                            coords = [[pt['lat'], pt['lon']] for pt in geom]
                            candidates.append(coords)
            except Exception:
                continue

        # If we have multiple candidates, pick the one closest to around_lat/lon
        if candidates:
            if around_lat is None or around_lon is None:
                return candidates[0]
            best = None
            best_d = None
            for coords in candidates:
                # compute centroid distance
                cx = sum(p[0] for p in coords)/len(coords)
                cy = sum(p[1] for p in coords)/len(coords)
                d = math.hypot(cx-around_lat, cy-around_lon)
                if best is None or d < best_d:
                    best = coords
                    best_d = d
            return best
        return None
    except Exception:
        pass
    return None

app = FastAPI(title="SafeRoute Prototype")

# --- SQLite setup for persistent SOS pings ---
DB_PATH = '/workspaces/SafeRouteApp/saferoute_prototype/saferoute.db'
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS sos_pings (
        id TEXT PRIMARY KEY,
        lat REAL,
        lon REAL,
        message TEXT,
        survivors INTEGER,
        timestamp TEXT
    )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_sos_to_db(ping: dict):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO sos_pings (id, lat, lon, message, survivors, timestamp) VALUES (?, ?, ?, ?, ?, ?)',
              (ping['id'], ping['location']['lat'], ping['location']['lon'], ping['message'], ping['survivors'], ping['timestamp']))
    conn.commit()
    conn.close()

def load_all_sos_from_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, lat, lon, message, survivors, timestamp FROM sos_pings ORDER BY timestamp DESC')
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({'id': r[0], 'location': {'lat': r[1], 'lon': r[2]}, 'message': r[3], 'survivors': r[4], 'timestamp': r[5]})
    return result

# --- Geometry helpers ---
def seg_intersect(a: Tuple[float,float], b: Tuple[float,float], c: Tuple[float,float], d: Tuple[float,float]) -> bool:
    # Check if segment AB intersects CD using orientation tests
    def orient(p, q, r):
        return (q[1]-p[1])*(r[0]-q[0]) - (q[0]-p[0])*(r[1]-q[1])
    def on_seg(p,q,r):
        return min(p[0],r[0]) <= q[0] <= max(p[0],r[0]) and min(p[1],r[1]) <= q[1] <= max(p[1],r[1])
    p, q, r, s = a, b, c, d
    o1 = orient(p,q,r)
    o2 = orient(p,q,s)
    o3 = orient(r,s,p)
    o4 = orient(r,s,q)
    if o1*o2 < 0 and o3*o4 < 0:
        return True
    return False

def polyline_intersects(poly: List[List[float]], a: Tuple[float,float], b: Tuple[float,float]) -> bool:
    for i in range(len(poly)-1):
        if seg_intersect((poly[i][0], poly[i][1]), (poly[i+1][0], poly[i+1][1]), a, b):
            return True
    return False

# --- Hazard simulation / auto-reroute ---
hazard_lock = threading.Lock()
hazard_version = 0

def hazard_simulator():
    global hazard_version
    toggle = True
    while True:
        time.sleep(10)
        with hazard_lock:
            # flip a simulated flooded street presence
            try:
                if toggle:
                    if 'Downtown Riverfront' not in hazard_data['flood_zones']:
                        hazard_data['flood_zones'].append('Downtown Riverfront')
                else:
                    if 'Downtown Riverfront' in hazard_data['flood_zones']:
                        hazard_data['flood_zones'].remove('Downtown Riverfront')
                hazard_version += 1
                toggle = not toggle
            except NameError:
                # hazard_data not yet initialized, skip until next iteration
                continue

# Note: start simulator after hazard_data is defined (below)

# ---- Mock environment ----
OFFLINE_MODE = False
ACTIVE_MODEL = "LMStudio-Edge-AI-v1"
SAFE_AREAS = ["North Ridge Shelter", "East High Gym", "City Hall", "Hilltop Church"]

hazard_data = {
    "flood_zones": ["Downtown Riverfront", "Harbor District"],
    "closed_roads": ["Main St", "Bridge Ave", "Riverside Blvd"],
    "power_outages": ["Industrial Park", "West Valley"],
    "sos_pings": []
}

# ---- Core AI logic ----
class SafeRouteAI:
    def __init__(self, offline=OFFLINE_MODE):
        self.offline = offline

    def summarize_status(self):
        return {
            "mode": "Offline" if self.offline else "Edge Connected",
            "active_model": ACTIVE_MODEL,
            "hazard_summary": {
                "flood_zones": len(hazard_data["flood_zones"]),
                "closed_roads": len(hazard_data["closed_roads"]),
                "power_outages": len(hazard_data["power_outages"]),
                "active_sos": len(hazard_data["sos_pings"])
            }
        }

    def generate_route(self, start="User Location"):
        destination = random.choice(SAFE_AREAS)
        route = {
            "start": start,
            "destination": destination,
            "path": ["User Location", "Hill St", "Maple Ave", destination],
            "hazards_nearby": [hz for hz, zones in hazard_data.items() if "Downtown" in str(zones)]
        }
        return route

    def send_sos(self, survivors=1, location="User Location"):
        sos_id = f"SOS-{random.randint(1000,9999)}"
        hazard_data["sos_pings"].append({
            "id": sos_id,
            "location": location,
            "survivors": survivors,
            "timestamp": time.ctime()
        })
        return {"status": "SOS Sent", "id": sos_id}

ai = SafeRouteAI()

# ---- FastAPI Routes ----
@app.get("/", response_class=HTMLResponse)
def home():
        html = """
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>SafeRoute Prototype</title>
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
            <style>
                html,body{height:100%;margin:0;background:#0A1D30;color:white;font-family:Arial}
                #header{padding:14px;text-align:center;position:relative;z-index:1000}
                #controls{display:flex;gap:12px;justify-content:center;padding:10px}
                button{padding:12px 20px;border-radius:12px;border:none;font-size:16px;cursor:pointer}
                #map{height:60vh;margin:12px;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.4)}
                #info{padding:10px;text-align:center}
                .btn-route{background:#00AFFF;color:#000}
                .btn-sos{background:#FF4040;color:white}
                .btn-status{background:#222;color:white}
            </style>
        </head>
        <body>
            <div id="header">
                <h1>🛰️ SafeRoute - Prototype</h1>
                <div id="controls">
                    <div style="position:relative;display:inline-block">
                        <input id="addressInput" type="text" placeholder="Enter your address..." style="padding:12px;border-radius:8px;border:1px solid #555;width:300px;background:#1a2a3a;color:white;font-size:14px" autocomplete="off" />
                        <div id="suggestions" style="position:absolute;top:100%;left:0;right:0;background:#1a2a3a;border:1px solid #555;border-top:none;border-radius:0 0 8px 8px;max-height:200px;overflow-y:auto;display:none;z-index:2000"></div>
                    </div>
                    <button id="findSafeZone" class="btn-route">Find Safe Zone</button>
                    <button id="sendSos" class="btn-sos">Send SOS</button>
                    <button id="toggleVoice" class="btn-status">Voice: Off</button>
                    <button id="checkStatus" class="btn-status">Check Status</button>
                </div>
            </div>
            <div id="map"></div>
            <div id="info">Mode: <span id="mode">Offline</span> — <span id="statusSummary">Loading status...</span></div>

            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <script>
                // Basic map setup
                const map = L.map('map');
                const markers = L.featureGroup().addTo(map);
                const routes = L.featureGroup().addTo(map);

                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    maxZoom: 19,
                    attribution: '© OpenStreetMap'
                }).addTo(map);

                // Set default map view (no markers until address is entered)
                let userLatLng = [37.7749, -122.4194];
                map.setView(userLatLng, 3);

                // Address autocomplete using Nominatim
                const addressInput = document.getElementById('addressInput');
                const suggestionsDiv = document.getElementById('suggestions');
                let suggestionTimeout;

                addressInput.addEventListener('input', async (e) => {
                    const query = e.target.value.trim();
                    if(query.length < 3) {
                        suggestionsDiv.style.display = 'none';
                        return;
                    }
                    
                    clearTimeout(suggestionTimeout);
                    suggestionTimeout = setTimeout(async () => {
                        try {
                            const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=5&addressdetails=1`;
                            const res = await fetch(url, { headers: { 'User-Agent': 'SafeRoutePrototype/1.0' } });
                            const data = await res.json();
                            
                            if(data.length > 0) {
                                suggestionsDiv.innerHTML = '';
                                data.forEach(item => {
                                    const div = document.createElement('div');
                                    div.textContent = item.display_name;
                                    div.style.padding = '10px';
                                    div.style.cursor = 'pointer';
                                    div.style.borderBottom = '1px solid #555';
                                    div.style.color = 'white';
                                    div.addEventListener('mouseenter', () => { div.style.background = '#2a3a4a'; });
                                    div.addEventListener('mouseleave', () => { div.style.background = '#1a2a3a'; });
                                    div.addEventListener('click', () => {
                                        addressInput.value = item.display_name;
                                        suggestionsDiv.style.display = 'none';
                                    });
                                    suggestionsDiv.appendChild(div);
                                });
                                suggestionsDiv.style.display = 'block';
                            } else {
                                suggestionsDiv.style.display = 'none';
                            }
                        } catch(e) {
                            console.error('Autocomplete error:', e);
                        }
                    }, 300);
                });

                // Hide suggestions when clicking outside
                document.addEventListener('click', (e) => {
                    if(e.target !== addressInput && e.target.parentElement !== suggestionsDiv) {
                        suggestionsDiv.style.display = 'none';
                    }
                });

                // Hide suggestions on Enter key
                addressInput.addEventListener('keydown', (e) => {
                    if(e.key === 'Enter') {
                        suggestionsDiv.style.display = 'none';
                    }
                });

                // Helpers
                function clearRoute() { routes.clearLayers(); }
                function speak(text){ if(!voiceEnabled) return; try{ speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance(text)); }catch(e){} }

                // Button handlers
                let scenarioData = null;
                let autoRouteInterval = null;
                let lastHazardVersion = null;

                async function fetchAndDrawRoute(origin, destination){
                    try{
                        const params = new URLSearchParams({ start_lat: origin[0], start_lon: origin[1], dest_lat: destination[0], dest_lon: destination[1] });
                        const res = await fetch('/compute_route?'+params.toString());
                        const data = await res.json();
                        if(!data || !data.route) return;
                        clearRoute();
                        const poly = L.polyline(data.route, {color:'#00AFFF', weight:5}).addTo(routes);
                        // draw destination marker
                        const dest = data.route[data.route.length-1];
                        L.marker(dest).addTo(routes).bindPopup('Destination').openPopup();
                        map.fitBounds(poly.getBounds(), {padding:[40,40]});
                        document.getElementById('statusSummary').textContent = `Route updated (hazard v:${data.hazard_version})`;
                        lastHazardVersion = data.hazard_version;
                    }catch(e){ console.error(e); }
                }



                document.getElementById('sendSos').addEventListener('click', async ()=>{
                    try{
                        const survivors = parseInt(prompt('Number of survivors (1-10):', '1')) || 1;
                        const message = prompt('Message (optional):', 'Need assistance');
                        const body = { lat: userLatLng[0], lon: userLatLng[1], message, survivors };
                        const res = await fetch('/sos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
                        const data = await res.json();
                        if(!data || !data.id){ alert('SOS failed'); return; }
                        // place SOS marker at user location with returned id
                        const sosMarker = L.circleMarker(userLatLng, {color:'#FF4040', radius:10}).addTo(routes).bindPopup('SOS Sent: '+data.id + '<br/>Survivors: '+survivors + '<br/>' + (message||'')).openPopup();
                        document.getElementById('statusSummary').textContent = `SOS sent (${data.id})`;
                        speak('SOS sent');
                    }catch(e){ alert('Failed to send SOS: '+e); }
                });

                // Find Safe Zone: geocode address, find nearest safe zone (school), show random hazards
                document.getElementById('findSafeZone').addEventListener('click', async ()=>{
                    try{
                        const address = document.getElementById('addressInput').value.trim();
                        if(!address){ alert('Please enter an address'); return; }
                        const params = new URLSearchParams({ address });
                        const res = await fetch('/find_safe_zone?'+params.toString());
                        const s = await res.json();
                        if(s.error){ alert('Error: '+s.error); return; }
                        // draw scenario
                        markers.clearLayers();
                        clearRoute();
                        // draw all hazard streets with color-coding
                        if(s.hazard_streets && s.hazard_streets.length){
                            const hazardColors = {
                                'flooded': '#FF0000',      // red
                                'fire': '#FF8800',         // orange
                                'powerline': '#FFFF00',    // yellow
                                'blocked': '#9900FF'       // purple
                            };
                            const hazardLabels = {
                                'flooded': '🌊 Flooded',
                                'fire': '🔥 Fire',
                                'powerline': '⚡ Downed Powerline',
                                'blocked': '🚧 Blocked'
                            };
                            s.hazard_streets.forEach(street => {
                                if(street.geometry && street.geometry.length){
                                    const color = hazardColors[street.hazard_type] || '#FF0000';
                                    const label = hazardLabels[street.hazard_type] || 'Hazard';
                                    L.polyline(street.geometry, {color: color, weight: 8, opacity: 0.7}).addTo(routes).bindPopup(label + ': ' + street.name);
                                }
                            });
                        }
                        // draw safe route
                        const safe = L.polyline(s.safe_route, {color:'#00FF6A', weight:5, dashArray:'6,4'}).addTo(routes);
                        const originMarker = L.marker(s.origin).addTo(markers).bindPopup('Your Location').openPopup();
                        const destMarker = L.marker(s.destination).addTo(markers).bindPopup('Safe Zone');
                        map.fitBounds(L.featureGroup([safe, originMarker, destMarker]).getBounds(), {padding:[40,40]});
                        const hazardText = s.hazard_streets.map(h=>`${h.name} (${h.hazard_type})`).join(', ') || 'none';
                        document.getElementById('statusSummary').textContent = `Route to Safe Zone — Hazards: ${hazardText}`;
                        speak('Route to safe zone calculated');
                        scenarioData = s;
                        userLatLng = s.origin;
                    }catch(e){ alert('Failed to find safe zone: '+e); }
                });

                document.getElementById('checkStatus').addEventListener('click', async ()=>{ await fetchStatus(); });

                let voiceEnabled = false;
                document.getElementById('toggleVoice').addEventListener('click', ()=>{
                    voiceEnabled = !voiceEnabled;
                    document.getElementById('toggleVoice').textContent = 'Voice: ' + (voiceEnabled ? 'On' : 'Off');
                });

                // Poll status periodically
                async function fetchStatus(){
                    try{
                        const res = await fetch('/status');
                        const json = await res.json();
                        document.getElementById('mode').textContent = json.mode;
                        document.getElementById('statusSummary').textContent = `Model: ${json.active_model} — Hazards:${JSON.stringify(json.hazard_summary)}`;
                    }catch(e){ document.getElementById('statusSummary').textContent = 'Status unavailable'; }
                }
                fetchStatus();
                setInterval(fetchStatus, 5000);
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

@app.get("/route")
def get_route():
    # allow query params for precise routing: start_lat, start_lon, dest_lat, dest_lon
    return JSONResponse(content=ai.generate_route())


@app.get('/compute_route')
def compute_route(start_lat: Optional[float]=None, start_lon: Optional[float]=None, dest_lat: Optional[float]=None, dest_lon: Optional[float]=None):
    """Compute a simple safe route that avoids known flooded street geometry when possible."""
    # Determine origin/destination
    if start_lat is None or start_lon is None or dest_lat is None or dest_lon is None:
        # fallback to random route
        return JSONResponse(content=ai.generate_route())
    origin = [float(start_lat), float(start_lon)]
    destination = [float(dest_lat), float(dest_lon)]

    # Attempt to get flooded geometry via Overpass near midpoint
    mid_lat = (origin[0] + destination[0]) / 2
    mid_lon = (origin[1] + destination[1]) / 2
    flooded = fetch_way_geometry('5th Ave W', around_lat=mid_lat, around_lon=mid_lon)
    # Basic direct route
    direct = [origin, destination]
    # If flooded exists and intersects the direct segment, compute detour
    if flooded and polyline_intersects(flooded, (origin[0], origin[1]), (destination[0], destination[1])):
        # compute bounding box of flooded
        lats = [p[0] for p in flooded]
        lons = [p[1] for p in flooded]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        # choose detour north or south depending which side is closer
        north_waypoint = [max_lat + 0.0015, (min_lon+max_lon)/2]
        south_waypoint = [min_lat - 0.0015, (min_lon+max_lon)/2]
        # pick waypoint with shorter total distance
        def path_len(path):
            s = 0.0
            for i in range(len(path)-1):
                s += math.hypot(path[i+1][0]-path[i][0], path[i+1][1]-path[i][1])
            return s
        north_path = [origin, north_waypoint, destination]
        south_path = [origin, south_waypoint, destination]
        route = north_path if path_len(north_path) < path_len(south_path) else south_path
    else:
        route = [origin, destination]

    # Include hazards nearby
    with hazard_lock:
        hz = list(hazard_data['flood_zones'])
        version = hazard_version

    resp = {
        'route': route,
        'hazards': hz,
        'hazard_version': version
    }
    return JSONResponse(content=resp)


@app.get("/scenario")
def get_scenario():
    """Return a canned Kalispell flash-flood scenario with coordinates for the prototype UI."""
    # Try to geocode addresses for precise coordinates using Nominatim (OpenStreetMap)
    geocode_cache = getattr(app.state, 'geocode_cache', {})
    if not geocode_cache:
        app.state.geocode_cache = geocode_cache

    def geocode(address):
        if address in geocode_cache:
            return geocode_cache[address]
        try:
            url = 'https://nominatim.openstreetmap.org/search'
            params = {'q': address, 'format': 'json', 'limit': 1}
            headers = {'User-Agent': 'SafeRoutePrototype/1.0 (+https://example.com)'}
            r = requests.get(url, params=params, headers=headers, timeout=5)
            r.raise_for_status()
            items = r.json()
            if items:
                lat = float(items[0]['lat'])
                lon = float(items[0]['lon'])
                geocode_cache[address] = [lat, lon]
                return [lat, lon]
        except Exception:
            pass
        return None

    origin_addr = '2150 U.S. 93 S, Kalispell, MT 59901'
    dest_addr = 'Flathead High School, 644 4th Ave W, Kalispell, MT 59901'
    flooded_street_addr = '5th Ave W, Kalispell, MT'

    origin = geocode(origin_addr)
    destination = geocode(dest_addr)
    flooded_pt = geocode(flooded_street_addr)

    # Fallback to previous approximate values if geocoding fails
    if origin is None:
        origin = [48.1935, -114.3128]
    if destination is None:
        destination = [48.1978, -114.3260]
    if flooded_pt is None:
        flooded_pt = [48.1962, -114.3265]

    # Try to fetch exact way geometry for the flooded street using Overpass
    flooded_street = None
    try:
        flooded_way = fetch_way_geometry('5th Ave W', around_lat=flooded_pt[0], around_lon=flooded_pt[1])
        if flooded_way:
            flooded_street = flooded_way
    except Exception:
        flooded_street = None

    # Fallback to a short polyline for the flooded street centered on flooded_pt
    if flooded_street is None:
        lat, lon = flooded_pt
        flooded_street = [
            [lat + 0.0012, lon - 0.0008],
            [lat, lon],
            [lat - 0.0012, lon + 0.0008]
        ]

    # Generate a simple safe route that avoids the flooded segment.
    # For the prototype we create intermediate waypoints that detour around the flooded_pt.
    safe_route = [
        origin,
        [ (origin[0] + flooded_pt[0]) / 2, origin[1] + 0.004 ],
        [ flooded_pt[0] + 0.0015, flooded_pt[1] - 0.003 ],
        destination
    ]

    scenario = {
        'name': 'Kalispell Flash Flood (geocoded)',
        'description': '5th Ave W flooded — avoid to reach Flathead High School.',
        'origin': origin,
        'destination': destination,
        'flooded_street': flooded_street,
        'safe_route': safe_route,
        'blocked_roads': ['5th Ave W'],
        'notes': 'Geocoded using Nominatim (OpenStreetMap). For demo only.'
    }
    return JSONResponse(content=scenario)


# start background simulator thread (after hazard_data is defined)
try:
    sim_thread = threading.Thread(target=hazard_simulator, daemon=True)
    sim_thread.start()
except Exception:
    pass


@app.post('/sos')
def post_sos(payload: dict):
    """Accept an SOS POST with JSON body: {lat, lon, message, survivors} and store it."""
    try:
        lat = payload.get('lat')
        lon = payload.get('lon')
        message = payload.get('message', '')
        survivors = int(payload.get('survivors', 1))
        sos_id = f"SOS-{random.randint(1000,9999)}"
        ping = {
            'id': sos_id,
            'location': {'lat': lat, 'lon': lon},
            'message': message,
            'survivors': survivors,
            'timestamp': time.ctime()
        }
        hazard_data['sos_pings'].append(ping)
        # persist to sqlite
        save_sos_to_db(ping)
        return JSONResponse(content={'status': 'ok', 'id': sos_id, 'ping': ping})
    except Exception as e:
        return JSONResponse(content={'status': 'error', 'detail': str(e)}, status_code=400)

@app.get("/sos")
def send_sos():
    # Return persisted SOS pings
    rows = load_all_sos_from_db()
    return JSONResponse(content={'sos': rows})

@app.get("/status")
def get_status():
    return JSONResponse(content=ai.summarize_status())


@app.get('/responders', response_class=HTMLResponse)
def responders_view():
        """Responder map showing incoming persistent SOS pings."""
        html = '''
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>Responders - SafeRoute</title>
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
            <style>html,body{height:100%;margin:0} #map{height:100vh}</style>
        </head>
        <body>
            <div id="map"></div>
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <script>
                const map = L.map('map').setView([48.1965, -114.3200], 14);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);
                async function loadSOS(){
                    const res = await fetch('/sos');
                    const json = await res.json();
                    const list = json.sos || [];
                    list.forEach(s => {
                        const lat = s.location.lat; const lon = s.location.lon;
                        L.marker([lat, lon], {icon: L.icon({iconUrl:'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png'})}).addTo(map).bindPopup(`<b>${s.id}</b><br/>Survivors: ${s.survivors}<br/>${s.message}`);
                    });
                    if(list.length) map.fitBounds(list.map(s => [s.location.lat, s.location.lon]));
                }
                loadSOS();
                setInterval(loadSOS, 8000);
            </script>
        </body>
        </html>
        '''
        return HTMLResponse(content=html)


@app.get('/find_safe_zone')
def find_safe_zone(address: str, radius: int=3000):
    """Geocode address, find nearest safe zone (school), generate random flooded streets for demo."""
    try:
        # Geocode address using Nominatim
        geocode_cache = getattr(app.state, 'geocode_cache', {})
        if not geocode_cache:
            app.state.geocode_cache = geocode_cache
        
        def geocode(addr):
            if addr in geocode_cache:
                return geocode_cache[addr]
            try:
                url = 'https://nominatim.openstreetmap.org/search'
                params = {'q': addr, 'format': 'json', 'limit': 1}
                headers = {'User-Agent': 'SafeRoutePrototype/1.0'}
                r = requests.get(url, params=params, headers=headers, timeout=5)
                r.raise_for_status()
                items = r.json()
                if items:
                    lat = float(items[0]['lat'])
                    lon = float(items[0]['lon'])
                    geocode_cache[addr] = [lat, lon]
                    return [lat, lon]
            except Exception:
                pass
            return None
        
        origin_coords = geocode(address)
        if not origin_coords:
            return JSONResponse(content={'error': 'Could not geocode address'}, status_code=400)
        
        lat, lon = origin_coords
        
        # Find nearest school (safe zone)
        url = 'https://overpass-api.de/api/interpreter'
        q = f"""
        [out:json][timeout:25];
        (
          node(around:{radius},{lat},{lon})["amenity"="school"];
          way(around:{radius},{lat},{lon})["amenity"="school"];
          relation(around:{radius},{lat},{lon})["amenity"="school"];
        );
        out center;
        """
        headers = {'User-Agent': 'SafeRoutePrototype/1.0'}
        try:
            r = requests.post(url, data={'data': q}, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception:
            # Overpass may be rate-limited; fallback to Nominatim search for 'school'
            try:
                nm_url = 'https://nominatim.openstreetmap.org/search'
                nm_params = {'q': 'school', 'format': 'json', 'limit': 20}
                nm_h = {'User-Agent': 'SafeRoutePrototype/1.0'}
                nr = requests.get(nm_url, params=nm_params, headers=nm_h, timeout=10)
                nr.raise_for_status()
                nm_data = nr.json()
                data = {'elements': []}
                for item in nm_data:
                    if 'lat' in item and 'lon' in item:
                        data['elements'].append({'type': 'node', 'lat': float(item['lat']), 'lon': float(item['lon'])})
            except Exception:
                return JSONResponse(content={'error': 'Failed to find safe zones'}, status_code=502)
        
        dest = None
        best_d = None
        for el in data.get('elements', []):
            if el.get('type') == 'node' and 'lat' in el and 'lon' in el:
                cx, cy = el['lat'], el['lon']
            else:
                center = el.get('center')
                if center:
                    cx, cy = center.get('lat'), center.get('lon')
                else:
                    continue
            d = math.hypot(cx - lat, cy - lon)
            if best_d is None or d < best_d:
                best_d = d
                dest = [cx, cy]
        
        if dest is None:
            return JSONResponse(content={'error': 'No safe zone found nearby'}, status_code=404)
        
        # Generate 3-6 random hazard streets within 3 miles of the entered address
        # 3 miles = 4828 meters
        hazard_radius = 4828
        
        # Query Overpass for nearby streets (within 3 miles of entered address)
        bbox_delta = hazard_radius / 111320.0
        q_streets = f"""
        [out:json][timeout:25];
        way({lat-bbox_delta},{lon-bbox_delta},{lat+bbox_delta},{lon+bbox_delta})["highway"]["name"];
        out geom;
        """
        hazard_streets = []
        hazard_types = ['flooded', 'fire', 'powerline', 'blocked']
        try:
            rs = requests.post(url, data={'data': q_streets}, headers=headers, timeout=15)
            rs.raise_for_status()
            streets_data = rs.json()
            candidates = []
            for el in streets_data.get('elements', []):
                if el.get('type') == 'way' and 'tags' in el and 'name' in el['tags'] and 'geometry' in el:
                    name = el['tags']['name']
                    geom = [[pt['lat'], pt['lon']] for pt in el['geometry']]
                    candidates.append({'name': name, 'geometry': geom})
            # Pick 3-6 random streets with random hazard types
            import random as rand
            num_hazards = min(rand.randint(3, 6), len(candidates))
            if num_hazards > 0:
                selected = rand.sample(candidates, num_hazards)
                for street in selected:
                    hazard_type = rand.choice(hazard_types)
                    hazard_streets.append({
                        'name': street['name'],
                        'geometry': street['geometry'],
                        'hazard_type': hazard_type
                    })
        except Exception:
            # If Overpass fails, generate synthetic hazard streets around entered address
            hazard_streets = [
                {'name': 'Main St (simulated)', 'geometry': [[lat+0.001, lon-0.002], [lat-0.001, lon+0.002]], 'hazard_type': 'flooded'},
                {'name': '5th Ave (simulated)', 'geometry': [[lat+0.002, lon], [lat-0.002, lon]], 'hazard_type': 'fire'},
                {'name': 'Oak Street (simulated)', 'geometry': [[lat-0.001, lon-0.001], [lat+0.001, lon+0.001]], 'hazard_type': 'powerline'}
            ]
        
        # Compute safe route using OSRM routing service (follows actual roads)
        origin = [float(lat), float(lon)]
        destination = dest
        
        # Use OSRM demo server for street-level routing
        try:
            osrm_url = f'https://router.project-osrm.org/route/v1/driving/{origin[1]},{origin[0]};{destination[1]},{destination[0]}'
            osrm_params = {'overview': 'full', 'geometries': 'geojson'}
            osrm_headers = {'User-Agent': 'SafeRoutePrototype/1.0'}
            osrm_resp = requests.get(osrm_url, params=osrm_params, headers=osrm_headers, timeout=10)
            osrm_resp.raise_for_status()
            osrm_data = osrm_resp.json()
            
            if osrm_data.get('code') == 'Ok' and 'routes' in osrm_data and len(osrm_data['routes']) > 0:
                # Extract route geometry (OSRM returns [lon, lat] pairs, we need [lat, lon])
                coords = osrm_data['routes'][0]['geometry']['coordinates']
                route = [[pt[1], pt[0]] for pt in coords]  # swap to [lat, lon]
            else:
                # Fallback to direct line if OSRM fails
                route = [origin, destination]
        except Exception:
            # If OSRM is unavailable, fall back to direct line
            route = [origin, destination]
        
        scenario = {
            'origin': origin,
            'destination': destination,
            'hazard_streets': hazard_streets,
            'safe_route': route
        }
        return JSONResponse(content=scenario)
    except Exception as e:
        return JSONResponse(content={'error': str(e)}, status_code=500)

# ---- Run ----
# In LM Studio or terminal: uvicorn saferoute_api:app --reload --port 8000
