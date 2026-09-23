const net = require('net');
const ipPattern = /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;

function performHealthCheck() {
  const envTargets = process.env.ALLOWED_RTSP_TARGETS;
  if (!envTargets) return;

  const targets = envTargets.split(',').map(t => t.trim()).filter(Boolean);
  const bareIps = targets.filter(t => ipPattern.test(t));

  if (bareIps.length === 0) return;

  console.log(`[RTSP Health] Starting health check for ${bareIps.length} configured camera(s)...`);

  bareIps.forEach(ip => {
    const socket = new net.Socket();
    socket.setTimeout(3000); // 3-second timeout

    const cleanup = () => {
      socket.removeAllListeners();
      socket.destroy();
    };

    socket.connect(554, ip, () => {
      console.log(`[RTSP Health] SUCCESS: Camera at ${ip}:554 is reachable.`);
      cleanup();
    });

    socket.on('timeout', () => {
      console.warn(`[RTSP Health] WARNING: Configured camera at ${ip}:554 is unreachable (timeout). Ensure the device is powered on or update ALLOWED_RTSP_TARGETS.`);
      cleanup();
    });

    socket.on('error', (err) => {
      console.warn(`[RTSP Health] WARNING: Configured camera at ${ip}:554 is unreachable (${err.code}). Ensure the device is powered on or update ALLOWED_RTSP_TARGETS.`);
      cleanup();
    });
  });
}

module.exports = { performHealthCheck };
