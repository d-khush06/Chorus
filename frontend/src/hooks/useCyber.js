import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../context/AuthContext';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000';

export function useJob() {
  const { token } = useAuth();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchJobs = useCallback(async () => {
    if (!token) return;
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/analyze/runs`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to fetch jobs');
      const data = await res.json();
      setJobs(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  const createJob = useCallback(async (options) => {
    if (!token) throw new Error('Not authenticated');
    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(options)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Failed to create job');
    }
    return res.json();
  }, [token]);

  const getJob = useCallback(async (runId) => {
    if (!token) throw new Error('Not authenticated');
    const res = await fetch(`${API_BASE}/api/analyze/runs/${runId}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error('Job not found');
    return res.json();
  }, [token]);

  const cancelJob = useCallback(async (runId) => {
    if (!token) throw new Error('Not authenticated');
    const res = await fetch(`${API_BASE}/api/analyze/runs/${runId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error('Failed to cancel job');
    return res.json();
  }, [token]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  return { jobs, loading, error, fetchJobs, createJob, getJob, cancelJob };
}

export function useSSE(runId, options = {}) {
  const { token } = useAuth();
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  const eventSourceRef = useRef(null);
  const lastEventIdRef = useRef(options.lastEventId || null);

  const connect = useCallback(() => {
    let isCancelled = false;

    async function initEventSource() {
      try {
        let ticketParam = '';
        if (token) {
          try {
            const ticketRes = await fetch(`${API_BASE}/api/auth/stream-ticket`, {
              method: 'POST',
              headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
              },
              body: JSON.stringify({ resourceId: runId })
            });
            if (ticketRes.ok) {
              const ticketData = await ticketRes.json();
              if (ticketData.ticket) {
                ticketParam = `ticket=${encodeURIComponent(ticketData.ticket)}`;
              }
            }
          } catch (tErr) {
            console.warn('[useSSE] Ticket fetch failed, attempting without ticket:', tErr);
          }
        }

        if (isCancelled) return;

        const url = new URL(`${API_BASE}/api/analyze/runs/${runId}/events`);
        if (ticketParam) {
          url.searchParams.set('ticket', ticketParam.replace('ticket=', ''));
        }
        if (lastEventIdRef.current) {
          url.searchParams.set('lastEventId', lastEventIdRef.current);
        }

        const es = new EventSource(url.toString());
        eventSourceRef.current = es;

        es.onopen = () => {
          setConnected(true);
          setError(null);
        };

        es.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.id) lastEventIdRef.current = data.id;
            setEvents(prev => [...prev.slice(-499), data]);
            options.onEvent?.(data);
          } catch (err) {
            console.warn('SSE parse error:', err);
          }
        };

        es.onerror = (err) => {
          setConnected(false);
          if (es.readyState === EventSource.CLOSED) {
            setError('Connection closed');
            options.onError?.(err);
          }
        };
      } catch (err) {
        setError(err.message);
      }
    }

    initEventSource();

    return () => {
      isCancelled = true;
    };
  }, [token, runId, options]);

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      setConnected(false);
    }
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  return { events, connected, error, clearEvents, reconnect: connect };
}

export function useStreamTicket(resourceId) {
  const { token } = useAuth();
  const [ticket, setTicket] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchTicket = useCallback(async () => {
    if (!token || !resourceId) return;
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/auth/stream-ticket`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ resourceId })
      });
      if (!res.ok) throw new Error('Failed to get stream ticket');
      const data = await res.json();
      setTicket(data.ticket);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, resourceId]);

  useEffect(() => {
    fetchTicket();
    // Auto-refresh ticket before expiry (every 10 minutes)
    const interval = setInterval(fetchTicket, 10 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchTicket]);

  return { ticket, loading, error, refresh: fetchTicket };
}