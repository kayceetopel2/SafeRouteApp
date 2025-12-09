# SafeRouteApp
MART391 Final

## Prototype Run Instructions

This workspace includes a small Node "render-service" that serves a frontend SPA prototype and simple API stubs, and a Python FastAPI prototype in `saferoute_prototype`.

- Run the Python FastAPI prototype (serves the Leaflet SPA) and the optional Electron wrapper:

Python FastAPI (recommended for prototype):

```bash
cd saferoute_prototype
python3 -m pip install -r requirements.txt || python3 -m pip install fastapi uvicorn requests
uvicorn saferoute_api:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in a browser to view the SafeRoute SPA. The SPA includes:
- Large `Get Safe Route` and `Send SOS` buttons
- Leaflet map with route rendering and SOS markers
- Text-only and voice modes (toggleable)

Optional Electron desktop wrapper (loads the FastAPI app URL):

```bash
cd render-service/electron
npm install
npm start
```

Notes:
- The FastAPI backend now provides geocoded demo scenarios and a POST `/sos` endpoint that accepts exact GPS coordinates and messages.
- For production or heavy testing, host your own Nominatim/Overpass or follow API usage policies.

