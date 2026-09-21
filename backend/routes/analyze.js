const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const router = express.Router();
const { protect } = require('../middleware/auth');
const casesRoute = require('./cases');
const { getJobManager } = require('../services/jobManager');
const { getSSEHub } = require('../services/sseHub');
const { validateUrl } = require('../services/ssrfGuard');
const { maskRtspUrl, maskRtspUrlInObject } = require('../services/maskRtspUrl');
const { validateTicket } = require('../services/streamTicket');
const { buildGeneralOutput, buildCyberOutput } = require('../services/outputFormatter');
const { getRelayService } = require('../services/relayService');
const jwt = require('jsonwebtoken');

const uploadsDir = path.join(__dirname, '../uploads');
if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir, { recursive: true });
}

const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, uploadsDir),
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1e9);
    const ext = path.extname(file.originalname) || '.mp4';
    cb(null, `upload-${uniqueSuffix}${ext}`);
  }
});

const upload = multer({
  storage,
  limits: { fileSize: 1024 * 1024 * 1024 },
  fileFilter: (req, file, cb) => cb(null, true)
});

function computeFileHash(filePath) {
  try {
    if (fs.existsSync(filePath)) {
      const buffer = fs.readFileSync(filePath);
      return crypto.createHash('sha256').update(buffer).digest('hex');
    }
  } catch (e) {
    console.error('Error calculating file hash:', e);
  }
  return crypto.randomBytes(32).toString('hex');
}


// POST /api/analyze - Async job creation, returns runId immediately
router.post('/', protect, upload.single('video'), async (req, res) => {
  const { mode = 'general', prompt = '', url = '', entry_point = 'forensic', case_id = null, notes = '' } = req.body;
  const videoFile = req.file;

  if (!videoFile && !prompt.trim() && !url.trim()) {
    return res.status(400).json({ success: false, error: 'Either video file, remote URL, or analysis prompt is required' });
  }
  if (!['general', 'cyber'].includes(mode)) {
    return res.status(400).json({ success: false, error: 'Invalid mode. Must be "general" or "cyber"' });
  }
  if (url && !url.startsWith('demo')) {
    const validation = await validateUrl(url, { allowPrivate: true, allowedTargets: [] });
    if (!validation.valid) {
      return res.status(403).json({ success: false, error: validation.reason });
    }
  }

  const source_type = videoFile ? 'local_upload' : (url.includes('youtube') ? 'youtube' : 'live_rtsp');
  const videoPath = videoFile ? videoFile.path : null;
  const rawHash = videoPath ? computeFileHash(videoPath) : crypto.randomBytes(32).toString('hex');

  const jobManager = getJobManager();
  const run = jobManager.createRun({
    mode, source_type, entry_point, case_id, notes,
    videoPath, url: url || null, prompt, rawHash,
    user_id: req.user._id.toString()
  });

  // Start live stream relay if RTSP or live monitoring
  if (source_type === 'live_rtsp' && url) {
    try {
      getRelayService().startRelay(run.id, url);
    } catch (relayErr) {
      console.warn(`[Analyze] Relay service failed to start for run ${run.id}:`, relayErr.message);
    }
  }

  res.status(202).json({ success: true, runId: run.id });
});

// GET /api/analyze/runs/:id - Get run status
router.get('/runs/:id', protect, async (req, res) => {
  const jobManager = getJobManager();
  const run = jobManager.getRun(req.params.id);
  if (!run) return res.status(404).json({ success: false, error: 'Run not found' });
  if (run.user_id && run.user_id !== req.user._id.toString()) {
    return res.status(403).json({ success: false, error: 'Not authorized' });
  }
  res.json({ success: true, run: jobManager.serializeRun(run) });
});

// GET /api/analyze/runs/:id/events - SSE event stream
// Accepts authentication via ticket (for EventSource) or Bearer header
router.get('/runs/:id/events', async (req, res) => {
  const { id } = req.params;
  const { ticket } = req.query;

  let authorized = false;
  let authUserId = null;

  if (ticket) {
    const validation = validateTicket(ticket, id);
    if (validation.valid) {
      authorized = true;
      authUserId = validation.ticket?.userId;
    }
  }

  if (!authorized && req.headers.authorization && req.headers.authorization.startsWith('Bearer ')) {
    try {
      const token = req.headers.authorization.split(' ')[1];
      const decoded = jwt.verify(token, process.env.JWT_SECRET || 'secret');
      authorized = true;
      authUserId = decoded.id;
    } catch (e) {}
  }

  if (!authorized) {
    return res.status(401).json({ success: false, error: 'Authentication ticket or token required for event stream' });
  }

  const jobManager = getJobManager();
  const run = jobManager.getRun(id);
  if (!run) return res.status(404).json({ success: false, error: 'Run not found' });

  if (run.user_id && authUserId && run.user_id !== authUserId.toString()) {
    return res.status(403).json({ success: false, error: 'Not authorized for this run' });
  }

  getSSEHub().addConnection(id, req, res);
});

// GET /api/analyze/runs/:id/profile - Retrieve VideoProfile JSON for a run
router.get('/runs/:id/profile', protect, async (req, res) => {
  const jobManager = getJobManager();
  const run = jobManager.getRun(req.params.id);
  if (!run) return res.status(404).json({ success: false, error: 'Run not found' });
  if (run.user_id && run.user_id !== req.user._id.toString()) {
    return res.status(403).json({ success: false, error: 'Not authorized' });
  }

  // engine_profile is in the run result
  const profile = run.result?.engine_profile || run.result?.pipelineResult?.engine_profile || null;
  if (!profile) {
    return res.status(404).json({
      success: false,
      error: 'Engine profile not available for this run. The run may not have completed or the VideoEngine step was skipped.',
    });
  }
  res.json({ success: true, profile });
});

