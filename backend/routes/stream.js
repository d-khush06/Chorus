const express = require('express');
const fs = require('fs');
const path = require('path');
const jwt = require('jsonwebtoken');
const router = express.Router();
const { validateTicket } = require('../services/streamTicket');
const { generatePreview } = require('../services/ffprobeService');

const uploadsDir = path.join(__dirname, '../uploads');

function getMimeType(filename) {
  const ext = path.extname(filename).toLowerCase();
  const types = {
    '.mp4': 'video/mp4',
    '.webm': 'video/webm',
    '.ogg': 'video/ogg',
    '.mov': 'video/quicktime',
    '.mkv': 'video/x-matroska',
    '.avi': 'video/x-msvideo',
    '.ts': 'video/mp2t',
    '.m3u8': 'application/vnd.apple.mpegurl'
  };
  return types[ext] || 'application/octet-stream';
}

/**
 * Handle Range-enabled video streaming
 */
async function handleStream(req, res) {
  const { filename } = req.params;
  const { ticket } = req.query;

  // Path traversal defense: strictly use basename
  const safeFilename = path.basename(filename);

  // Authenticate: Ticket check takes priority (EventSource and <video> cannot send Authorization headers)
  if (ticket) {
    const validation = validateTicket(ticket, safeFilename);
    if (!validation.valid) {
      return res.status(403).json({ error: validation.reason || 'Invalid or expired stream ticket' });
    }
  } else {
    // Fallback check for standard Authorization header if available
    const authHeader = req.headers.authorization;
    if (authHeader && authHeader.startsWith('Bearer ')) {
      try {
        const token = authHeader.split(' ')[1];
        jwt.verify(token, process.env.JWT_SECRET || 'secret');
      } catch (err) {
        return res.status(401).json({ error: 'Invalid authentication token' });
      }
    } else {
      return res.status(401).json({ error: 'Stream ticket or authorization required' });
    }
  }

  let filePath = path.join(uploadsDir, safeFilename);

  if (!fs.existsSync(filePath)) {
    return res.status(404).json({ error: 'File not found' });
  }

  // Non-MP4 preview support via ffmpeg
  const ext = path.extname(safeFilename).toLowerCase();
  if (['.mkv', '.avi', '.mov', '.ts'].includes(ext)) {
    const previewFilename = `preview-${path.parse(safeFilename).name}.mp4`;
    const previewPath = path.join(uploadsDir, previewFilename);

    if (fs.existsSync(previewPath)) {
      filePath = previewPath;
    } else {
      try {
        await generatePreview(filePath, previewPath);
        filePath = previewPath;
      } catch (err) {
        // Fallback to streaming original if preview generation fails
        console.warn(`[Stream] Could not generate preview for ${safeFilename}, streaming original:`, err.message);
      }
    }
  }

  const stat = fs.statSync(filePath);
  const fileSize = stat.size;
  const mimeType = getMimeType(filePath);

  const range = req.headers.range;
  if (range) {
    const parts = range.replace(/bytes=/, '').split('-');
    const start = parseInt(parts[0], 10);
    const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;

    // Check unsatisfiable range
    if (isNaN(start) || start >= fileSize || end >= fileSize || start > end) {
      res.setHeader('Content-Range', `bytes */${fileSize}`);
      return res.status(416).json({ error: 'Range not satisfiable' });
    }

    const chunkSize = (end - start) + 1;
    const file = fs.createReadStream(filePath, { start, end });

    const headers = {
      'Content-Range': `bytes ${start}-${end}/${fileSize}`,
      'Accept-Ranges': 'bytes',
      'Content-Length': chunkSize,
      'Content-Type': mimeType,
      'Cache-Control': 'no-cache'
    };

    res.writeHead(206, headers);
    file.pipe(res);

    file.on('error', (err) => {
      console.error('[Stream] File read error:', err.message);
      if (!res.headersSent) {
        res.status(500).json({ error: 'Stream error' });
      }
    });

    // Destroy stream on client close (crucial for resource cleanup)
    req.on('close', () => {
      file.destroy();
    });
  } else {
    // Full file stream (200 OK)
    const headers = {
      'Content-Length': fileSize,
      'Content-Type': mimeType,
      'Accept-Ranges': 'bytes',
      'Cache-Control': 'no-cache'
    };
    res.writeHead(200, headers);
    const file = fs.createReadStream(filePath);
    file.pipe(res);

    req.on('close', () => {
      file.destroy();
    });
  }
}

// Mount both GET /stream/:filename and GET /:filename for compatibility
router.get('/stream/:filename', handleStream);
router.get('/:filename', handleStream);

module.exports = router;
module.exports.handleStream = handleStream;
module.exports.getMimeType = getMimeType;