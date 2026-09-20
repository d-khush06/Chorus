import { describe, it, expect, vi, beforeEach } from 'vitest';

// Test maskRtspUrl
import { maskRtspUrl, maskRtspUrlInObject } from '../../../backend/services/maskRtspUrl.js';

// Test streamTicket
import { generateTicket, validateTicket, TICKET_TTL_MS } from '../../../backend/services/streamTicket.js';

// Test ssrfGuard
import { isPrivateIP, validateUrl } from '../../../backend/services/ssrfGuard.js';

describe('maskRtspUrl', () => {
  it('masks username and password from RTSP URL', () => {
    const raw = 'rtsp://admin:secret123@192.168.1.100:554/live';
    const masked = maskRtspUrl(raw);
    expect(masked).toBe('rtsp://***:***@192.168.1.100:554/live');
    expect(masked).not.toContain('secret123');
    expect(masked).not.toContain('admin');
  });

  it('masks username-only RTSP URL', () => {
    const raw = 'rtsp://operator@camera.internal:554/feed';
    const masked = maskRtspUrl(raw);
    expect(masked).toMatch(/^rtsp:\/\/\*\*\*(@|:\*\*\*@)camera\.internal:554\/feed$/);
    expect(masked).not.toContain('operator');
  });

  it('leaves clean URLs without credentials intact', () => {
    const clean = 'rtsp://localhost:8554/mystream';
    expect(maskRtspUrl(clean)).toBe('rtsp://localhost:8554/mystream');
  });

  it('recursively masks URLs inside complex objects', () => {
    const payload = {
      runId: 'run-123',
      source_uri: 'rtsp://admin:supersecret@10.0.0.50:554/h264',
      metadata: {
        camera_url: 'rtsp://user:pass123@cam-01.lan/stream',
        safe_param: 'unchanged'
      }
    };
    const masked = maskRtspUrlInObject(payload);
    expect(masked.source_uri).toBe('rtsp://***:***@10.0.0.50:554/h264');
    expect(masked.metadata.camera_url).toBe('rtsp://***:***@cam-01.lan/stream');
    expect(masked.metadata.safe_param).toBe('unchanged');
    expect(JSON.stringify(masked)).not.toContain('supersecret');
    expect(JSON.stringify(masked)).not.toContain('pass123');
  });
});

describe('streamTicket Service', () => {
  it('generates a multi-use stream ticket bound to userId and resourceId with 15-min TTL', () => {
    const ticket = generateTicket('user-abc', 'upload-video-123.mp4');
    expect(ticket.id).toBeDefined();
    expect(ticket.userId).toBe('user-abc');
    expect(ticket.resourceId).toBe('upload-video-123.mp4');
    expect(ticket.expiresAt - ticket.createdAt).toBe(TICKET_TTL_MS);
    expect(ticket.maxUses).toBeGreaterThanOrEqual(100);
  });

  it('validates a valid stream ticket for the target resource', () => {
    const ticket = generateTicket('user-1', 'clip1.mp4');
    const res = validateTicket(ticket.id, 'clip1.mp4');
    expect(res.valid).toBe(true);
    expect(res.ticket.uses).toBe(1);

    // Multi-use: validate again
    const res2 = validateTicket(ticket.id, 'clip1.mp4');
    expect(res2.valid).toBe(true);
    expect(res2.ticket.uses).toBe(2);
  });

  it('rejects access when resourceId does not match ticket bound resource', () => {
    const ticket = generateTicket('user-1', 'clip1.mp4');
    const res = validateTicket(ticket.id, 'clip2.mp4');
    expect(res.valid).toBe(false);
    expect(res.reason).toBe('Ticket resource mismatch');
  });

  it('rejects expired tickets', () => {
    const ticket = generateTicket('user-1', 'clip1.mp4');
    ticket.expiresAt = Date.now() - 1000; // Force expired
    const res = validateTicket(ticket.id, 'clip1.mp4');
    expect(res.valid).toBe(false);
    expect(res.reason).toBe('Ticket expired');
  });

  it('validates ownership when userId is explicitly provided', () => {
    const ticket = generateTicket('user-1', 'clip1.mp4');
    const res = validateTicket(ticket.id, 'clip1.mp4', 'different-user');
    expect(res.valid).toBe(false);
    expect(res.reason).toBe('Ticket user mismatch');
  });
});

