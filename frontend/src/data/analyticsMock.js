/**
 * analyticsMock.js
 * Mock analysis responses for Universal Video Analytics Platform.
 * 
 * Swap with real API calls:
 *   const result = await fetch('/api/analyze', { method: 'POST', body: formData }).then(r => r.json());
 */

export const mockGeneralAnalysis = {
  videoTitle: 'Sample Video Analysis',
  duration: 187,
  fps: 30,
  resolution: '1920x1080',
  fileSize: '142 MB',
  processingTime: 4.2,
  overallScore: 87,

  scenes: [
    { id: 's1', start: 0,   end: 23,  label: 'Outdoor — Urban Street', confidence: 0.94, thumbnail: null, dominantColor: '#4a6fa5' },
    { id: 's2', start: 23,  end: 51,  label: 'Interior — Office Space', confidence: 0.88, thumbnail: null, dominantColor: '#5a8a6a' },
    { id: 's3', start: 51,  end: 89,  label: 'Close-up — Person Speaking', confidence: 0.97, thumbnail: null, dominantColor: '#8a6a5a' },
    { id: 's4', start: 89,  end: 134, label: 'Outdoor — Parking Lot', confidence: 0.91, thumbnail: null, dominantColor: '#6a5a8a' },
    { id: 's5', start: 134, end: 187, label: 'Interior — Meeting Room', confidence: 0.85, thumbnail: null, dominantColor: '#5a7a8a' },
  ],

  objectDetection: [
    { label: 'Person',      count: 14, confidence: 0.96 },
    { label: 'Vehicle',     count: 7,  confidence: 0.91 },
    { label: 'Laptop',      count: 3,  confidence: 0.88 },
    { label: 'Chair',       count: 9,  confidence: 0.84 },
    { label: 'Smartphone',  count: 2,  confidence: 0.79 },
    { label: 'Table',       count: 5,  confidence: 0.92 },
  ],

  sentiment: {
    positive: 62,
    neutral:  27,
    negative: 11,
    timeline: [
      { time: 0,   score: 0.55 },
      { time: 30,  score: 0.70 },
      { time: 60,  score: 0.45 },
      { time: 90,  score: 0.80 },
      { time: 120, score: 0.60 },
      { time: 150, score: 0.75 },
      { time: 187, score: 0.68 },
    ],
  },

  transcript: [
    { start: 4,   end: 11,  text: 'Welcome to the quarterly review. Today we\'ll be discussing performance metrics and upcoming goals.' },
    { start: 14,  end: 22,  text: 'As you can see from the dashboard, we\'ve exceeded our targets by twelve percent this quarter.' },
    { start: 25,  end: 38,  text: 'The new product line has been particularly successful, especially in the Asia-Pacific region.' },
    { start: 42,  end: 55,  text: 'However, there are some areas where we need to focus our attention going forward.' },
    { start: 60,  end: 74,  text: 'Marketing spend needs to be optimized and we should look at better attribution models.' },
    { start: 80,  end: 95,  text: 'Moving forward, we have three key initiatives planned for the next quarter.' },
  ],

  keywords: [
    { word: 'performance',  weight: 0.92 },
    { word: 'metrics',      weight: 0.85 },
    { word: 'quarterly',    weight: 0.88 },
    { word: 'product',      weight: 0.79 },
    { word: 'marketing',    weight: 0.76 },
    { word: 'targets',      weight: 0.82 },
    { word: 'initiatives',  weight: 0.71 },
    { word: 'dashboard',    weight: 0.68 },
    { word: 'attribution',  weight: 0.65 },
    { word: 'optimize',     weight: 0.73 },
  ],

  engagementScore: 78,
  contentRating: 'G',
  language: 'English',
  speakerCount: 3,
};