// DELETE /api/analyze/runs/:id - Cancel run
router.delete('/runs/:id', protect, async (req, res) => {
  const jobManager = getJobManager();
  const run = jobManager.getRun(req.params.id);
  if (!run) return res.status(404).json({ success: false, error: 'Run not found' });
  if (run.user_id && run.user_id !== req.user._id.toString()) {
    return res.status(403).json({ success: false, error: 'Not authorized' });
  }
  const result = jobManager.cancelRun(req.params.id);
  res.json({ success: result.success, message: result.message, error: result.error });
});

// POST /api/analyze/sync — permanently moved; redirect to async endpoint
// Bug 9 fix: was returning 410 Gone with no actionable redirect; now 308 Permanent Redirect.
router.post('/sync', (req, res) => {
  res.redirect(308, '/api/analyze');
});

// POST /api/analyze/chat - Interactive Q&A
router.post('/chat', async (req, res) => {
  try {
    const { question, videoContext, model = 'flash' } = req.body;
    if (!question || !question.trim()) {
      return res.status(400).json({ success: false, error: 'Question is required' });
    }

    const q = question.trim();
    const qLower = q.toLowerCase();

    // 1. Conversational greetings & system overview
    const isGreeting = /^(hi|hii|hello|hey|greetings|howdy|what'?s up|sup)(\b|[!?., ])/i.test(qLower) ||
                       /^(what are you doing|who are you|what is chorus|what can you do)/i.test(qLower);

    if (isGreeting) {
      if (videoContext && (videoContext.title || videoContext.overview)) {
        const title = videoContext.title || 'the current video';
        return res.json({
          success: true,
          answer: `Hello! I am Chorus AI. I have analyzed **${title}**. You can ask me anything about the observed events, detected objects, speech transcript, scene milestones, or forensic integrity. What would you like to know?`,
          model
        });
      } else {
        return res.json({
          success: true,
          answer: `Hello! I am Chorus AI, your multimodal video intelligence and forensic analysis platform. I can analyze uploaded video files, YouTube URLs, or live RTSP surveillance feeds to extract keyframes, transcribe speech with Whisper, detect scenes, and audit digital tamper indicators. Upload a video file or paste a link to get started!`,
          model
        });
      }
    }

    // 2. Video contextual reasoning
    if (videoContext && (videoContext.overview || videoContext.transcript || videoContext.detailed_analysis || videoContext.scenes)) {
      const { overview = '', transcript = '', scenes = [], detailed_analysis = [], vl_output = '' } = videoContext;

      // Question about what happened / summary / overview
      if (/what (happened|is happening|is going on)|summar(y|ize)|overview|tell me about/i.test(qLower)) {
        let answer = overview || 'Automated multimodal breakdown completed.';
        if (Array.isArray(detailed_analysis) && detailed_analysis.length > 0) {
          answer += '\n\n**Key Observations:**\n' + detailed_analysis.map((obs, i) => `• ${typeof obs === 'string' ? obs : (obs.detail || JSON.stringify(obs))}`).join('\n');
        }
        if (transcript && transcript !== 'Audio analysis complete.') {
          answer += `\n\n**Audio Dialogue (Whisper):** "${transcript}"`;
        }
        return res.json({ success: true, answer, model });
      }

      // Question about dialogue / speech
      if (/speak|speech|say|said|audio|transcript|talk|voice/i.test(qLower)) {
        if (transcript && transcript !== 'Audio analysis complete.') {
          return res.json({
            success: true,
            answer: `**Speech Transcript:**\n"${transcript}"`,
            model
          });
        } else {
          return res.json({
            success: true,
            answer: `No spoken audio dialogue was detected in the ingested video track.`,
            model
          });
        }
      }

      // Question about scenes or timeline
      if (/scene|timeline|chapter|timestamp|milestone/i.test(qLower)) {
        if (Array.isArray(scenes) && scenes.length > 0) {
          const sceneList = scenes.map((s, i) => `• Scene ${i + 1} (${s.start}s - ${s.end}s): ${s.label || 'Monitored window'}`).join('\n');
          return res.json({
            success: true,
            answer: `**Timeline Scene Breakdown:**\n${sceneList}`,
            model
          });
        }
      }

      // Targeted search across observations and transcript
      const words = qLower.split(/\s+/).filter(w => w.length > 3);
      const matches = [];

      if (Array.isArray(detailed_analysis)) {
        for (const item of detailed_analysis) {
          const str = typeof item === 'string' ? item : JSON.stringify(item);
          if (words.some(w => str.toLowerCase().includes(w))) {
            matches.push(str);
          }
        }
      }

      if (matches.length > 0) {
        return res.json({
          success: true,
          answer: `Regarding **"${q}"**, the analysis recorded the following evidence:\n\n` + matches.map(m => `• ${m}`).join('\n'),
          model
        });
      }

      // Default contextual synthesis
      let synthesis = overview || '';
      if (vl_output && typeof vl_output === 'string' && vl_output.length > 15) {
        synthesis = `${synthesis}\n\n**Visual Observations:** ${vl_output}`;
      }
      if (transcript && transcript !== 'Audio analysis complete.') {
        synthesis = `${synthesis}\n\n**Spoken Audio:** "${transcript}"`;
      }

      return res.json({
        success: true,
        answer: synthesis || `Analysis of the video confirms the detected timeline and scene properties. Feel free to ask about specific timestamps, audio quotes, or objects.`,
        model
      });
    }

    // 3. Fallback general assistant response
    return res.json({
      success: true,
      answer: `I am ready to analyze your video evidence. Please attach an MP4/video file, provide a YouTube URL, or connect an RTSP camera stream to generate a detailed multimodal intelligence summary and forensic timeline.`,
      model
    });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

module.exports = router;