describe('SSRF Guard', () => {
  it('correctly identifies blocked private IPv4 ranges', () => {
    // 127.0.0.0/8 loopback
    expect(isPrivateIP('127.0.0.1')).toBe(true);
    expect(isPrivateIP('127.255.255.254')).toBe(true);

    // 10.0.0.0/8 RFC1918
    expect(isPrivateIP('10.0.0.1')).toBe(true);
    expect(isPrivateIP('10.254.1.1')).toBe(true);

    // 172.16.0.0/12 RFC1918
    expect(isPrivateIP('172.16.0.1')).toBe(true);
    expect(isPrivateIP('172.31.255.254')).toBe(true);
    expect(isPrivateIP('172.32.0.1')).toBe(false); // Public

    // 192.168.0.0/16 RFC1918
    expect(isPrivateIP('192.168.1.1')).toBe(true);
    expect(isPrivateIP('192.168.254.10')).toBe(true);

    // 169.254.0.0/16 link-local / AWS metadata
    expect(isPrivateIP('169.254.169.254')).toBe(true);

    // 100.64.0.0/10 CGNAT
    expect(isPrivateIP('100.64.0.1')).toBe(true);
    expect(isPrivateIP('100.127.255.254')).toBe(true);

    // Public IPs
    expect(isPrivateIP('8.8.8.8')).toBe(false);
    expect(isPrivateIP('1.1.1.1')).toBe(false);
    expect(isPrivateIP('142.250.190.46')).toBe(false);
  });

  it('correctly identifies blocked IPv6 ranges', () => {
    expect(isPrivateIP('::1')).toBe(true);
    expect(isPrivateIP('fe80::1')).toBe(true); // link-local
    expect(isPrivateIP('fc00::1')).toBe(true); // ULA
    expect(isPrivateIP('2607:f8b0:4005:805::200e')).toBe(false); // Google public IPv6
  });

  it('blocks disallowed schemes (e.g. file, ftp, gopher, http)', async () => {
    const res = await validateUrl('ftp://example.com/stream');
    expect(res.valid).toBe(false);
    expect(res.reason).toContain('not allowed');
  });

  it('exempts configured relay host on localhost', async () => {
    const res = await validateUrl('rtsp://localhost:8554/mystream');
    expect(res.valid).toBe(true);
    expect(res.isRelay).toBe(true);
  });

  it('allows private camera when explicitly listed in ALLOWED_RTSP_TARGETS allowlist', async () => {
    const dns = await import('dns');
    vi.spyOn(dns.promises, 'lookup').mockResolvedValueOnce([
      { address: '192.168.10.55', family: 4 }
    ]);

    const res = await validateUrl('rtsp://camera-sec.internal/stream', {
      allowedTargets: ['192.168.10.0/24']
    });
    expect(res.valid).toBe(true);
    expect(res.validatedIp).toBe('192.168.10.55');
  });

  it('blocks private camera when NOT in allowlist and returns 403 reason', async () => {
    const dns = await import('dns');
    vi.spyOn(dns.promises, 'lookup').mockResolvedValueOnce([
      { address: '10.20.30.40', family: 4 }
    ]);

    const res = await validateUrl('rtsp://private-cam.corp/stream', {
      allowedTargets: ['192.168.1.0/24']
    });
    expect(res.valid).toBe(false);
    expect(res.statusCode).toBe(403);
    expect(res.reason).toContain('blocked by SSRF guard');
  });
});
