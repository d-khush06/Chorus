/**
 * cloudflareService.js
 * ────────────────────────────────────────────────────────────────────────────
 * Manages cloudflared Quick-Tunnel processes so that a CCTV camera connected
 * to a mobile hotspot (or any LAN) can be reached from the Chorus backend
 * running anywhere on the internet.
 *
 * How it works:
 *   1. A helper device (laptop / Pi) sits on the SAME network as the camera.
 *   2. That device runs `cloudflared tunnel --url http://localhost:<PORT>` 
 *      (which this service can spawn if the backend is co-located, or the user
 *       runs it manually and pastes the tunnel URL into the Chorus UI).
 *   3. cloudflared prints a public URL like https://random.trycloudflare.com
 *   4. Chorus's relayService connects to that URL → FFmpeg transcodes → HLS.
 *
 * For raw RTSP cameras (no HTTP wrapper) we also support:
 *   - ngrok TCP tunnels  →  rtsp://x.tcp.ngrok.io:PORT/stream
 *   - Any public IP/DDNS →  rtsp://203.x.x.x:554/stream  (ALLOW_PUBLIC_RTSP=true)
 *   - Cloudflare + HLS   →  https://random.trycloudflare.com/stream/index.m3u8
 * ────────────────────────────────────────────────────────────────────────────
 */

const { spawn, execSync } = require('child_process');
const EventEmitter = require('events');

// Regex patterns to capture the public URL from cloudflared's stderr output
const CF_URL_PATTERNS = [
  /https:\/\/[a-z0-9-]+\.trycloudflare\.com/i,
  /https:\/\/[a-z0-9-]+\.cfargotunnel\.com/i,
  /\|\s+(https:\/\/[^\s|]+)/i,
];

class CloudflareService extends EventEmitter {
  constructor() {
    super();
    // tunnelId → { process, pid, publicUrl, localPort, status, error, startedAt, logs[] }
    this.tunnels = new Map();
  }

  /**
   * Check if cloudflared binary is available on PATH or common install locations.
   * Returns { installed: bool, path: string|null, version: string|null }
   */
  checkInstalled() {
    const candidates = [
      'cloudflared',
      '/usr/local/bin/cloudflared',
      '/usr/bin/cloudflared',
      `${process.env.HOME}/.cloudflared/cloudflared`,
      'C:\\Program Files\\cloudflared\\cloudflared.exe',
      'C:\\ProgramData\\chocolatey\\bin\\cloudflared.exe',
    ];

    for (const bin of candidates) {
      try {
        const version = execSync(`"${bin}" --version 2>&1`, {
          encoding: 'utf-8',
          timeout: 3000,
        }).trim();
        return { installed: true, path: bin, version };
      } catch (_) {}
    }
    return { installed: false, path: null, version: null };
  }

