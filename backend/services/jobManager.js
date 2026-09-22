const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');
const { EventEmitter } = require('events');
const { getSSEHub } = require('./sseHub');
const { maskRtspUrl } = require('./maskRtspUrl');
const { formatRunResult } = require('./outputFormatter');

const RUNS_DIR = path.join(__dirname, '../data/runs');
const MAX_CONCURRENT_RUNS = 2;

if (!fs.existsSync(RUNS_DIR)) {
  fs.mkdirSync(RUNS_DIR, { recursive: true });
}

class JobManager extends EventEmitter {
  constructor() {
    super();
    this.queue = [];
    this.running = new Map();
    this.runs = new Map();
    this.loadPersistedRuns();
  }

  loadPersistedRuns() {
    try {
      const files = fs.readdirSync(RUNS_DIR).filter(f => f.endsWith('.json') && !f.startsWith('pipeline-out-'));
      for (const file of files) {
        const runPath = path.join(RUNS_DIR, file);
        const runData = JSON.parse(fs.readFileSync(runPath, 'utf-8'));
        if (runData.status === 'running' || runData.status === 'queued') {
          runData.status = 'failed';
          runData.error = 'Server restarted while run was in progress';
          runData.pid = null;
          runData.completed_at = new Date().toISOString();
          // Persist the corrected status back to disk
          fs.writeFileSync(runPath, JSON.stringify(runData, null, 2));
        }
        this.runs.set(runData.id, runData);
      }
      console.log(`[JobManager] Loaded ${this.runs.size} persisted runs (running/queued cleared to failed)`);
    } catch (err) {
      console.error('[JobManager] Failed to load persisted runs:', err.message);
    }
  }

  persistRun(run) {
    try {
      const runPath = path.join(RUNS_DIR, `${run.id}.json`);
      fs.writeFileSync(runPath, JSON.stringify(run, null, 2));
    } catch (err) {
      console.error('[JobManager] Failed to persist run:', err.message);
    }
  }

  deletePersistedRun(runId) {
    try {
      const runPath = path.join(RUNS_DIR, `${runId}.json`);
      if (fs.existsSync(runPath)) {
        fs.unlinkSync(runPath);
      }
    } catch (err) {
      console.error('[JobManager] Failed to delete persisted run:', err.message);
    }
  }

  generateRunId() {
    return crypto.randomUUID();
  }

  createRun(options) {
    const runId = this.generateRunId();
    const run = {
      id: runId,
      mode: options.mode || 'general',
      model: options.model || 'flash',
      source_type: options.source_type || 'local_upload',
      entry_point: options.entry_point || 'forensic',
      case_id: options.case_id || null,
      notes: options.notes || '',
      videoPath: options.videoPath || null,
      url: options.url || null,
      prompt: options.prompt || '',
      rawHash: options.rawHash || '',   // Bug 10 fix: was never stored
      status: 'queued',
      created_at: new Date().toISOString(),
      started_at: null,
      completed_at: null,
      pid: null,
      exit_code: null,
      error: null,
      stage_manifest: [],
      current_stage: null,
      progress: 0
    };
    this.runs.set(runId, run);
    this.persistRun(run);
    this.queue.push(runId);
    this.processQueue();
    return run;
  }

  getRun(runId) {
    return this.runs.get(runId) || null;
  }

  getAllRuns() {
    return Array.from(this.runs.values()).sort((a, b) => 
      new Date(b.created_at) - new Date(a.created_at)
    );
  }

  async processQueue() {
    if (this.running.size >= MAX_CONCURRENT_RUNS) return;
    if (this.queue.length === 0) return;

    const runId = this.queue.shift();
    const run = this.runs.get(runId);
    if (!run || run.status !== 'queued') {
      this.processQueue();
      return;
    }

    await this.startRun(runId);
    this.processQueue();
  }

