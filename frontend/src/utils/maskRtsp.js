/**
 * Mask credentials in RTSP/HTTP URLs for safe display and logging
 * Example: rtsp://admin:pass@192.168.1.10:554/live -> rtsp://***:***@192.168.1.10:554/live
 */
export function maskRtspUrl(url) {
  if (!url || typeof url !== 'string') return url;
  return url.replace(/([a-zA-Z0-9+.-]+:\/\/)([^:@\s]+):([^@\s]+)@/g, '$1***:***@');
}

export default maskRtspUrl;
