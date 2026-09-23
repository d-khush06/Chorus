const dns = require('dns').promises;
const { URL } = require('url');

const BLOCKED_IPV4_RANGES = [
  '0.0.0.0/8',
  '10.0.0.0/8',
  '100.64.0.0/10',
  '127.0.0.0/8',
  '169.254.0.0/16',
  '172.16.0.0/12',
  '192.168.0.0/16',
  '192.0.0.0/24',
  '192.0.2.0/24',
  '198.18.0.0/15',
  '198.51.100.0/24',
  '203.0.113.0/24',
  '224.0.0.0/4',
  '240.0.0.0/4',
  '255.255.255.255/32'
];

const BLOCKED_IPV6_RANGES = [
  '::1/128',
  '::/128',
  '::ffff:0:0/96',
  '64:ff9b::/96',
  '100::/64',
  '2001::/32',
  '2001:10::/28',
  '2001:20::/28',
  '2001:db8::/32',
  '2002::/16',
  'fc00::/7',
  'fe80::/10',
  'ff00::/8'
];

// Allowed URL schemes for RTSP/CCTV relay and analysis URLs
// rtsps:// = RTSP over TLS (secure cameras over internet)
// https:// = HLS streams from cloud DVRs or IP cameras with web interface
const ALLOWED_SCHEMES = new Set(['https', 'rtsp', 'rtsps', 'http']);

// Trusted tunnel provider hostnames — these are always allowed regardless of
// which IP they resolve to, since the IP is a Cloudflare / ngrok edge server,
// not the actual camera (the camera sits behind the tunnel).
const TRUSTED_TUNNEL_SUFFIXES = [
  '.trycloudflare.com',   // Cloudflare Quick Tunnels (no account needed)
  '.cfargotunnel.com',    // Cloudflare named tunnels
  '.cloudflare.com',
  '.tcp.ngrok.io',        // ngrok TCP tunnels
  '.ngrok-free.app',      // ngrok free-tier HTTP tunnels
  '.ngrok.app',           // ngrok paid HTTP tunnels
  '.ngrok.io',            // ngrok legacy
  '.serveo.net',          // Serveo SSH tunnels
  '.loca.lt',             // localtunnel.me
];

function isTrustedTunnel(hostname) {
  const h = (hostname || '').toLowerCase();
  return TRUSTED_TUNNEL_SUFFIXES.some(suffix => h.endsWith(suffix));
}

function ipInCIDR(ip, cidr) {
  const [rangeIp, bits] = cidr.split('/');
  const mask = parseInt(bits, 10);
  
  const isCidrIPv6 = rangeIp.includes(':');
  const isIpIPv6 = ip.includes(':');

  if (isCidrIPv6 !== isIpIPv6) {
    return false;
  }
  
  if (isIpIPv6) {
    return ipv6InCIDR(ip, rangeIp, mask);
  } else {
    return ipv4InCIDR(ip, rangeIp, mask);
  }
}

function ipv4InCIDR(ip, rangeIp, mask) {
  const ipNum = ip.split('.').reduce((acc, octet) => (acc << 8) + parseInt(octet, 10), 0) >>> 0;
  const rangeNum = rangeIp.split('.').reduce((acc, octet) => (acc << 8) + parseInt(octet, 10), 0) >>> 0;
  const maskNum = mask === 0 ? 0 : (~0 << (32 - mask)) >>> 0;
  return (ipNum & maskNum) === (rangeNum & maskNum);
}

function ipv6InCIDR(ip, rangeIp, mask) {
  function expandIPv6(addr) {
    if (addr.includes('::')) {
      const parts = addr.split('::');
      const left = parts[0] ? parts[0].split(':').filter(Boolean) : [];
      const right = parts[1] ? parts[1].split(':').filter(Boolean) : [];
      const missing = 8 - left.length - right.length;
      return [...left, ...Array(missing).fill('0000'), ...right].map(p => p.padStart(4, '0'));
    }
    return addr.split(':').filter(Boolean).map(p => p.padStart(4, '0'));
  }

  const ipParts = expandIPv6(ip);
  const rangeParts = expandIPv6(rangeIp);

  const ipBigInt = ipParts.reduce((acc, part) => (acc << 16n) + BigInt(`0x${part}`), 0n);
  const rangeBigInt = rangeParts.reduce((acc, part) => (acc << 16n) + BigInt(`0x${part}`), 0n);
  const maskBigInt = mask === 0 ? 0n : (~0n << (128n - BigInt(mask)));

  return (ipBigInt & maskBigInt) === (rangeBigInt & maskBigInt);
}

function isPrivateIP(ip) {
  const isIPv6 = ip.includes(':');
  if (isIPv6) {
    for (const range of BLOCKED_IPV6_RANGES) {
      if (ipInCIDR(ip, range)) return true;
    }
  } else {
    for (const range of BLOCKED_IPV4_RANGES) {
      if (ipInCIDR(ip, range)) return true;
    }
  }
  return false;
}

function getAllowedTargets() {
  // SECURITY REMINDER: Never commit real camera credentials or IPs to source control.
  // ALLOWED_RTSP_TARGETS is loaded from .env which must be gitignored.
  const envTargets = process.env.ALLOWED_RTSP_TARGETS;
  if (!envTargets) return [];
  return envTargets.split(',').map(t => t.trim()).filter(Boolean);
}

