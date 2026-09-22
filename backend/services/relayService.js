const { spawn, execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const http = require('http');
const { getSSEHub } = require('./sseHub');

const LIVE_DIR = path.join(__dirname, '../public/live');
if (!fs.existsSync(LIVE_DIR)) {
  fs.mkdirSync(LIVE_DIR, { recursive: true });
}

let cachedFfmpegPath = null;

function getFfmpegPath() {
  if (cachedFfmpegPath && fs.existsSync(cachedFfmpegPath)) {
    return cachedFfmpegPath;
  }

  // 1. Explicit env override
  if (process.env.FFMPEG_PATH && fs.existsSync(process.env.FFMPEG_PATH)) {
    cachedFfmpegPath = process.env.FFMPEG_PATH;
    return cachedFfmpegPath;
  }

  // 2. Dynamically ask Python's imageio_ffmpeg for the bundled binary
  try {
    const pyOutput = execSync(
      'python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"',
      { encoding: 'utf-8', timeout: 5000 }
    ).trim();
    if (pyOutput && fs.existsSync(pyOutput)) {
      cachedFfmpegPath = pyOutput;
      console.log(`[RelayService] ffmpeg resolved via imageio_ffmpeg: ${cachedFfmpegPath}`);
      return cachedFfmpegPath;
    }
  } catch (e) {
    console.warn('[RelayService] imageio_ffmpeg lookup failed:', e.message);
  }

  // 3. Fall back to system ffmpeg on PATH
  console.warn('[RelayService] Falling back to system ffmpeg on PATH');
  return 'ffmpeg';
}

class RelayService {
  constructor() {
    this.relays = new Map(); // runId -> { process, pid, hlsDir, hlsUrl, status, error, startTime }
  }

  /**
   * Check if an external MediaMTX server is answering on HLS port 8888
   */
  async checkMediaMTX(host = 'localhost', port = 8888) {
    return new Promise((resolve) => {
      const req = http.get({ host, port, path: '/', timeout: 1000 }, (res) => {
        resolve({ available: true, hlsBase: `http://${host}:${port}` });
      });
      req.on('error', () => resolve({ available: false }));
      req.on('timeout', () => {
        req.destroy();
        resolve({ available: false });
      });
    });
  }

  /**
   * Start HLS relay for a given run and stream URL
   */
  async startRelay(runId, streamUrl) {
    if (this.relays.has(runId)) {
      const existing = this.relays.get(runId);
      if (existing.status === 'ready' || existing.status === 'starting') {
        return existing;
      }
      this.stopRelay(runId);
    }

    const hlsDir = path.join(LIVE_DIR, runId);
    if (!fs.existsSync(hlsDir)) {
      fs.mkdirSync(hlsDir, { recursive: true });
    }

    const playlistPath = path.join(hlsDir, 'index.m3u8');
    // Clear any previous segments in folder
    try {
      const files = fs.readdirSync(hlsDir);
      for (const f of files) {
        fs.unlinkSync(path.join(hlsDir, f));
      }
    } catch (e) {}

    // Check if stream is already HLS or is a Wowza Cloud stream with direct HLS playback
    if (streamUrl.includes('cloud.wowza.com')) {
      let wowzaHlsUrl = streamUrl;
      if (streamUrl.startsWith('rtsp://') || streamUrl.startsWith('rtsps://')) {
        try {
          const u = new URL(streamUrl);
          wowzaHlsUrl = `http://${u.host}${u.pathname}${u.pathname.endsWith('.m3u8') ? '' : '/playlist.m3u8'}`;
        } catch (e) {}
      }
      console.log(`[RelayService] Wowza Cloud stream detected, routing directly to HLS endpoint: ${wowzaHlsUrl}`);
      const relayInfo = {
        runId,
        pid: null,
        hlsDir,
        hlsUrl: wowzaHlsUrl,
        status: 'ready',
        error: null,
        startTime: Date.now()
      };
      this.relays.set(runId, relayInfo);

      setTimeout(() => {
        getSSEHub().emit(runId, {
          type: 'RELAY_READY',
          runId,
          hlsUrl: wowzaHlsUrl,
          stream_stats: {
            fps: 30,
            bitrate: '598 kbps',
            codec: 'H.264'
          }
        });
      }, 300);

      return relayInfo;
    }

    if (streamUrl.toLowerCase().includes('.m3u8')) {
      console.log(`[RelayService] Direct HLS stream detected: ${streamUrl}`);
      const relayInfo = {
        runId,
        pid: null,
        hlsDir,
        hlsUrl: streamUrl,
        status: 'ready',
        error: null,
        startTime: Date.now()
      };
      this.relays.set(runId, relayInfo);

      setTimeout(() => {
        getSSEHub().emit(runId, {
          type: 'RELAY_READY',
          runId,
          hlsUrl: streamUrl,
          stream_stats: {
            fps: 30,
            bitrate: 'Adaptive',
            codec: 'H.264'
          }
        });
      }, 300);

      return relayInfo;
    }

    const ffmpegExe = getFfmpegPath();
    const isRtsp = streamUrl.toLowerCase().startsWith('rtsp://') || streamUrl.toLowerCase().startsWith('rtsps://');
    const isLocalFile = fs.existsSync(streamUrl) || (!isRtsp && !streamUrl.includes('://'));

    let args = [];
    if (isRtsp) {
      args = [
        '-y',
        '-rtsp_transport', 'tcp',
        '-stimeout', '5000000', // 5s socket timeout
        '-i', streamUrl,
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-f', 'hls',
        '-hls_time', '2',
        '-hls_list_size', '4',
        '-hls_flags', 'delete_segments+append_list',
        playlistPath
      ];
    } else {
      // Local video file — must exist; no demo fallback
      if (!fs.existsSync(streamUrl)) {
        throw new Error(
          `Video file not found: ${streamUrl}. ` +
          `For live CCTV streams, provide a valid rtsp:// or rtsps:// URL.`
        );
      }

      // Loop the local file continuously for dashboard preview
      args = [
        '-y',
        '-re',
        '-stream_loop', '-1',
        '-i', streamUrl,
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-tune', 'zerolatency',
        '-g', '30',
        '-f', 'hls',
        '-hls_time', '2',
        '-hls_list_size', '4',
        '-hls_flags', 'delete_segments+append_list',
        playlistPath
      ];
    }

    console.log(`[RelayService] Starting FFmpeg HLS relay for ${runId}...`);
    const proc = spawn(ffmpegExe, args, {
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe']
    });

    const relayInfo = {
      runId,
      pid: proc.pid,
      hlsDir,
      hlsUrl: `/api/cyber/live/${runId}/stream/index.m3u8`,
      status: 'starting',
      error: null,
      startTime: Date.now()
    };
    this.relays.set(runId, relayInfo);

    let stderrBuffer = '';
    proc.stderr.on('data', (d) => {
      const txt = d.toString('utf-8');
      stderrBuffer = (stderrBuffer + txt).slice(-2000);
    });

    // Poll for index.m3u8 readiness
    let pollCount = 0;
    const checkInterval = setInterval(() => {
      pollCount++;
      if (!this.relays.has(runId)) {
        clearInterval(checkInterval);
        return;
      }

      if (fs.existsSync(playlistPath)) {
        try {
          const content = fs.readFileSync(playlistPath, 'utf-8');
          if (content.includes('.ts')) {
            clearInterval(checkInterval);
            relayInfo.status = 'ready';
            console.log(`[RelayService] Relay ready for ${runId}: ${playlistPath}`);
            getSSEHub().emit(runId, {
              type: 'RELAY_READY',
              runId,
              hlsUrl: relayInfo.hlsUrl,
              stream_stats: {
                fps: 30,
                bitrate: '2.5 Mbps',
                codec: 'H.264 (AVC)'
              }
            });
            return;
          }
        } catch (e) {}
      }

      if (pollCount > 25) { // 12.5 seconds timeout
        clearInterval(checkInterval);
        if (relayInfo.status !== 'ready') {
          relayInfo.status = 'error';
          relayInfo.error = stderrBuffer || 'Stream negotiation timed out';
          getSSEHub().emit(runId, {
            type: 'RELAY_ERROR',
            runId,
            error: 'Camera stream timeout: Host unreachable or stream format unsupported.'
          });
        }
      }
    }, 500);

    proc.on('close', (code) => {
      clearInterval(checkInterval);
      if (this.relays.get(runId)?.status !== 'stopped') {
        let errDesc = `Relay process exited with code ${code}`;
        if (stderrBuffer.includes('403') || stderrBuffer.includes('Forbidden')) {
          errDesc = 'Access Denied (403 Forbidden): Server rejected RTSP playback. If using Wowza Cloud, use the HLS playlist endpoint.';
        } else if (stderrBuffer.includes('401') || stderrBuffer.includes('Unauthorized')) {
          errDesc = 'RTSP camera authentication failed (invalid credentials).';
        } else if (stderrBuffer.includes('timed out')) {
          errDesc = 'Connection timed out connecting to RTSP host.';
        }
        
        console.warn(`[RelayService] Relay process for ${runId} closed with code ${code}: ${errDesc}`);
        if (relayInfo.status !== 'ready') {
          relayInfo.status = 'error';
          relayInfo.error = errDesc;
          getSSEHub().emit(runId, {
            type: 'RELAY_ERROR',
            runId,
            error: errDesc
          });
        }
      }
    });

    proc.on('error', (err) => {
      clearInterval(checkInterval);
      relayInfo.status = 'error';
      relayInfo.error = err.message;
      getSSEHub().emit(runId, {
        type: 'RELAY_ERROR',
        runId,
        error: `Failed to spawn transcoding relay: ${err.message}`
      });
    });

    return relayInfo;
  }

  /**
   * Stop HLS relay and clean up resources
   */
  stopRelay(runId) {
    const relay = this.relays.get(runId);
    if (!relay) return;

    relay.status = 'stopped';
    if (relay.pid) {
      try {
        if (process.platform === 'win32') {
          spawn('taskkill', ['/PID', String(relay.pid), '/T', '/F'], { windowsHide: true });
        } else {
          process.kill(relay.pid, 'SIGKILL');
        }
      } catch (e) {}
    }

    this.relays.delete(runId);
    console.log(`[RelayService] Relay stopped for ${runId}`);
  }

  getRelay(runId) {
    return this.relays.get(runId) || null;
  }

  getHlsDir(runId) {
    return path.join(LIVE_DIR, runId);
  }
}

let relayServiceInstance = null;
function getRelayService() {
  if (!relayServiceInstance) {
    relayServiceInstance = new RelayService();
  }
  return relayServiceInstance;
}

module.exports = {
  RelayService,
  getRelayService,
  getFfmpegPath,
  LIVE_DIR
};