  async startRun(runId) {
    const run = this.runs.get(runId);
    if (!run) return;

    run.status = 'running';
    run.started_at = new Date().toISOString();
    this.persistRun(run);
    this.running.set(runId, run);
    this.emit('run:started', run);

    const repoRoot = path.resolve(__dirname, '../../');
    const runnerScript = path.join(repoRoot, 'pipeline_runner.py');
    const outputFile = path.join(RUNS_DIR, `pipeline-out-${runId}.json`);

    // Resolve Python executable: env var > `python` on PATH > py launcher
    function getPythonExecutable() {
      const { execSync } = require('child_process');

      // 1. Explicit env override
      if (process.env.PYTHON_PATH && fs.existsSync(process.env.PYTHON_PATH)) {
        return process.env.PYTHON_PATH;
      }

      // 2. Ask `python` to self-report its path (works when python is on PATH)
      try {
        const pyPath = execSync('python -c "import sys; print(sys.executable)"', {
          encoding: 'utf-8',
          timeout: 5000
        }).trim();
        if (pyPath && fs.existsSync(pyPath)) return pyPath;
      } catch (e) {}

      // 3. Try Windows py launcher as last resort
      try {
        const pyPath = execSync('py -3 -c "import sys; print(sys.executable)"', {
          encoding: 'utf-8',
          timeout: 5000
        }).trim();
        if (pyPath && fs.existsSync(pyPath)) return pyPath;
      } catch (e) {}

      return 'python';
    }

    const pythonExe = getPythonExecutable();

    // Flash model = skip heavy LLM stages for speed:
    //   --skip-asr  → no Whisper transcription
    //   --skip-vl   → no VL vision-language model (frame-by-frame captioning)
    //   --skip-output → no Qwen2.5-7B domain output LLM
    // Deepthink = full pipeline (all stages)
    const isFlash = !run.model || run.model === 'flash';

    const args = [
      runnerScript,
      '--mode', run.mode,
      '--question', run.prompt || 'Analyze this video for forensic evidence.',
      '--output-file', outputFile,
      '--fast',
      '--skip-dedup',
      '--pretty',
      '--emit-events'
    ];

    // Flash model: skip ASR + domain LLM but keep VL for visual descriptions
    if (isFlash) {
      args.push('--skip-asr');    // skip Whisper ASR (~30-90s)
      // VL runs so we get actual visual frame descriptions
      args.push('--skip-output'); // skip Qwen 7B domain output LLM (~30-60s)
    }

    if (run.videoPath) {
      args.push('--video', run.videoPath);
      args.push('--source-type', run.source_type);
    } else if (run.url) {
      args.push('--url', run.url);
      args.push('--source-type', run.source_type);
    }

    if (run.case_id) {
      args.push('--case-id', run.case_id);
    }
    if (run.entry_point) {
      args.push('--entry-point', run.entry_point);
    }

    const pyArgs = ['-u', ...args];
    console.log(`[JobManager] Spawning run ${runId}: ${pythonExe} ${maskRtspUrl(pyArgs.slice(1).join(' '))}`);

    const env = {
      ...process.env,
      CHORUS_FAST_ROUTING: '1',
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
      PYTHONUNBUFFERED: '1'
    };

    const pyProcess = spawn(pythonExe, pyArgs, { 
      cwd: repoRoot, 
      env,
      shell: false,
      windowsHide: true
    });

    run.pid = pyProcess.pid;
    this.persistRun(run);

    let stdout = '';
    let stderr = '';

    pyProcess.stdout.on('data', (data) => {
      const chunk = data.toString('utf-8');
      stdout += chunk;
      this.handlePipelineOutput(runId, chunk);
    });

    pyProcess.stderr.on('data', (data) => {
      stderr += data.toString('utf-8');
    });

    pyProcess.on('close', (code) => {
      run.exit_code = code;
      run.completed_at = new Date().toISOString();
      run.pid = null;
      
      const elapsedSeconds = run.started_at 
        ? ((Date.now() - new Date(run.started_at).getTime()) / 1000).toFixed(1) 
        : null;

      let pipelineResult = null;
      if (fs.existsSync(outputFile)) {
        try {
          pipelineResult = JSON.parse(fs.readFileSync(outputFile, 'utf-8'));
          run.pipelineResult = pipelineResult;
          run.result = formatRunResult(run, pipelineResult, elapsedSeconds);
        } catch (e) {
          console.error('[JobManager] Error parsing output file:', e.message);
        }
      }

      if (code === 0 && run.result) {
        run.status = 'completed';
        run.progress = 100;
        getSSEHub().emit(runId, {
          type: 'RUN_COMPLETED',
          status: 'completed',
          result: run.result,
          run: this.serializeRun(run)
        });
      } else if (run.result) {
        // Soft completion if output was generated despite nonzero exit code
        run.status = 'completed';
        run.progress = 100;
        getSSEHub().emit(runId, {
          type: 'RUN_COMPLETED',
          status: 'completed',
          result: run.result,
          run: this.serializeRun(run)
        });
      } else {
        run.status = 'failed';
        run.error = stderr.slice(-500) || 'Pipeline failed';
        getSSEHub().emit(runId, {
          type: 'RUN_FAILED',
          status: 'failed',
          error: run.error,
          run: this.serializeRun(run)
        });
      }
      
      this.running.delete(runId);
      this.persistRun(run);
      this.emit('run:completed', { run, code, stdout, stderr });
      this.processQueue();
    });

    pyProcess.on('error', (err) => {
      run.status = 'failed';
      run.error = err.message;
      run.completed_at = new Date().toISOString();
      getSSEHub().emit(runId, {
        type: 'RUN_FAILED',
        status: 'failed',
        error: err.message,
        run: this.serializeRun(run)
      });
      this.running.delete(runId);
      this.persistRun(run);
      this.emit('run:error', { run, error: err });
      this.processQueue();
    });
  }

