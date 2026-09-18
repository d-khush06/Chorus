/**
 * App.jsx
 * Root application component.
 * Manages:
 *   - Case selection state
 *   - Timeline data fetching
 *   - Responsive layout state (leftCollapsed, rightDrawerOpen)
 *   - Scroll-to-scene via scene refs map
 */
import { useState, useEffect, useRef, useCallback, useContext } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { fetchCases, fetchTimeline, verifyIntegrity } from './data/api.js';
import AuthContext from './context/AuthContext';
import CaseList from './components/CaseList.jsx';
import CaseManifestPanel from './components/CaseManifestPanel.jsx';
import TimelineScrubber from './components/TimelineScrubber.jsx';
import FusedEventCard from './components/FusedEventCard.jsx';
import ConflictCard from './components/ConflictCard.jsx';
import AnalyticsPage from './pages/AnalyticsPage.jsx';
import LoginPage from './pages/LoginPage.jsx';
import HomePage from './pages/HomePage.jsx';
import './App.css';

// Private Route Wrapper
const PrivateRoute = ({ children }) => {
  const { token, loading } = useContext(AuthContext);
  if (loading) return <div style={{ color: 'white', padding: '20px' }}>Loading...</div>;
  return token ? children : <Navigate to="/login" />;
};

function EvidenceRoom() {
  const navigate = useNavigate();
  const [cases, setCases] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [timelineData, setTimelineData] = useState(null);
  const [loadingTimeline, setLoadingTimeline] = useState(false);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [isNarrow, setIsNarrow] = useState(window.innerWidth < 1200);

  // Refs map: scene_id → first DOM node for that scene
  // We register a ref per rendered card and track the first seen per scene
  const sceneRefsMap = useRef(new Map());

  // Load cases on mount
  useEffect(() => {
    fetchCases().then(data => {
      setCases(data);
      if (data.length > 0) setSelectedId(data[0].case_id);
    });
  }, []);

  // Load timeline when selection changes
  useEffect(() => {
    if (!selectedId) return;
    sceneRefsMap.current.clear();
    setLoadingTimeline(true);
    fetchTimeline(selectedId).then(data => {
      setTimelineData(data);
      setLoadingTimeline(false);
    });
  }, [selectedId]);

  // Responsive: track window width
  useEffect(() => {
    function handleResize() {
      const narrow = window.innerWidth < 1200;
      setIsNarrow(narrow);
      if (!narrow) setRightDrawerOpen(false);
      if (window.innerWidth < 900) setLeftCollapsed(true);
    }
    window.addEventListener('resize', handleResize);
    handleResize();
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleSceneClick = useCallback((scene_id) => {
    const el = sceneRefsMap.current.get(scene_id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, []);

  const handleVerify = useCallback(async () => {
    return await verifyIntegrity(selectedId);
  }, [selectedId]);

  const selectedCase = cases.find(c => c.case_id === selectedId) ?? null;

  // Build the merged timeline: interleave events and conflicts sorted by start time
  const mergedItems = buildMergedTimeline(timelineData);

  // Register ref callback — only stores the first element per scene_id
  function makeRefCallback(sceneId, isFirstForScene) {
    if (!isFirstForScene) return undefined;
    return (el) => {
      if (el) sceneRefsMap.current.set(sceneId, el);
      else sceneRefsMap.current.delete(sceneId);
    };
  }

  // Determine which scene IDs have already been registered (to know "first" per scene)
  const seenScenes = new Set();

  const { logout } = useContext(AuthContext);

  return (
    <div
      className={[
        'app-shell',
        leftCollapsed ? 'left-collapsed' : '',
        isNarrow ? 'right-drawer' : '',
      ].filter(Boolean).join(' ')}
    >
      {/* ── Left Sidebar: Case List ── */}
      <CaseList
        cases={cases}
        selectedId={selectedId}
        collapsed={leftCollapsed}
        onSelect={(id) => { setSelectedId(id); setRightDrawerOpen(false); }}
        onToggle={() => setLeftCollapsed(v => !v)}
      />

      {/* ── Main Pane ── */}
      <main className="main-pane" aria-label="Case review">
        {/* Modern Header bar */}
        <div className="main-pane__header">
          <div className="main-pane__header-left">
            <button
              className="ev-back-btn"
              onClick={(e) => {
                e.preventDefault();
                navigate('/analytics');
                setTimeout(() => {
                  if (window.location.pathname !== '/analytics') {
                    window.location.href = '/analytics';
                  }
                }, 50);
              }}
              title="Return to AI Chat & Cyber Mode"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
              <span>AI Chat & Cyber</span>
            </button>

            <div className="ev-brand-pill">
              <span className="ev-brand-title">Chorus</span>
              <span className="ev-brand-sub">Evidence Room</span>
            </div>

            {selectedCase && (
              <div className="ev-case-pill">
                <span className="ev-case-label">{selectedCase.case_id}</span>
                {selectedCase.title && <span className="ev-case-name">— {selectedCase.title}</span>}
              </div>
            )}
          </div>

          <div className="main-pane__header-actions">
            {timelineData?.conflicts?.length > 0 && (
              <span className="conflict-count-badge">
                ⚑ {timelineData.conflicts.length} Conflict{timelineData.conflicts.length !== 1 ? 's' : ''}
              </span>
            )}

            {isNarrow && selectedCase && (
              <button
                className="manifest-drawer-toggle"
                onClick={() => setRightDrawerOpen(v => !v)}
                aria-label="Toggle manifest panel"
                aria-expanded={rightDrawerOpen}
              >
                Manifest
              </button>
            )}

            <div className="ev-user-badge">
              <span>{useContext(AuthContext).user?.email?.split('@')[0] || 'User'}</span>
              <button
                className="ev-signout-btn"
                onClick={() => { logout(); navigate('/'); }}
              >
                Sign Out
              </button>
            </div>
          </div>
        </div>

        {/* Timeline scrubber */}
        <TimelineScrubber
          fusedTimeline={timelineData?.fused_timeline ?? []}
          conflicts={timelineData?.conflicts ?? []}
          onSceneClick={handleSceneClick}
        />

        {/* Fused timeline event list */}
        <div className="timeline-list" role="feed" aria-label="Fused timeline" aria-busy={loadingTimeline}>
          {loadingTimeline && (
            <div className="timeline-list__loading">
              <span className="mono text-3">Loading timeline…</span>
            </div>
          )}

          {!loadingTimeline && mergedItems.length === 0 && (
            <div className="timeline-list__empty">
              <span className="mono text-3">No timeline events for this case.</span>
            </div>
          )}

          {!loadingTimeline && mergedItems.map((item, idx) => {
            if (item.kind === 'conflict') {
              const isFirst = !seenScenes.has(`c-${item.data.scene_id}-${item.data.conflict_type}`);
              if (isFirst) seenScenes.add(`c-${item.data.scene_id}-${item.data.conflict_type}`);
              const refCb = isFirst ? makeRefCallback(item.data.scene_id, !seenScenes.has(`seen-${item.data.scene_id}`)) : undefined;
              if (!seenScenes.has(`seen-${item.data.scene_id}`)) seenScenes.add(`seen-${item.data.scene_id}`);
              return (
                <ConflictCard
                  key={`conflict-${idx}`}
                  conflict={item.data}
                  eventRef={refCb}
                />
              );
            }
            // Regular event
            const sceneId = item.data.scene_id;
            const isFirstForScene = !seenScenes.has(`seen-${sceneId}`);
            if (isFirstForScene) seenScenes.add(`seen-${sceneId}`);
            return (
              <FusedEventCard
                key={`event-${idx}`}
                event={item.data}
                eventRef={isFirstForScene ? makeRefCallback(sceneId, true) : undefined}
              />
            );
          })}
        </div>
      </main>

      {/* ── Right Sidebar: Manifest Panel (inline mode) ── */}
      {!isNarrow && (
        <CaseManifestPanel
          caseData={selectedCase}
          onVerify={handleVerify}
        />
      )}

      {/* ── Right Drawer (narrow screens) ── */}
      {isNarrow && (
        <>
          <div
            className={`right-drawer-overlay${rightDrawerOpen ? ' visible active' : ''}`}
            onClick={() => setRightDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className={`right-drawer-panel${rightDrawerOpen ? ' open' : ''}`}>
            <CaseManifestPanel
              caseData={selectedCase}
              onVerify={handleVerify}
            />
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Merge fused_timeline events and conflicts into a single sorted list.
 * Conflicts are inserted inline at their start time position.
 * Items of the same start time: events first, then conflicts.
 */
function buildMergedTimeline(timelineData) {
  if (!timelineData) return [];

  const events = (timelineData.fused_timeline ?? []).map(e => ({
    kind: 'event',
    t: e.start_seconds,
    data: e,
  }));

  const conflicts = (timelineData.conflicts ?? []).map(c => ({
    kind: 'conflict',
    t: c.time_range[0],
    data: c,
  }));

  const merged = [...events, ...conflicts];
  merged.sort((a, b) => a.t - b.t || (a.kind === 'conflict' ? 1 : -1));
  return merged;
}

export default function App() {
  const navigate = useNavigate();
  return (
    <div className="global-app-container">
      {/* Global Background Ambient Orbs */}
      <div className="global-bg-orb orb-1"></div>
      <div className="global-bg-orb orb-2"></div>
      
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<LoginPage />} />
        <Route path="/analytics" element={
          <PrivateRoute>
            <AnalyticsPage onBack={() => navigate('/evidence')} />
          </PrivateRoute>
        } />
        <Route path="/evidence" element={
          <PrivateRoute>
            <EvidenceRoom />
          </PrivateRoute>
        } />
        <Route path="/" element={<HomePage />} />
      </Routes>
    </div>
  );
}
