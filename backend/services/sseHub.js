const { EventEmitter } = require('events');

class SSEHub extends EventEmitter {
  constructor() {
    super();
    this.connections = new Map();
    this.eventHistory = new Map();
    this.maxHistoryPerRun = 500;
  }

  addConnection(runId, req, res) {
    if (!this.connections.has(runId)) {
      this.connections.set(runId, new Set());
    }
    this.connections.get(runId).add(res);

    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    res.flushHeaders();

    const lastEventId = req.headers['last-event-id'];
    if (lastEventId && this.eventHistory.has(runId)) {
      const history = this.eventHistory.get(runId);
      const idx = history.findIndex(e => e.id === lastEventId);
      if (idx !== -1) {
        for (let i = idx + 1; i < history.length; i++) {
          this.sendEvent(res, history[i]);
        }
      }
    }

    this.sendEvent(res, { type: 'connected', runId, timestamp: new Date().toISOString() });

    req.on('close', () => {
      this.removeConnection(runId, res);
    });
  }

  removeConnection(runId, res) {
    const conns = this.connections.get(runId);
    if (conns) {
      conns.delete(res);
      if (conns.size === 0) {
        this.connections.delete(runId);
      }
    }
  }

  emit(runId, event) {
    const eventWithMeta = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      timestamp: new Date().toISOString(),
      ...event
    };

    if (!this.eventHistory.has(runId)) {
      this.eventHistory.set(runId, []);
    }
    const history = this.eventHistory.get(runId);
    history.push(eventWithMeta);
    if (history.length > this.maxHistoryPerRun) {
      history.shift();
    }

    const conns = this.connections.get(runId);
    if (conns) {
      for (const res of conns) {
        this.sendEvent(res, eventWithMeta);
      }
    }
  }

  sendEvent(res, event) {
    const data = `data: ${JSON.stringify(event)}\n\n`;
    try {
      res.write(data);
    } catch (err) {
      // Connection likely closed
    }
  }

  getHistory(runId, sinceId = null) {
    const history = this.eventHistory.get(runId) || [];
    if (!sinceId) return history;
    const idx = history.findIndex(e => e.id === sinceId);
    return idx !== -1 ? history.slice(idx + 1) : history;
  }
}

let sseHubInstance = null;

function getSSEHub() {
  if (!sseHubInstance) {
    sseHubInstance = new SSEHub();
  }
  return sseHubInstance;
}

module.exports = { SSEHub, getSSEHub };