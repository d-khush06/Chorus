# Chorus Cyber Mode — Full Transformation Plan

## Phase 0 Report + Design System + Static Layouts

---

## PHASE 0 REPORT

### (a) Hardcoded Data Audit

| Item | Location | Status | Source |
|------|----------|--------|--------|
| **"3 Cases"** badge | `ChatGPTGeneralView.jsx:1406` | **HARDCODED** | Literal string `"3 Cases"` in JSX. Not derived from state or API. |
| **"Executive Briefing Q3 — Revenue & Growth"** | `ChatGPTGeneralView.jsx:76` | **HARDCODED** | In `INITIAL_HISTORY` array (line 76), a static seed object. |
| **"CR-889 — CCTV Perimeter Tamper Audit"** | `ChatGPTGeneralView.jsx:23` | **HARDCODED** | In `INITIAL_HISTORY` array (line 23), a static seed object. |
| **"Synthetic Voice & Deepfake Screen"** | `ChatGPTGeneralView.jsx:142` | **HARDCODED** | In `INITIAL_HISTORY` array (line 142), a static seed object. |
| **"Flash" model chip** | `ChatGPTGeneralView.jsx:599` | **HARDCODED** | Ternary `selectedModel === 'deepthink' ? 'Deepthink' : 'Flash'` in UI text. Labels "Chorus Flash" (line 613) and "Chorus Deepthink" (line 626) are also hardcoded strings, not from run metadata. |
| **"Chorus Flash" / "Chorus Deepthink"** labels | `ChatGPTGeneralView.jsx:735,1172,1185,1245,1247,1926,2049,2180,2251` | **HARDCODED** | All model name strings are static. No backend metadata drives these labels. |
| **INITIAL_HISTORY** (all 5 entries) | `ChatGPTGeneralView.jsx:20-165` | **HARDCODED** | 5 fully fabricated investigation/analysis sessions with fake data (threat scores, anomalies, summaries). |

**Verdict:** The sidebar history, model chip, "3 Cases" badge, and all summary data in INITIAL_HISTORY are hardcoded mock data. The new UI must remove all of this and use only backend-sourced data or explicit empty/"not connected" states.

### (b) Build / Test / Vite Verification

```
npm run build → ✓ built in 3.53s (Vite 6.4.3)
  dist/index.html         1.12 kB
  dist/assets/index.css  94.25 kB
  dist/assets/index.js  326.43 kB

npm run test → 1 passed (Smoke.test.jsx)

npm ls vite → Single Vite version: 6.4.3
  ├── vite@6.4.3
  ├── @vitejs/plugin-react@4.7.0 → vite@6.4.3 (deduped)
  └── vitest@5.0.1 → vite@6.4.3 (deduped)
```

### (c) Route Regression Confirmation

| Route | Component | Status |
|-------|-----------|--------|
| `/` | `HomePage` | ✅ Unchanged |
| `/login` | `LoginPage` | ✅ Unchanged |
| `/evidence` | `EvidenceRoom` | ✅ Unchanged |
| `/analytics` | `AnalyticsPage` → `ChatGPTGeneralView` | ✅ Unchanged |

All four existing routes remain functional and unmodified.

### (d) VL Latency & Concurrency (for Live Watch refresh rate)

From `benchmark_vl_concurrency.py` docstring and `test_vl_worker_pool.py`:
- **Measured VL latency:** Not directly benchmarked for single-frame latency in the existing files. The benchmark measures *throughput* at concurrency levels (0.58–0.92 vids/s for 2–4 concurrent).
- **Safe concurrency:** `max_concurrent=4` on the tested GPU (8–10 GB VRAM, OOM at 6).
- **For Live Watch:** Since the pipeline processes chunks (not individual frames), and the VL engine handles batched frames, a **30-second chunk interval** is appropriate — matching the existing CHUNK_EVENT cadence. The UI should poll/refresh observations on each chunk boundary, not per-frame.

---

## DESIGN SYSTEM

### Tokens (Exact Values — No #000000 or #FFFFFF)