  handlePipelineOutput(runId, chunk) {
    const run = this.runs.get(runId);
    if (!run) return;

    const lines = chunk.trim().split('\n');
    for (const line of lines) {
      if (line.startsWith('STAGE_EVENT:')) {
        try {
          const event = JSON.parse(line.substring('STAGE_EVENT:'.length));
          this.handleStageEvent(runId, event);
        } catch (e) {}
      } else if (line.startsWith('TOOL_CALL:')) {
        // Hermes-style tool-call events — forward to SSE stream
        try {
          const event = JSON.parse(line.substring('TOOL_CALL:'.length));
          getSSEHub().emit(runId, { type: 'TOOL_CALL', data: event });
        } catch (e) {}
      } else if (line.startsWith('CHUNK_EVENT:')) {
        try {
          const event = JSON.parse(line.substring('CHUNK_EVENT:'.length));
          getSSEHub().emit(runId, { type: 'chunk', data: event });
        } catch (e) {}
      } else if (line.startsWith('OBSERVATION_EVENT:')) {
        try {
          const event = JSON.parse(line.substring('OBSERVATION_EVENT:'.length));
          getSSEHub().emit(runId, { type: 'observation', data: event });
        } catch (e) {}
      } else if (line.startsWith('ALERT_EVENT:')) {
        try {
          const event = JSON.parse(line.substring('ALERT_EVENT:'.length));
          getSSEHub().emit(runId, { type: 'alert', data: event });
        } catch (e) {}
      }
    }
  }

