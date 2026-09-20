/**
 * Mask credentials from RTSP URLs at write time so passwords/usernames never appear
 * in audit logs, review-queue source_uri, run files, or process arguments.
 */

function maskRtspUrl(url) {
  if (!url || typeof url !== 'string') return url;

  // Mask user:pass@ or user@ pattern
  let masked = url;

  try {
    const parsed = new URL(url);
    if (parsed.username || parsed.password) {
      parsed.username = '***';
      parsed.password = '***';
      return parsed.toString();
    }
  } catch (err) {
    // Fallback to regex if URL parser fails on non-standard format
  }

  // Regex fallback covers rtsp://, rtsps://, http://, https:// credentials
  masked = masked.replace(
    /(rtsp[s]?:\/\/)([^:@\s]+):([^@\s]+)@/gi,
    '$1***:***@'
  );

  masked = masked.replace(
    /(rtsp[s]?:\/\/)([^@\s]+)@/gi,
    '$1***@'
  );

  return masked;
}

function maskRtspUrlInObject(obj, keys = ['url', 'streamUrl', 'rtsp_url', 'camera_url', 'source_uri', 'sourceUri']) {
  if (!obj || typeof obj !== 'object') return obj;

  const result = Array.isArray(obj) ? [...obj] : { ...obj };

  for (const key of Object.keys(result)) {
    const val = result[key];
    if (typeof val === 'string') {
      if (keys.includes(key) || val.startsWith('rtsp://') || val.startsWith('rtsps://')) {
        result[key] = maskRtspUrl(val);
      }
    } else if (val && typeof val === 'object') {
      result[key] = maskRtspUrlInObject(val, keys);
    }
  }

  return result;
}

module.exports = { maskRtspUrl, maskRtspUrlInObject };