#### Light Theme `[data-theme="light"]`
| Token | Value | Usage |
|-------|-------|-------|
| `--cyber-bg` | `#F5F3EE` | Page background |
| `--cyber-surface` | `#E8E3D2` | Sidebar, cards |
| `--cyber-border` | `#DCD7C6` | Borders, dividers |
| `--cyber-text` | `#141413` | Primary text |
| `--cyber-text-secondary` | `#5E5D59` | Secondary text, labels |
| `--cyber-accent` | `#C15F3C` | Buttons, active tabs, focus rings, LIVE dot |

#### Dark Theme `[data-theme="dark"]`
| Token | Value | Usage |
|-------|-------|-------|
| `--cyber-bg` | `#191816` | Page background |
| `--cyber-surface` | `#1A1A18` | Sidebar, cards |
| `--cyber-border` | `#30302E` | Borders, dividers |
| `--cyber-text` | `#FAF9F5` | Primary text |
| `--cyber-text-secondary` | `#B0AEA5` | Secondary text, labels |
| `--cyber-accent` | `#D97757` | Buttons, active tabs, focus rings, LIVE dot |

#### Semantic Status Colors (Extension — Needs Approval)
| Status | Light | Dark | Icon |
|--------|-------|------|------|
| `ok` | `#4A7C59` on `#E8E3D2` bg | `#6B9E7A` on `#1A1A18` bg | ✓ shield-check |
| `warning` | `#B8860B` on `#E8E3D2` bg | `#D4A843` on `#1A1A18` bg | ⚠ alert-triangle |
| `danger` | `#A63D40` on `#E8E3D2` bg | `#D46A6D` on `#1A1A18` bg | ✕ shield-alert (distinct from accent terracotta) |
| `info` | `#4A6FA5` on `#E8E3D2` bg | `#7B9CC4` on `#1A1A18` bg | ℹ info |

**Danger vs Accent distinction:** Danger uses a cooler, more saturated red (`#A63D40` light / `#D46A6D` dark) while accent is warm terracotta (`#C15F3C` / `#D97757`). The hue difference (~15°) ensures visual separation.

### Typography
- **Headings:** Source Serif 4 (fallback: Georgia) — loaded via Google Fonts in `index.html`
- **UI text:** Inter (already loaded)
- **Data/timestamps/hashes:** JetBrains Mono (already loaded) with `font-variant-numeric: tabular-nums`

### Spacing & Radius
- 4px grid: `4, 8, 12, 16, 20, 24, 32, 40, 48, 64`
- Cards: `border-radius: 12px`
- Controls: `border-radius: 8px`
- Dividers: `1px` hairline

### Motion
- Transitions: `150ms ease` (default), `200ms ease` (page transitions)
- LIVE dot: `@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } } 1.5s ease-in-out infinite`
- `prefers-reduced-motion: reduce` → disable all animations

### Shadows
- Soft warm: `rgba(20, 20, 19, 0.08)` — prefer borders over shadows

### Implementation
- CSS variables per theme under `[data-theme="light"]` and `[data-theme="dark"]`
- Default from `prefers-color-scheme`, manual toggle persisted in `localStorage('cyber-theme')`
- Tailwind v3 config: map tokens via `rgb(var(--cyber-token) / <alpha-value>)`
- **Preflight remains disabled globally**; base styles scoped under `.cyber-console` wrapper
- Scope existing pages to NOT be affected by new cyber styles

---

## FILE PLAN

### Phase 0 — Design Tokens + Primitives + Static Layouts

