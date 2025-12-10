# SafeRouteApp
MART391 Final

🌐 **[Try the Live Demo](YOUR_CODESPACE_URL_HERE)** 

👉 **To get your demo link:**
1. Start the server: `cd saferoute_prototype && uvicorn saferoute_api:app --host 0.0.0.0 --port 8000 --reload`
2. Open the **PORTS** tab in VS Code
3. Right-click port 8000 → **Port Visibility** → **Public**
4. Copy the forwarded URL (format: `https://xxxxx-8000.app.github.dev`)
5. Replace `YOUR_CODESPACE_URL_HERE` above with your copied URL

## Prototype Run Instructions

This workspace includes a Python FastAPI prototype that serves an interactive Leaflet-based map application for emergency routing with real-time hazard visualization.

### Quick Start - Python FastAPI (recommended for prototype):

```bash
cd saferoute_prototype
python3 -m pip install -r requirements.txt || python3 -m pip install fastapi uvicorn requests
uvicorn saferoute_api:app --reload --host 0.0.0.0 --port 8000
```

**Access the app:** Open `http://localhost:8000` in a browser

### Features:
- **Interactive Map**: Click anywhere on the map to set your location, or type an address
- **Address Autocomplete**: Type-ahead suggestions powered by Nominatim
- **Multi-Hazard Demo**: Displays flooded (🌊), fire (🔥), downed powerline (⚡), and blocked (🚧) streets within 3 miles
- **Smart Routing**: OSRM-powered street-level routing to nearest safe zone (schools)
- **SOS System**: Send emergency pings with survivor counts and messages
- **Responder View**: Access `/responders` endpoint to see all active SOS pings
- **Voice Mode**: Toggle speech synthesis for route updates

- **Voice Mode**: Toggle speech synthesis for route updates

### Optional Electron Desktop Wrapper:

```bash
cd render-service/electron
npm install
npm start
```

### Sharing Your Demo:

**For GitHub Codespaces:**
1. Make sure the server is running on port 8000
2. Go to the **PORTS** tab in VS Code (or press Ctrl+Shift+P → "Ports: Focus on Ports View")
3. Right-click port 8000 → **Port Visibility** → **Public**
4. Copy the forwarded URL (e.g., `https://xxxxx-8000.app.github.dev`)
5. Share the URL with others to try your demo!

**Keeping Your Demo Running Longer:**

By default, GitHub Codespaces auto-suspend after 30 minutes of inactivity. To extend this:

1. Go to **https://github.com/settings/codespaces**
2. Under "Default idle timeout", change from **30 minutes** to a longer duration (up to **4 hours**)
3. Click **Save**

**Tips for maintaining server uptime:**
- Keep the Codespace browser tab open during demo periods
- Interact with VS Code occasionally to prevent auto-suspend
- If the server stops, restart with: `cd /workspaces/SafeRouteApp/saferoute_prototype && uvicorn saferoute_api:app --host 0.0.0.0 --port 8000 --reload`
- Consider upgrading to GitHub Pro for longer timeout limits (up to 8 hours)

### API Endpoints:
- `GET /` - Main SafeRoute SPA interface
- `GET /find_safe_zone?address=<addr>` - Geocode address and find route to nearest safe zone
- `POST /sos` - Submit emergency SOS ping with location and details
- `GET /sos` - Retrieve all persisted SOS pings
- `GET /responders` - Responder map view showing all active SOS locations
- `GET /status` - System status and hazard summary

### Technologies:
- **Backend**: FastAPI, Python 3.12
- **Frontend**: Leaflet.js, vanilla JavaScript
- **Geocoding**: Nominatim (OpenStreetMap)
- **Routing**: OSRM (Open Source Routing Machine)
- **Hazard Data**: Overpass API for OSM queries
- **Database**: SQLite for SOS persistence

Notes:
- The FastAPI backend now provides geocoded demo scenarios and a POST `/sos` endpoint that accepts exact GPS coordinates and messages.
- For production or heavy testing, host your own Nominatim/Overpass or follow API usage policies.

