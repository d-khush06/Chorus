import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import path from 'path';
import fs from 'fs';
import { handleStream, getMimeType } from '../../../backend/routes/stream.js';
import { generateTicket } from '../../../backend/services/streamTicket.js';

describe('Range Streaming Route (/api/videos/stream/:filename)', () => {
  const backendUploadsDir = path.resolve(__dirname, '../../../backend/uploads');
  const testFilename = 'test-sample-video.mp4';
  const testFilePath = path.join(backendUploadsDir, testFilename);

  beforeEach(() => {
    if (!fs.existsSync(backendUploadsDir)) {
      fs.mkdirSync(backendUploadsDir, { recursive: true });
    }
    fs.writeFileSync(testFilePath, Buffer.alloc(1000, 0x41));
  });

  afterEach(() => {
    try {
      if (fs.existsSync(testFilePath)) {
        fs.unlinkSync(testFilePath);
      }
    } catch (e) {}
  });

  it('correctly maps mime types for common video formats', () => {
    expect(getMimeType('video.mp4')).toBe('video/mp4');
    expect(getMimeType('video.webm')).toBe('video/webm');
    expect(getMimeType('video.mov')).toBe('video/quicktime');
    expect(getMimeType('stream.m3u8')).toBe('application/vnd.apple.mpegurl');
  });

  it('returns 401 when neither stream ticket nor bearer auth is supplied', async () => {
    const req = {
      params: { filename: testFilename },
      query: {},
      headers: {},
      on: vi.fn()
    };
    let statusSent = null;
    let jsonSent = null;
    const res = {
      status: (s) => { statusSent = s; return res; },
      json: (j) => { jsonSent = j; return res; }
    };

    await handleStream(req, res);
    expect(statusSent).toBe(401);
    expect(jsonSent.error).toContain('ticket');
  });

  it('returns 206 with correct Content-Range and chunk size when valid Range is requested', async () => {
    const ticket = generateTicket('user-1', testFilename);
    const req = {
      params: { filename: testFilename },
      query: { ticket: ticket.id },
      headers: { range: 'bytes=0-499' },
      on: vi.fn()
    };

    let statusCode = null;
    let responseHeaders = {};
    const res = {
      writeHead: (code, headers) => {
        statusCode = code;
        responseHeaders = headers;
      },
      status: vi.fn().mockReturnThis(),
      json: vi.fn(),
      setHeader: vi.fn(),
      pipe: vi.fn(),
      emit: vi.fn(),
      on: vi.fn(),
      once: vi.fn()
    };

    await handleStream(req, res);
    expect(statusCode).toBe(206);
    expect(responseHeaders['Content-Range']).toBe('bytes 0-499/1000');
    expect(responseHeaders['Content-Length']).toBe(500);
    expect(responseHeaders['Accept-Ranges']).toBe('bytes');
    expect(responseHeaders['Content-Type']).toBe('video/mp4');
  });

  it('returns 416 Range Not Satisfiable when range start exceeds file size', async () => {
    const ticket = generateTicket('user-1', testFilename);
    const req = {
      params: { filename: testFilename },
      query: { ticket: ticket.id },
      headers: { range: 'bytes=1500-2000' },
      on: vi.fn()
    };

    let statusSent = null;
    let jsonSent = null;
    let rangeHeader = null;
    const res = {
      setHeader: (name, val) => { if (name === 'Content-Range') rangeHeader = val; },
      status: (s) => { statusSent = s; return res; },
      json: (j) => { jsonSent = j; return res; }
    };

    await handleStream(req, res);
    expect(statusSent).toBe(416);
    expect(rangeHeader).toBe('bytes */1000');
    expect(jsonSent.error).toContain('Range not satisfiable');
  });

  it('neutralizes path traversal attempts using path.basename', async () => {
    const ticket = generateTicket('user-1', 'passwd');
    const req = {
      params: { filename: '../../../../etc/passwd' },
      query: { ticket: ticket.id },
      headers: {},
      on: vi.fn()
    };

    let statusSent = null;
    const res = {
      status: (s) => { statusSent = s; return res; },
      json: vi.fn()
    };

    await handleStream(req, res);
    // Looking for safe filename 'passwd' in uploads directory (which doesn't exist)
    expect(statusSent).toBe(404);
  });
});
