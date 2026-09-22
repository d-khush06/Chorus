/**
 * tunnel.js  —  /api/tunnel
 * ────────────────────────────────────────────────────────────────────────────
 * REST API for managing Cloudflare Quick-Tunnels and registering external
 * tunnel URLs (ngrok, public IP, DDNS) for CCTV sources.
 *
 * Endpoints:
 *   GET  /api/tunnel/check        → Is cloudflared installed?
 *   GET  /api/tunnel/instructions → How to install cloudflared
 *   GET  /api/tunnel              → List all active tunnels
 *   POST /api/tunnel/start        → Start a new CF Quick-Tunnel
 *   POST /api/tunnel/register     → Register an external tunnel URL
 *   GET  /api/tunnel/:id          → Get single tunnel status
 *   DELETE /api/tunnel/:id        → Stop a tunnel
 * ────────────────────────────────────────────────────────────────────────────
 */

const express  = require('express');
const router   = express.Router();
const { protect } = require('../middleware/auth');
const { getCloudflareService } = require('../services/cloudflareService');
const { validateUrl }          = require('../services/ssrfGuard');

// ── GET /api/tunnel/check ─────────────────────────────────────────────────
// Returns whether cloudflared is installed and its version.
router.get('/check', protect, (req, res) => {
  const svc    = getCloudflareService();
  const result = svc.checkInstalled();
  res.json({
    installed: result.installed,
    path:      result.path,
    version:   result.version,
    instructions: result.installed ? null : svc.installInstructions(),
  });
});

// ── GET /api/tunnel/instructions ─────────────────────────────────────────
// Returns OS-specific install instructions for cloudflared.
router.get('/instructions', (req, res) => {
  const svc = getCloudflareService();
  res.json({
    instructions: svc.installInstructions(),
    usageGuide: {
      sameNetwork: {
        title: 'Camera on same network as this server',
        steps: [
          'No tunnel needed — just enter the RTSP URL directly.',
          'Example: rtsp://192.168.1.100:554/stream',
          'Set ALLOW_PUBLIC_RTSP=false in backend/.env',
        ],
      },
      hotspotOrRemote: {
        title: 'Camera connected via mobile hotspot / different network',
        steps: [
          '1. Install cloudflared on a device that IS on the same network as your camera.',
          '2. Run: cloudflared tunnel --url http://<camera-ip>:8080',
          '   Or wrap RTSP with a MediaMTX HLS bridge first: cloudflared tunnel --url http://localhost:8888',
          '3. Copy the generated URL (e.g. https://abc123.trycloudflare.com)',
          '4. Paste it into Chorus → Live CCTV → Stream URL',
          '5. Chorus will connect to it directly — no same-network needed.',
        ],
      },
      publicIp: {
        title: 'Camera with a direct public IP or DDNS hostname',
        steps: [
          'Set ALLOW_PUBLIC_RTSP=true in backend/.env',
          'Enter the public URL directly: rtsp://<public-ip>:554/stream',
          'Examples:',
          '  rtsp://203.x.x.x:554/stream',
          '  rtsp://myhome.ddns.net:554/cam1',
          '  rtsps://camera.example.com:322/secure',
        ],
      },
      ngrok: {
        title: 'Using ngrok TCP tunnel (alternative to Cloudflare)',
        steps: [
          '1. Install ngrok: https://ngrok.com/download',
          '2. Run: ngrok tcp 554  (or your camera RTSP port)',
          '3. Copy the TCP URL (e.g. tcp://1.tcp.ngrok.io:12345)',
          '4. Change tcp:// to rtsp:// and enter in Chorus',
          '   → rtsp://1.tcp.ngrok.io:12345/stream',
        ],
      },
    },
  });
});

// ── GET /api/tunnel ───────────────────────────────────────────────────────
// List all active tunnels.
router.get('/', protect, (req, res) => {
  const svc = getCloudflareService();
  res.json({ tunnels: svc.listTunnels() });
});

// ── POST /api/tunnel/start ────────────────────────────────────────────────
// Spawn a cloudflared Quick-Tunnel exposing a local port.
// Body: { tunnelId?: string, localPort: number, protocol?: 'http'|'tcp', timeout?: number }
router.post('/start', protect, async (req, res) => {
  const { localPort, protocol = 'http', timeout = 35000 } = req.body;
  const tunnelId = req.body.tunnelId || `cf_${Date.now()}`;

  if (!localPort || typeof localPort !== 'number' || localPort < 1 || localPort > 65535) {
    return res.status(400).json({ success: false, error: 'localPort must be a number between 1 and 65535' });
  }

  const svc = getCloudflareService();

  try {
    const { publicUrl } = await svc.startTunnel(tunnelId, localPort, { protocol, timeout });
    return res.json({
      success:   true,
      tunnelId,
      publicUrl,
      message:   `Tunnel ready — use this URL in Chorus: ${publicUrl}`,
      hint:      `For RTSP cameras, replace https:// with rtsp:// if your camera speaks raw RTSP`,
    });
  } catch (err) {
    return res.status(500).json({
      success: false,
      error: err.message,
      instructions: svc.installInstructions(),
    });
  }
});

// ── POST /api/tunnel/register ─────────────────────────────────────────────
// Register an externally managed tunnel URL (user ran cloudflared/ngrok manually,
// or has a public IP / DDNS domain).
// Body: { tunnelId?: string, publicUrl: string }
router.post('/register', protect, async (req, res) => {
  const { publicUrl } = req.body;
  const tunnelId = req.body.tunnelId || `ext_${Date.now()}`;

  if (!publicUrl) {
    return res.status(400).json({ success: false, error: 'publicUrl is required' });
  }

  // Validate the URL through ssrfGuard before registering
  const validation = await validateUrl(publicUrl, {
    allowedSchemes: new Set(['https', 'http', 'rtsp', 'rtsps']),
  });

  if (!validation.valid) {
    return res.status(403).json({
      success: false,
      error:   `URL blocked by security guard: ${validation.reason}`,
      hint:    'Set ALLOW_PUBLIC_RTSP=true in backend/.env to allow public internet RTSP cameras.',
    });
  }

  const svc = getCloudflareService();
  svc.registerExternalTunnel(tunnelId, publicUrl);

  return res.json({
    success: true,
    tunnelId,
    publicUrl,
    resolvedIp: validation.validatedIp,
    message: `External tunnel registered. Use tunnelId "${tunnelId}" when starting a Cyber run.`,
  });
});

// ── GET /api/tunnel/:id ───────────────────────────────────────────────────
router.get('/:id', protect, (req, res) => {
  const svc  = getCloudflareService();
  const info = svc.getTunnel(req.params.id);
  if (!info) {
    return res.status(404).json({ success: false, error: 'Tunnel not found' });
  }
  res.json({
    tunnelId:   req.params.id,
    publicUrl:  info.publicUrl,
    localPort:  info.localPort,
    status:     info.status,
    error:      info.error,
    startedAt:  info.startedAt,
    isExternal: info.status === 'external',
  });
});

// ── DELETE /api/tunnel/:id ────────────────────────────────────────────────
router.delete('/:id', protect, (req, res) => {
  const svc    = getCloudflareService();
  const result = svc.stopTunnel(req.params.id);
  res.json(result);
});

module.exports = router;