  handleStageEvent(runId, event) {
    const run = this.runs.get(runId);
    if (!run) return;

    if (event.type === 'manifest') {
      run.stage_manifest = event.stages || [];
      run.current_stage = run.stage_manifest[0]?.name || null;
    } else if (event.type === 'start') {
      const stage = run.stage_manifest.find(s => s.name === event.stage);
      if (stage) {
        stage.status = 'running';
        stage.started_at = new Date().toISOString();
      }
      run.current_stage = event.stage;
    } else if (event.type === 'complete') {
      const stage = run.stage_manifest.find(s => s.name === event.stage);
      if (stage) {
        stage.status = 'completed';
        stage.completed_at = new Date().toISOString();
        stage.result = event.result;
      }
      const nextStage = run.stage_manifest.find(s => s.status === 'pending');
      run.current_stage = nextStage?.name || null;
      run.progress = Math.round(
        (run.stage_manifest.filter(s => s.status === 'completed').length / 
         run.stage_manifest.length) * 100
      );
    } else if (event.type === 'skip') {
      const stage = run.stage_manifest.find(s => s.name === event.stage);
      if (stage) {
        stage.status = 'skipped';
        stage.reason = event.reason;
      }
      run.progress = Math.round(
        (run.stage_manifest.filter(s => ['completed', 'skipped'].includes(s.status)).length / 
         run.stage_manifest.length) * 100
      );
    }

    this.persistRun(run);
    getSSEHub().emit(runId, {
      type: 'STAGE_EVENT',
      stage: run.current_stage,
      stages: run.stage_manifest,
      progress: run.progress,
      event: event,
      run: this.serializeRun(run)
    });
  }

  cancelRun(runId) {
    const run = this.runs.get(runId);
    if (!run) return { success: false, error: 'Run not found' };

    try {
      const { getRelayService } = require('./relayService');
      getRelayService().stopRelay(runId);
    } catch (e) {}

    if (run.status === 'queued') {
      const idx = this.queue.indexOf(runId);
      if (idx !== -1) this.queue.splice(idx, 1);
      run.status = 'cancelled';
      run.completed_at = new Date().toISOString();
      this.persistRun(run);
      this.emit('run:cancelled', run);
      return { success: true };
    }

    if (run.status === 'running' && run.pid) {
      try {
        // Bug 3 fix: cross-platform process kill
        // Windows uses taskkill to recursively kill the Python process tree.
        // Linux/macOS use the native process.kill() with SIGKILL.
        if (process.platform === 'win32') {
          const { spawn } = require('child_process');
          const kill = spawn('taskkill', ['/PID', String(run.pid), '/T', '/F'], { windowsHide: true });
          kill.on('close', () => {
            run.status = 'cancelled';
            run.completed_at = new Date().toISOString();
            run.pid = null;
            this.running.delete(runId);
            this.persistRun(run);
            this.emit('run:cancelled', run);
          });
        } else {
          // Linux / macOS — kill the process group to terminate child processes too
          try {
            process.kill(-run.pid, 'SIGKILL');  // negative PID = entire process group
          } catch (_) {
            process.kill(run.pid, 'SIGKILL');   // fallback: kill just the PID
          }
          run.status = 'cancelled';
          run.completed_at = new Date().toISOString();
          run.pid = null;
          this.running.delete(runId);
          this.persistRun(run);
          this.emit('run:cancelled', run);
        }
        return { success: true, message: 'Kill signal sent' };
      } catch (err) {
        return { success: false, error: err.message };
      }
    }

    return { success: false, error: 'Run not cancellable in current state' };
  }

  serializeRun(run) {
    return {
      id: run.id,
      mode: run.mode,
      source_type: run.source_type,
      entry_point: run.entry_point,
      case_id: run.case_id,
      url: run.url ? maskRtspUrl(run.url) : null,
      status: run.status,
      created_at: run.created_at,
      started_at: run.started_at,
      completed_at: run.completed_at,
      progress: run.progress,
      current_stage: run.current_stage,
      stage_manifest: run.stage_manifest,
      error: run.error
    };
  }
}

let jobManagerInstance = null;

function getJobManager() {
  if (!jobManagerInstance) {
    jobManagerInstance = new JobManager();
  }
  return jobManagerInstance;
}

module.exports = { JobManager, getJobManager, RUNS_DIR, MAX_CONCURRENT_RUNS };