| # | File | Action |
|---|------|--------|
| 1 | `frontend/index.html` | Add Source Serif 4 font link |
| 2 | `frontend/src/styles/cyber-tokens.css` | NEW — CSS variables for both themes |
| 3 | `frontend/tailwind.config.js` | Extend with cyber token colors via CSS variable references |
| 4 | `frontend/src/components/cyber/primitives/Card.jsx` | NEW — Card primitive |
| 5 | `frontend/src/components/cyber/primitives/Badge.jsx` | NEW — Badge primitive |
| 6 | `frontend/src/components/cyber/primitives/Button.jsx` | NEW — Button primitive |
| 7 | `frontend/src/components/cyber/primitives/Tabs.jsx` | NEW — Tabs primitive |
| 8 | `frontend/src/components/cyber/primitives/StatusPill.jsx` | NEW — StatusPill primitive |
| 9 | `frontend/src/components/cyber/primitives/EmptyState.jsx` | NEW — EmptyState primitive |
| 10 | `frontend/src/components/cyber/primitives/ErrorState.jsx` | NEW — ErrorState primitive |
| 11 | `frontend/src/components/cyber/primitives/Skeleton.jsx` | NEW — Skeleton loading primitive |
| 12 | `frontend/src/components/cyber/primitives/ThemeToggle.jsx` | NEW — Light/dark toggle |
| 13 | `frontend/src/components/cyber/primitives/index.js` | NEW — barrel export |
| 14 | `frontend/src/components/cyber/CyberLayout.jsx` | NEW — shared shell (top bar, tabs, back, theme, status) |
| 15 | `frontend/src/components/cyber/LiveWatchPage.jsx` | NEW — static layout (no data) |
| 16 | `frontend/src/components/cyber/ForensicPage.jsx` | NEW — static layout (no data) |
| 17 | `frontend/src/components/cyber/TracePage.jsx` | NEW — static layout (no data) |
| 18 | `frontend/src/components/cyber/CyberLanding.jsx` | NEW — 3-card landing |
| 19 | `frontend/src/App.jsx` | Add `/cyber/*` routes |
| 20 | `frontend/src/test/cyber-primitives.test.jsx` | NEW — Vitest + RTL tests for primitives |
| 21 | `frontend/src/test/cyber-theme.test.jsx` | NEW — Theme toggle tests |

### Phase 1 — Async JobManager + SSE + Secure Video + Pipeline Events

| # | File | Action |
|---|------|--------|
| 1 | `backend/services/jobManager.js` | NEW — MAX_CONCURRENT_RUNS=2, queue, cancel, persist |
| 2 | `backend/services/sseHub.js` | NEW — SSE connections, replay via Last-Event-ID |
| 3 | `backend/services/streamTicket.js` | NEW — POST /api/auth/stream-ticket, 15-min TTL |
| 4 | `backend/services/ffprobeService.js` | NEW — ffprobe metadata extraction |
| 5 | `backend/services/ssrfGuard.js` | NEW — DNS resolution, IP allowlist, private range check |
| 6 | `backend/services/maskRtspUrl.js` | NEW — credential masking for logs |
| 7 | `backend/routes/analyze.js` | MODIFY — async spawn, stage manifest, SSE events |
| 8 | `backend/routes/stream.js` | NEW — GET /api/videos/stream/:filename with Range, ticket auth |
| 9 | `backend/routes/auth.js` | ADD — POST /api/auth/stream-ticket |
| 10 | `pipeline_runner.py` | MODIFY — emit STAGE_EVENT, CHUNK_EVENT, OBSERVATION_EVENT prefixes |
| 11 | `frontend/src/hooks/useSSE.js` | NEW — EventSource hook with reconnect |
| 12 | `frontend/src/hooks/useJob.js` | NEW — Job creation, status polling |
| 13 | `frontend/src/test/jobManager.test.js` | NEW — Unit tests |
| 14 | `frontend/src/test/ssrfGuard.test.js` | NEW — SSRF guard tests |
| 15 | `frontend/src/test/sseHub.test.js` | NEW — SSE replay tests |

### Phase 2 — Cyber Landing + Forensic Page (Wired)