  /**
   * Start a Quick Tunnel that exposes a local HTTP/HLS port to the internet.
   *
   * @param {string} tunnelId  - Unique ID (e.g. runId or user-supplied name)
   * @param {number} localPort - Local port to expose (e.g. 8080 for HLS server)
   * @param {object} opts      - { protocol: 'http'|'tcp', timeout: 30000 }
   * @returns {Promise<{ publicUrl: string, tunnelId: string }>}
   */
  startTunnel(tunnelId, localPort, opts = {}) {
    return new Promise((resolve, reject) => {
      if (this.tunnels.has(tunnelId)) {
        const existing = this.tunnels.get(tunnelId);
        if (existing.status === 'ready' && existing.publicUrl) {
          return resolve({ publicUrl: existing.publicUrl, tunnelId });
        }
        // Kill stale tunnel before restarting
        this._killTunnel(tunnelId);
      }

      const { installed, path: cfPath } = this.checkInstalled();
      if (!installed) {
        return reject(new Error(
          'cloudflared is not installed. Run: ' +
          'curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared'
        ));
      }

      const protocol = opts.protocol || 'http';
      const timeout  = opts.timeout  || 35000; // cloudflared can take ~10-15 s to connect
      const localUrl = `${protocol}://localhost:${localPort}`;

      console.log(`[CloudflareService] Starting tunnel ${tunnelId} → ${localUrl}`);

      const proc = spawn(cfPath, ['tunnel', '--url', localUrl], {
        stdio: ['ignore', 'pipe', 'pipe'],
      });

      const info = {
        process: proc,
        pid: proc.pid,
        publicUrl: null,
        localPort,
        status: 'starting',
        error: null,
        startedAt: new Date().toISOString(),
        logs: [],
      };
      this.tunnels.set(tunnelId, info);

      let settled = false;
      const settle = (err, url) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (err) {
          info.status = 'error';
          info.error  = err.message;
          reject(err);
        } else {
          info.publicUrl = url;
          info.status    = 'ready';
          this.emit('tunnel:ready', { tunnelId, publicUrl: url });
          resolve({ publicUrl: url, tunnelId });
        }
      };

      const timer = setTimeout(() => {
        settle(new Error(`cloudflared tunnel timed out after ${timeout}ms — check that port ${localPort} is reachable`));
      }, timeout);

      // cloudflared prints the URL to stderr
      const parseOutput = (data) => {
        const text = data.toString();
        info.logs.push(text);

        for (const pattern of CF_URL_PATTERNS) {
          const match = text.match(pattern);
          if (match) {
            settle(null, match[0].trim());
            return;
          }
        }
        // Also check for error messages
        if (text.includes('failed to') || text.includes('connection refused') || text.includes('ERR')) {
          console.warn(`[CloudflareService] cloudflared stderr: ${text.trim()}`);
        }
      };

      proc.stdout.on('data', parseOutput);
      proc.stderr.on('data', parseOutput);

      proc.on('error', (err) => {
        settle(new Error(`cloudflared process error: ${err.message}`));
      });

      proc.on('close', (code) => {
        if (!settled) {
          settle(new Error(`cloudflared exited with code ${code} before providing a URL`));
        }
        if (this.tunnels.has(tunnelId)) {
          const t = this.tunnels.get(tunnelId);
          if (t.status !== 'stopped') {
            t.status = code === 0 ? 'stopped' : 'error';
          }
        }
        this.emit('tunnel:closed', { tunnelId, code });
      });
    });
  }

  /**
   * Register an externally-created tunnel URL (user ran cloudflared manually
   * or is using ngrok / a static public IP) so Chorus can track and validate it.
   *
   * @param {string} tunnelId
   * @param {string} publicUrl  - e.g. "rtsp://x.tcp.ngrok.io:12345" or "https://abc.trycloudflare.com"
   */
  registerExternalTunnel(tunnelId, publicUrl) {
    this.tunnels.set(tunnelId, {
      process: null,
      pid: null,
      publicUrl,
      localPort: null,
      status: 'external',   // externally managed — Chorus won't kill it
      error: null,
      startedAt: new Date().toISOString(),
      logs: [],
    });
    this.emit('tunnel:ready', { tunnelId, publicUrl });
    return { tunnelId, publicUrl };
  }

  /** Get tunnel info by ID */
  getTunnel(tunnelId) {
    return this.tunnels.get(tunnelId) || null;
  }

  /** List all tunnels (serialized, no process handle) */
  listTunnels() {
    const out = [];
    for (const [id, info] of this.tunnels) {
      out.push({
        tunnelId: id,
        publicUrl: info.publicUrl,
        localPort: info.localPort,
        status: info.status,
        error: info.error,
        startedAt: info.startedAt,
        isExternal: info.status === 'external',
      });
    }
    return out;
  }

  /** Stop a tunnel by ID */
  stopTunnel(tunnelId) {
    const info = this.tunnels.get(tunnelId);
    if (!info) return { success: false, error: 'Tunnel not found' };
    this._killTunnel(tunnelId);
    return { success: true };
  }

  /** Stop all tunnels (called on server shutdown) */
  stopAll() {
    for (const id of this.tunnels.keys()) {
      this._killTunnel(id);
    }
  }

  _killTunnel(tunnelId) {
    const info = this.tunnels.get(tunnelId);
    if (!info || !info.process) return;
    try {
      if (process.platform === 'win32') {
        const { spawn } = require('child_process');
        spawn('taskkill', ['/PID', String(info.pid), '/T', '/F'], { windowsHide: true });
      } else {
        try { process.kill(-info.pid, 'SIGKILL'); } catch (_) {
          process.kill(info.pid, 'SIGKILL');
        }
      }
    } catch (_) {}
    info.status  = 'stopped';
    info.process = null;
    this.emit('tunnel:stopped', { tunnelId });
  }

  /**
   * Return installation instructions for the user's OS.
   */
  installInstructions() {
    const isWin = process.platform === 'win32';
    const isMac = process.platform === 'darwin';
    if (isWin) {
      return {
        method: 'winget',
        command: 'winget install --id Cloudflare.cloudflared',
        alt: 'choco install cloudflared',
        docs: 'https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/',
      };
    }
    if (isMac) {
      return {
        method: 'brew',
        command: 'brew install cloudflare/cloudflare/cloudflared',
        docs: 'https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/',
      };
    }
    return {
      method: 'curl',
      command: 'curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared',
      alt: 'wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared',
      docs: 'https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/',
    };
  }
}

// ── Singleton ──────────────────────────────────────────────────────────────
let _instance = null;
function getCloudflareService() {
  if (!_instance) _instance = new CloudflareService();
  return _instance;
}

module.exports = { CloudflareService, getCloudflareService };