export const mockCyberAnalysis = {
  caseId: 'CYB-2024-0847',
  evidenceHash: 'sha256:a3f9b1d2e4c7f8a0b5d3e6f1c2a4b7d9e0f3c5a8b1d4e7f0c2a5b8d1e4f7a0b3',
  integrityStatus: 'VERIFIED',
  ingestTimestamp: '2024-11-14T03:27:41Z',
  chainOfCustody: [
    { actor: 'Officer K. Sharma', action: 'Evidence Collected', timestamp: '2024-11-14T03:27:41Z' },
    { actor: 'Lab Tech M. Patel', action: 'Digital Transfer', timestamp: '2024-11-14T04:15:22Z' },
    { actor: 'Analyst R. Verma',  action: 'Analysis Initiated', timestamp: '2024-11-14T05:02:09Z' },
  ],
  
  threatScore: 76,
  threatLevel: 'HIGH',
  duration: 312,
  resolution: '1280x720',

  suspiciousTimestamps: [
    { time: 14,  severity: 'critical', label: 'Unidentified Individual Enters Frame',   confidence: 0.93 },
    { time: 47,  severity: 'high',     label: 'Partial Face Obstruction Detected',       confidence: 0.87 },
    { time: 98,  severity: 'medium',   label: 'Loitering Behavior Pattern',              confidence: 0.81 },
    { time: 143, severity: 'critical', label: 'Object Exchange Between Subjects',        confidence: 0.91 },
    { time: 201, severity: 'high',     label: 'Rapid Egress — Possible Flight Pattern', confidence: 0.88 },
    { time: 267, severity: 'medium',   label: 'Re-entry of Previously Flagged Subject', confidence: 0.79 },
  ],

  faceDetection: [
    { id: 'SUBJ-001', appearances: 7, totalSeconds: 64, matchScore: null,          status: 'UNIDENTIFIED' },
    { id: 'SUBJ-002', appearances: 3, totalSeconds: 28, matchScore: 0.94,          status: 'DATABASE MATCH', name: 'REDACTED' },
    { id: 'SUBJ-003', appearances: 2, totalSeconds: 11, matchScore: null,          status: 'PARTIAL' },
  ],

  anomalyHeatmap: [
    { zone: 'Entry Door',    activityScore: 91 },
    { zone: 'Counter Area',  activityScore: 74 },
    { zone: 'Exit Corridor', activityScore: 88 },
    { zone: 'Parking View',  activityScore: 45 },
    { zone: 'Back Hallway',  activityScore: 62 },
  ],

  crimeClassification: [
    { category: 'Suspicious Activity', probability: 0.83 },
    { category: 'Trespassing',          probability: 0.61 },
    { category: 'Drug Transaction',     probability: 0.54 },
    { category: 'Theft / Burglary',     probability: 0.39 },
    { category: 'Assault',              probability: 0.22 },
  ],

  metadataForensics: {
    gpsCoordinates: '28.6139° N, 77.2090° E',
    deviceMake: 'Hikvision DS-2CD2143G2',
    codec: 'H.264 AVC',
    bitrate: '4 Mbps',
    tamperIndicators: ['Timestamp gap at 02:31:18', 'Frame skip detected near 00:47:03'],
    creationDate: '2024-11-14T02:58:12Z',
  },
};

/**
 * Simulates async analysis with a delay.
 * @param {'general'|'cyber'} mode
 * @param {number} delayMs
 */
export async function runMockAnalysis(mode, delayMs = 3500) {
  // Simulate step-by-step progress
  const steps = mode === 'general'
    ? [
        'Extracting video frames…',
        'Running scene segmentation…',
        'Detecting objects & entities…',
        'Performing sentiment analysis…',
        'Generating transcript…',
        'Computing engagement score…',
        'Compiling results…',
      ]
    : [
        'Verifying evidence integrity…',
        'Logging chain of custody…',
        'Extracting forensic metadata…',
        'Running face detection…',
        'Analyzing anomaly patterns…',
        'Classifying threat categories…',
        'Generating threat score…',
        'Sealing analysis report…',
      ];

  return { steps, result: mode === 'general' ? mockGeneralAnalysis : mockCyberAnalysis };
}