| # | File | Action |
|---|------|--------|
| 1 | `backend/routes/cyber.js` | NEW — /api/cyber/* routes |
| 2 | `backend/services/verdictModule.js` | NEW — deterministic verdict logic |
| 3 | `backend/services/custodyChain.js` | NEW — append-only custody events |
| 4 | `backend/services/reviewQueue.js` | NEW — read-only review queue |
| 5 | `frontend/src/components/cyber/CyberLanding.jsx` | WIRE — navigate to /cyber/* |
| 6 | `frontend/src/components/cyber/ForensicPage.jsx` | WIRE — end-to-end data flow |
| 7 | `frontend/src/test/verdictModule.test.js` | NEW — all verdict paths |

### Phase 3 — Live Watch + Relay + Agent Panel + Alerts

| # | File | Action |
|---|------|--------|
| 1 | `backend/routes/cyber.js` | ADD — /api/cyber/live/*, /api/cyber/cameras/* |
| 2 | `backend/services/relayService.js` | NEW — MediaMTX/go2rtc integration |
| 3 | `frontend/src/components/cyber/LiveWatchPage.jsx` | WIRE — HLS stream, agent panel, alerts |
| 4 | `frontend/src/components/cyber/AgentPanel.jsx` | NEW — observations, ask, rules tabs |
| 5 | `frontend/src/components/cyber/AlertFeed.jsx` | NEW — live alert stream |

### Phase 4 — Trace + Polish

| # | File | Action |
|---|------|--------|
| 1 | `frontend/src/components/cyber/TracePage.jsx` | WIRE or "Coming Soon" banner |
| 2 | Responsive audit at 1280/1024/768 |
| 3 | Keyboard accessibility audit |
| 4 | Contrast audit (all pairs verified) |
| 5 | Reduced motion audit |

---

## STATIC LAYOUT DESIGNS (Phase 0 Deliverable)

### Shared Cyber Console Shell (`CyberLayout.jsx`)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◀ Back to chat   Live Watch │ Forensic │ Trace        ☀/☾   ● Connected   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [Page content area - routes to LiveWatchPage, ForensicPage, TracePage]      │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Top Bar:**
- Left: "Back to chat" link (navigates to `/analytics`)
- Center: Three tabs (Live Watch | Forensic | Trace) — active tab has accent underline + bold
- Right: Theme toggle (sun/moon icon), connection status pill ("● Connected" / "○ Not connected")

---

### Cyber Landing Page (`CyberLanding.jsx`)

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│                     Cyber Investigation Console                    │
│                                                                    │
│   ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐  │
│   │                  │ │                  │ │                  │  │
│   │   ▶ Live Watch   │ │  🔍 Forensic     │ │  📍 Trace        │  │
│   │                  │ │     Analysis     │ │                  │  │
│   │  Monitor RTSP    │ │                  │ │  Track people    │  │
│   │  camera feeds    │ │  Analyze video   │ │  and locations   │  │
│   │  in real-time    │ │  for tampering   │ │  across footage  │  │
│   │                  │ │  and deepfakes   │ │                  │  │
│   │  [Not connected] │ │  [Upload file]   │ │  [Coming soon]   │  │
│   │                  │ │                  │ │                  │  │
│   └──────────────────┘ └──────────────────┘ └──────────────────┘  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**Cards:**
- Each card: `border: 1px solid var(--cyber-border)`, `border-radius: 12px`, `background: var(--cyber-surface)`
- Icon: Lucide icon in accent color, 24px
- Title: Source Serif 4, 18px, semibold, `var(--cyber-text)`
- Description: Inter, 14px, `var(--cyber-text-secondary)`
- Status/CTA: Button or "Coming soon" badge
- Hover: `border-color: var(--cyber-accent)`, subtle warm shadow

---

### Live Watch Page (`/cyber/live`)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◀ Back   Live Watch │ Forensic │ Trace          ☀/☾   ● Connected          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────┐  ┌──────────────────────────────┐  │
│  │  CAM-04  │ rtsp://***:***@cam-04    │  │  LIVE AGENT                  │  │
│  │  Test    │ Start / Stop             │  │                              │  │
│  ├─────────────────────────────────────┤  │  ┌───────┬───────┬────────┐  │  │
│  │                                     │  │  │Observe│ Ask   │ Rules  │  │  │
│  │         ┌───────────────────┐       │  │  └───────┴───────┴────────┘  │  │
│  │         │                   │       │  │                              │  │
│  │         │   HLS VIDEO       │       │  │  14:32:07  Person detected   │  │
│  │         │   #141413 bg      │       │  │  14:32:05  Acoustic: alarm   │  │
│  │         │                   │       │  │  14:32:02  Chunk analyzed    │  │
│  │         │   ● LIVE          │       │  │                              │  │
│  │         │   FPS: 29.97     │       │  │  Last analyzed: 12s ago      │  │
│  │         │   Bitrate: 4.2Mbps│       │  │                              │  │
│  │         └───────────────────┘       │  │  ┌──────────────────────┐    │  │
│  │                                     │  │  │ Ask about feed...    │    │  │
│  │  Chunk Timeline                     │  │  └──────────────────────┘    │  │
│  │  ├─ Chunk 1 (0:00-0:30) ─┤         │  │                              │  │
│  │  ├─ Chunk 2 (0:30-1:00) ─┤ ◀ now  │  │  Model: Qwen2.5-VL          │  │
│  │                                     │  │  Window: last 5 min         │  │
│  │  Alert Feed                         │  │                              │  │
│  │  ⚠ 14:32:07  Acoustic alarm ─ HIGH │  │                              │  │
│  │  ℹ 14:31:45  Stream OK      ─ OK   │  │                              │  │
│  └─────────────────────────────────────┘  └──────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Layout:** 65% left / 35% right (at 1280px)
**Left panel:**
- Camera card: `background: #141413` (video stage), overlay with camera name + LIVE dot
- Stream health: FPS, bitrate, last chunk time (JetBrains Mono)
- Chunk timeline: horizontal bar with 30s segments, current highlighted
- Alert feed: scrollable list, each item has severity icon + label + timestamp + aria-live="polite"

**Right panel (Agent):**
- Three tabs: Observations | Ask | Rules
- Observations: timestamped VL log entries
- Ask: chat input + response, shows time window and model name
- Rules: create/disable standing watch rules
- "Last analyzed Ns ago" indicator

**Empty state (no camera):**
```
┌─────────────────────────────────────┐
│                                     │
│       No camera connected          │
│                                     │
│  Enter an RTSP URL and click       │
│  Test connection to begin.         │
│                                     │
│  [RTSP URL input]  [Test]          │
│                                     │
└─────────────────────────────────────┘
```

**Loading state:**
- Video area: Skeleton pulse on `#141413` background
- Agent panel: 3 skeleton rows with shimmer

**Error state:**
- Connection failed: danger icon + "Connection failed" + retry button
- Stream dropped: warning icon + "Stream interrupted" + timestamp

---

### Forensic Workbench (`/cyber/forensic`)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◀ Back   Live Watch │ Forensic │ Trace          ☀/☾   ● Connected          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CASE: CR-2024-001  │  File: CCTV_Sector4.mp4  │  SHA-256: a3f2...8b1c     │
│  Verdict: Likely Manipulated  │  [Save to Evidence] [Export] [Review Queue]│
│                                                                              │
│  ┌─────────────────────────────────────┐  ┌──────────────────────────────┐  │
│  │                                     │  │  ┌───────┬────────┬───────┐  │  │
│  │         ┌───────────────────┐       │  │  │Authen │Metadata│Custody│  │  │
│  │         │                   │       │  │  └───────┴────────┴───────┘  │  │
│  │         │   VIDEO PLAYER    │       │  │                              │  │
│  │         │   #141413 bg      │       │  │  ┌──────────────────────┐    │  │
│  │         │                   │       │  │  │ SBI Deepfake Check   │    │  │
│  │         │   ◀  ▶  Frame    │       │  │  │ Score: 0.73          │    │  │
│  │         │   42 / 1847       │       │  │  │ Threshold: 0.65      │    │  │
│  │         │   00:14.200       │       │  │  │ Status: FLAGGED      │    │  │
│  │         └───────────────────┘       │  │  │ "Frame 420 shows     │    │  │
│  │                                     │  │  │  compression quants  │    │  │
│  │  Frame-by-frame: ◀ prev  next ▶    │  │  │  inconsistent with   │    │  │
│  │                                     │  │  │  surrounding frames" │    │  │
│  └─────────────────────────────────────┘  │  └──────────────────────┘    │  │
│                                           │                              │  │
│  ┌─────────────────────────────────────┐  │  ┌──────────────────────┐    │  │
│  │  TIMELINE                           │  │  │ AI Generation Check  │    │  │
│  │  ┌─Fake Score Graph─────────────┐   │  │  │ Score: 0.12          │    │  │
│  │  │  ─── 0.65 threshold ─────── │   │  │  │ Status: Clean        │    │  │
│  │  │  ▁▁▁▂▁▁▁▁████▁▁▁▁▁▁▁▁▁▁▁  │   │  │  └──────────────────────┘    │  │
│  │  └──────────────────────────────┘   │  │                              │  │
│  │  Scene cuts: |  |    |              │  │  ┌──────────────────────┐    │  │
│  │  Findings:  ▼  ▼    ▼              │  │  │ Quality Gate (8 rules)│    │  │
│  │    • Frame splice @ 00:14           │  │  │ 7/8 passed            │    │  │
│  │    • Audio desync @ 00:00           │  │  │ Rule 3: FAILED        │    │  │
│  │    • Timestamp gap @ 00:32          │  │  │ "Zero audio track"    │    │  │
│  └─────────────────────────────────────┘  │  └──────────────────────┘    │  │
│                                           │                              │  │
│                                           │  [Metadata tab content]      │  │
│                                           │  [Custody tab content]       │  │
│                                           └──────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Layout:** Player left, tabs right, timeline bottom (full width)

**Header row:**
- Case ID (JetBrains Mono), file name, SHA-256 hash (truncated, mono)
- Verdict badge: StatusPill with semantic color
- Action buttons: Save to Evidence Room, Export Report, Route to Review Queue

**Authenticity tab:**
- One card per check (SBI, AI-generation, Quality Gate)
- Each card: check name, score, threshold, status badge, plain-language explanation, limitations text
- SBI deepfake: frame threshold + video threshold
- Quality Gate: rule-by-rule breakdown with notes and failed event IDs

**Metadata tab:**
- ffprobe output: container, codec, encoder, creation time, editing traces
- Displayed as key-value pairs in JetBrains Mono

**Custody tab:**
- SHA-256 hash (full, mono)
- Event list: uploaded → analyzed → viewed → exported (each with user, timestamp)
- Merkle verification status

**Timeline (bottom, full width):**
- Per-frame fake-score graph (line chart) with threshold lines
- Scene cut markers
- Timestamp gap indicators
- Findings list (clickable → seeks player)

**Empty state:**
```
┌─────────────────────────────────────┐
│                                     │
│       No evidence loaded            │
│                                     │
│  Upload a video file or provide    │
│  a URL to begin forensic analysis. │
│                                     │
│  [Upload]  [Enter URL]             │
│                                     │
└─────────────────────────────────────┘
```

---

### Trace Page (`/cyber/trace`)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◀ Back   Live Watch │ Forensic │ Trace          ☀/☾   ● Connected          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  ⚠  Coming Soon — Person Tracking & Geolocation                     │   │
│  │                                                                      │   │
│  │  This feature requires face_reid_agent and geo_estimation_agent     │   │
│  │  to produce usable output and pass governance gates.                │   │
│  │                                                                      │   │
│  │  Planned capabilities:                                               │   │
│  │  • Person identity tracking across multiple camera feeds             │   │
│  │  • GPS location estimation from scene frames                         │   │
│  │  • Movement轨迹 visualization on map                                 │   │
│  │  • Cross-camera person re-identification                             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  [Video player area - #141413 bg]                                    │   │
│  │                                                                      │   │
│  │  [Map placeholder]                                                   │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**State:** "Coming Soon" banner with explanation. No data wiring. Placeholder layout only.

---

## VERIFICATION CHECKLIST (Phase 0)

- [ ] `npm run build` — clean, no errors
- [ ] `npm run test` — all tests pass (primitives, theme toggle)
- [ ] `npm ls vite` — single Vite 6.4.3
- [ ] Light mode screenshots of all 4 pages (Landing, Live, Forensic, Trace)
- [ ] Dark mode screenshots of all 4 pages
- [ ] `/`, `/login`, `/evidence`, `/analytics` unchanged and functional
- [ ] No #000000 or #FFFFFF used anywhere in cyber CSS
- [ ] All text/background pairs ≥ 4.5:1 contrast (3:1 for large text)
- [ ] Keyboard navigation works for tabs, theme toggle, buttons
- [ ] `prefers-reduced-motion` respected
- [ ] All primitives have loading, empty, and error states

---

## APPROVAL GATE

Awaiting approval before implementing Phase 0 code. Once approved, I will:

1. Create all Phase 0 files (tokens, primitives, layouts, tests)
2. Run build + tests
3. Take screenshots at 1280/1024/768 in light and dark modes
4. Stop for review before Phase 1