function isRelayExempt(hostname, ip) {
  const relayHost = (process.env.RTSP_RELAY_HOST || process.env.MEDIAMTX_HOST || 'localhost').toLowerCase();
  const hostLower = (hostname || '').toLowerCase();
  if (hostLower === relayHost) return true;
  if (hostLower === 'localhost' || hostLower === '127.0.0.1' || hostLower === '::1') {
    // If relay is configured on localhost
    return true;
  }
  return false;
}

async function validateUrl(inputUrl, options = {}) {
  const allowedSchemes = options.allowedSchemes || ALLOWED_SCHEMES;
  const allowedTargets = options.allowedTargets !== undefined ? options.allowedTargets : getAllowedTargets();

  let parsed;
  try {
    parsed = new URL(inputUrl);
  } catch (err) {
    return { valid: false, reason: 'Invalid URL format', statusCode: 400 };
  }

  const scheme = parsed.protocol.replace(':', '').toLowerCase();
  if (!allowedSchemes.has(scheme)) {
    return { valid: false, reason: `Scheme ${parsed.protocol} not allowed. Only https and rtsp are permitted.`, statusCode: 403 };
  }

  const hostname = parsed.hostname;
  if (!hostname) {
    return { valid: false, reason: 'Missing hostname in URL', statusCode: 400 };
  }

  // ── Fast-path: trusted tunnel providers ─────────────────────────────────
  // Cloudflare / ngrok / Serveo edge IPs are NOT private, but we allow them
  // unconditionally since they are just relay edges, not internal services.
  if (isTrustedTunnel(hostname)) {
    console.log(`[ssrfGuard] Trusted tunnel provider: ${hostname} — skipping IP validation`);
    return {
      valid: true,
      hostname,
      resolvedIps: [],
      validatedIp: hostname,   // use hostname directly; FFmpeg resolves at connect time
      isTunnel: true,
      isRelay: false,
    };
  }

  // ── Fast-path: configured local RTSP relay (MediaMTX etc.) ──────────────
  if (isRelayExempt(hostname)) {
    return {
      valid: true,
      hostname,
      resolvedIps: ['127.0.0.1'],
      validatedIp: '127.0.0.1',
      isRelay: true,
    };
  }

  let resolvedIps;
  try {
    const results = await dns.lookup(hostname, { all: true });
    resolvedIps = results.map(r => r.address);
  } catch (err) {
    return { valid: false, reason: `DNS resolution failed: ${err.message}`, statusCode: 403 };
  }

  if (!resolvedIps || resolvedIps.length === 0) {
    return { valid: false, reason: 'No IP addresses found for hostname', statusCode: 403 };
  }

  // ── Private-IP enforcement ───────────────────────────────────────────────
  //
  // There are now three modes:
  //   1. ALLOW_PUBLIC_RTSP=true   → ANY RTSP/RTSPS URL passes (hotspot, DDNS, public IP)
  //   2. ALLOWED_RTSP_TARGETS=*   → ALL private IPs allowed for that scheme
  //   3. Default                  → Only allowlisted private IPs pass
  //
  const allowPublicRtsp  = (process.env.ALLOW_PUBLIC_RTSP || '').toLowerCase() === 'true';
  const isRtspScheme     = scheme === 'rtsp' || scheme === 'rtsps';

  // Mode 1: ALLOW_PUBLIC_RTSP blanket-allows all RTSP regardless of IP
  if (allowPublicRtsp && isRtspScheme) {
    console.log(`[ssrfGuard] ALLOW_PUBLIC_RTSP=true — allowing ${hostname} (${resolvedIps.join(', ')})`);
    return {
      valid: true,
      hostname,
      resolvedIps,
      validatedIp: resolvedIps[0],
      isRelay: false,
    };
  }

  // Mode 2 + 3: per-IP check
  for (const ip of resolvedIps) {
    if (!isPrivateIP(ip)) continue;  // public IP — always fine

    if (options.allowPrivate) continue;

    // Check admin allowlist (ALLOWED_RTSP_TARGETS)
    const isAllowed = allowedTargets.some(target => {
      if (target === '*') return true;
      if (target.includes('/')) {
        try { return ipInCIDR(ip, target); } catch (e) { return false; }
      }
      return ip === target || hostname === target;
    });

    if (!isAllowed) {
      return {
        valid:      false,
        reason:     `Access to private IP ${ip} is blocked. Add it to ALLOWED_RTSP_TARGETS, or set ALLOW_PUBLIC_RTSP=true for internet cameras.`,
        statusCode: 403,
        blockedIp:  ip,
      };
    }
  }

  // Connect to the validated IP without re-resolving (DNS rebinding / TOCTOU protection)
  const validatedIp = resolvedIps[0];

  return {
    valid: true,
    hostname,
    resolvedIps,
    validatedIp,
    isRelay: false
  };
}

module.exports = {
  validateUrl,
  isPrivateIP,
  getAllowedTargets,
  isRelayExempt,
  BLOCKED_IPV4_RANGES,
  BLOCKED_IPV6_RANGES,
  ALLOWED_SCHEMES
};