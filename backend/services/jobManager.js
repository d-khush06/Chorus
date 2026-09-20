const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');
const { EventEmitter } = require('events');
const { getSSEHub } = require('./sseHub');
const { maskRtspUrl } = require('./maskRtspUrl');

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
      const files = fs.readdirSync(RUNS_DIR).filter(f => f.endsWith('.json'));
      for (const file of files) {
        const runPath = path.join(RUNS_DIR, file);
        const runData = JSON.parse(fs.readFileSync(runPath, 'utf-8'));
        this.runs.set(runData.id, runData);
      }
      console.log(`[JobManager] Loaded ${this.runs.size} persisted runs`);
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
      source_type: options.source_type || 'local_upload',
      entry_point: options.entry_point || 'forensic',
      case_id: options.case_id || null,
      notes: options.notes || '',
      videoPath: options.videoPath || null,
      url: options.url || null,
      prompt: options.prompt || '',
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

    const PYTHON_CANDIDATES = [
      process.env.PYTHON_PATH,
      'C:\\Users\\mpdell43212p\\AppData\\Local\\Programs\\Python\\Python312\\python.exe',
      'C:\\Users\\DELL\\AppData\\Local\\Programs\\Python\\Python311\\python.exe',
      'python',
      'python3'
    ].filter(Boolean);

    function getPythonExecutable() {
      for (const p of PYTHON_CANDIDATES) {
        if (p === 'python' || p === 'python3' || fs.existsSync(p)) {
          return p;
        }
      }
      return 'python';
    }

    const pythonExe = getPythonExecutable();

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
      
      if (code === 0) {
        run.status = 'completed';
        run.progress = 100;
      } else {
        run.status = 'failed';
        run.error = stderr.slice(-500) || 'Pipeline failed';
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
    getSSEHub().emit(runId, { type: 'stage', data: event, run: this.serializeRun(run) });
  }

  cancelRun(runId) {
    const run = this.runs.get(runId);
    if (!run) return { success: false, error: 'Run not found' };

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