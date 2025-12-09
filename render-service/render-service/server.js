// render-service/server.js
// Serves static frontend + simple API for Render deployment

const express = require('express');
const path = require('path');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 8000;

// Serve API
app.use(cors());
app.use(express.json());

app.get('/status', (req, res) => res.json({ status: 'ok', timestamp: Date.now() }));

app.get('/route', (req, res) => {
  res.json({
    path: { start: [37.7749, -122.4194], end: [37.7849, -122.4094] },
    eta_seconds: 420
  });
});

app.get('/sos', (req, res) => res.json({ ok: true, message: 'SOS sent (prototype)' }));

// Serve static frontend files from ../frontend
const frontendDir = path.resolve(__dirname, '..', 'frontend');
app.use(express.static(frontendDir));

// Fallback to index.html for SPA routing
app.get('*', (req, res) => {
  res.sendFile(path.join(frontendDir, 'index.html'));
});

// Start server
app.listen(PORT, () => {
  console.log(`✅ SafeRoute render-service listening on http://0.0.0.0:${PORT}`);
});