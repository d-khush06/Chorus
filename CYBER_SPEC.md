ROLE
Act as a Principal UI/UX Engineer and Senior Frontend Developer (with strong Node/Python backend skills). Work in gated steps: produce the plan and static layouts first, wait for my approval, then implement ONE phase at a time and stop after each phase with evidence (npm run build, npm run test, npm ls vite output, and screenshots in light and dark mode).

=====================================================================
1. DESIGN SYSTEM (applies to every new Cyber page and the Cyber landing cards)
=====================================================================
Aesthetic: warm, intellectual, document-focused, like the Claude AI interface. High readability, generous line height (body 1.6-1.7), calm density, no neon, no glassmorphism.

Tokens (use exactly; never #000000 or #FFFFFF anywhere):
LIGHT: bg #F5F3EE | surface (sidebar/cards) #E8E3D2 | border #DCD7C6 | text #141413 | text-secondary #5E5D59 | accent #C15F3C
DARK:  bg #191816 | surface #1A1A18 | border #30302E | text #FAF9F5 | text-secondary #B0AEA5 | accent #D97757

Rules:
- Accent (terracotta) is used sparingly: primary buttons, active tab indicator, focus rings, the LIVE dot, notification badges. Never for large fills or decoration.
- Dark mode: surface #1A1A18 is almost identical to bg #191816. Separate cards with a 1px #30302E border and spacing, not fill color alone.
- Contrast: accent on light bg is about 3.8:1, so use accent for fills, borders and icons, not small text; small links use text color with an accent underline. Button labels: light mode #FAF9F5 at 16px+ semibold; dark mode #191816 on #D97757. Verify every text/background pair with a contrast checker and report any pair below 4.5:1 (3:1 for large text and UI components).
- Video/evidence stage background: #141413 (light and dark), never pure black.
- Shadows are soft and warm (rgba(20,20,19,0.08)); prefer borders over shadows.
- Semantic status colors (PROPOSED EXTENSION, not in the base matrix; list them for my approval): ok, warning, danger, info as muted, desaturated tones tuned per theme, always paired with an icon and text label (never color alone). Danger must be visibly distinct from the terracotta accent.
- Typography: headings in a serif (Source Serif 4, fallback Georgia); UI text in Inter; data/timestamps/hashes in JetBrains Mono. Load via index.html. Tabular numerals for timestamps and scores.
- Spacing on a 4px grid; radius 10-14px for cards, 8px for controls; hairline dividers.
- Motion: 150-200ms ease; LIVE dot pulse; everything respects prefers-reduced-motion.
- Accessibility: visible focus rings (accent), aria-labels on icon buttons, aria-live="polite" for alert feed and stage changes, full keyboard operation of tabs, timeline, and player controls.
- Implementation: CSS variables per theme ([data-theme="light"|"dark"], default from prefers-color-scheme, with a manual toggle persisted in localStorage), mapped into Tailwind v3 colors via rgb(var(--token) / <alpha-value>). Keep Tailwind preflight disabled and scope base styles under a .cyber-console wrapper so existing pages are not affected. Deliver a tokens file, a Tailwind config, and a small primitives set (Card, Badge, Button, Tabs, StatusPill, EmptyState, ErrorState, Skeleton) before any page.

=====================================================================
2. NON-NEGOTIABLES
=====================================================================
- General mode and its data pipeline stay unchanged. Phase 2 may change only its transport (SSE stage events instead of a waiting spinner).
- Existing routes /, /login, /evidence, /analytics keep working. The old /launchpad shell is fully removed.
- NO FAKE DATA: no hardcoded counts, names, model labels, GPU stats or sample investigations in any new UI. Every value comes from the backend or shows an explicit empty/"not connected"/"planned" state. Model labels come from run metadata. A mock provider may exist only behind VITE_USE_MOCKS=true with a visible "DEMO DATA" banner.
- Do not bypass any governance/consent gate in face_reid_agent.py or geo_estimation_agent.py.
- Every card and panel has loading, empty and error states.
- Phase 0 report (owed from earlier): (a) where do "3 Cases", "Executive Briefing Q3", "CR-889 — CCTV Perimeter…", "Synthetic Voice & Deepfak…" and the "Flash" model chip come from (real or hardcoded, with file and line); (b) build/test/npm ls vite output (single Vite version); (c) confirmation that /, /login, /evidence, /analytics are unchanged.

=====================================================================
3. PRODUCT STRUCTURE
=====================================================================
- Mode toggle in the existing chat UI: General | Cyber.
- Selecting Cyber shows a landing with three cards: Live Watch (RTSP), Forensic Analysis, Trace. Each card opens its OWN full-page route with its own layout (not the chat UI): /cyber/live, /cyber/forensic, /cyber/trace. Shared "Cyber console" shell: top bar with tabs (Live Watch | Forensic | Trace), "Back to chat", theme toggle, and connection/run status pill. No chat sidebar or prompt bar.
- Cyber mode uses ONE cyber pipeline (mode=cyber in pipeline_runner.py), separate from the general pipeline. The three pages are different front doors and views onto that same pipeline: they differ in input source and in which results they emphasize. Record entry_point (live_watch | forensic | trace) in run and case metadata. Do not create separate pipelines or a new workflow parameter.

=====================================================================
4. BACKEND ARCHITECTURE (Node/Express + Python)
=====================================================================
Routing: POST /api/analyze accepts mode=general|cyber, source_type=local_upload|youtube|live_rtsp, entry_point, optional case_id and notes. It validates input, creates a run, spawns pipeline_runner.py, and returns 202 { runId } immediately.

Process spawning: spawn with an argument array, shell:false; python -u with PYTHONUNBUFFERED=1 and PYTHONIOENCODING=utf-8 (Windows).

Event protocol (stdout lines with distinct prefixes, flushed): STAGE_EVENT, CHUNK_EVENT (per 30s chunk), OBSERVATION_EVENT (VL agent observation with timestamps), ALERT_EVENT (from alert_system.py and rule matches). Backend sends a stage manifest at run start; the frontend renders stages from the manifest and never hardcodes order.

Cyber stage manifest: derive the true stage order from the code (candidates: source_ingestion, duplication_check, quality_gate, manipulation_detection, ai_generation_detection, orchestrator_routing, scene_segmentation using AdaptiveDetector, asr_transcription, vision_perception, multimodal_fusion, domain_output, acoustic_event_detection, geo_estimation, face_reid, alert_system). Produce an applicability matrix per source_type/entry_point. Non-applicable stages are "not_applicable" or "skipped", never "failed" (for example stream continuity for a file).

jobManager (backend/services/jobManager.js): MAX_CONCURRENT_RUNS=2 with a queued state; DELETE /api/analyze/runs/:id cancels and kills the whole process tree on Windows (taskkill /T /F or tree-kill); persist runs to backend/data/runs/<runId>.json; SSE replay via Last-Event-ID; no timeout for live_rtsp runs; graceful shutdown.

Endpoints (in addition to POST /api/analyze):
- GET /api/analyze/runs/:id (status), GET /api/analyze/runs/:id/events (SSE), DELETE /api/analyze/runs/:id
- POST /api/auth/stream-ticket -> multi-use ticket, 15-min TTL, bound to (userId, resourceId), auto-refresh on the client (needed because EventSource and <video> cannot send Authorization headers)
- GET /api/videos/stream/:filename?ticket= -> authenticated Range streaming: 206/416, correct Content-Type, destroy the stream on client close, path.basename against traversal. /uploads is never public. Non-mp4 uploads get an H.264/AAC MP4 preview via ffmpeg; the pipeline analyzes the original.
- POST /api/cyber/cameras/test -> connection test through the SSRF guard
- POST /api/cyber/live/:runId/ask -> chat about the recent feed, answering only from the last N minutes of observations/chunks and stating the time window
- GET/POST/DELETE /api/cyber/live/:runId/rules -> standing watch rules; matches emit ALERT_EVENT. Evaluate all rules per chunk in one batched VL prompt; validate feasibility against measured latency
- GET /api/cyber/forensic/:runId/report -> JSON report (PDF optional later) including limitations
- POST /api/cyber/forensic/:runId/save-case -> write to Evidence Room
- GET /api/cyber/forensic/:runId/custody -> chain-of-custody events
- GET /api/review-queue -> read-only in this scope; resolutions later as new append-only JSONL records (reviewer id from JWT), never edits

RTSP relay and credentials: MediaMTX or go2rtc is the single camera consumer (HLS on 8888 for MediaMTX, API on 1984 for go2rtc; 8554 is RTSP, not HLS; base URLs from env). Camera credentials live only in relay registration/.env. The pipeline receives only the credential-free local relay URL. The browser never receives camera credentials. maskRtspUrl() is applied at write time to audit logs, review-queue source_uri, run files and process args.

SSRF guard: allowlist schemes (https for YouTube, rtsp for cameras); resolve DNS, check resolved IPs against 0.0.0.0/8, 127/8, 10/8, 172.16/12, 192.168/16, 169.254/16, 100.64/10, ::1, fc00::/7, fe80::/10; connect to the validated IP (no re-resolution). Private cameras are permitted only via an admin ALLOWED_RTSP_TARGETS allowlist (hosts/CIDRs); the configured relay host is exempt. Blocked targets return 403.

Forensic verdict (single backend module, deterministic, unit-tested, thresholds read from result payloads, never hardcoded in the UI):
- Inconclusive: detector_error, NO_FACES_DETECTED with no other usable evidence, or too few decodable frames
- Likely manipulated: manipulation verdict FLAGGED or AI-generation screening positive
- Suspicious: borderline scores or warnings
- Authentic-looking: all applicable checks ran and were clean. State that this is not proof of authenticity.
Always return scores, thresholds and per-check evidence. Never a bare "fake/real".

Chain of custody: append-only events (uploaded, hashed, analyzed, viewed, exported, saved) with user id and timestamp in audit_logs/custody/. SHA-256 comes from the pipeline (no client-side hashing). Reuse the existing Evidence Room case and Merkle verification.

Metadata: small ffprobe service (spawn with an argument array) returning container, codec, encoder, creation time, and flags for editing-software traces.

=====================================================================
5. PAGE SPECS
=====================================================================
/cyber/live (Live Watch)
- Left (about 65%): one large camera card: relay stream (hls.js) on a #141413 stage, overlay with camera name, clock, LIVE dot (accent), stream health (fps, bitrate, last chunk). Below it: chunk timeline (30s chunks) and alert feed (acoustic, stream continuity, rule matches) with severity icon + label and aria-live.
- Right (about 35%): LIVE AGENT panel with tabs Observations (timestamped VL log), Ask (chat limited to the recent window, shows the window and model name), Rules (create/disable standing rules). Show "last analyzed Ns ago". It is near-live and works on sampled frames/chunks; say so in the UI.
- Top: camera name, RTSP URL (masked after entry), Test connection, Start/Stop. Stop can save the session and incidents as a case.
- Start with one camera. Before committing to a refresh rate, inspect benchmark_vl_concurrency.py and test_vl_worker_pool.py and report measured VL latency and supported concurrent streams.

/cyber/forensic (Forensic workbench)
- Header: case id, file name, SHA-256 (mono), verdict badge, Save to Evidence Room, Route to Review Queue, Export report.
- Left: evidence player with frame-by-frame stepping (frame number and time); stage in #141413.
- Right tabs: Authenticity (one card per check: SBI deepfake with frame and video thresholds, AI-generation, quality gate 8 rules with notes and failed event ids, each with a plain-language explanation and limitations), Metadata (ffprobe), Custody (hash, events, Merkle verification).
- Bottom: timeline synced to the player: per-frame fake-score graph with threshold lines, scene cuts, timestamp gaps, findings list; clicking a finding seeks the player.
- Frame-level tamper analysis is shown as PLANNED. State which checks are backed by existing files and which are new work.

/cyber/trace
- Same shell. Person tracks list, video with the selected track highlighted, map with location estimate. "Coming soon" banner unless face_reid_agent and geo_estimation_agent produce usable output in a normal run and pass governance gates.

=====================================================================
6. PHASES (each ends with a working, testable result and stops for my review)
=====================================================================
Phase 0: Phase 0 report (section 2), design tokens + Tailwind + primitives, static layouts of all three pages in light and dark mode with empty/loading/error states and NO data wiring. Stop for approval.
Phase 1: async jobManager, stage events, SSE, secure video route, stream tickets, pipeline_runner.py event emission; General mode transport change only.
Phase 2: Cyber landing cards + /cyber/forensic wired end to end (verdict module, ffprobe, custody, save case, review queue read-only, report export).
Phase 3: /cyber/live + relay service + SSRF guard + camera test + agent panel (observations, ask, rules) + alert feed.
Phase 4: /cyber/trace (or documented "Coming soon") + polish (responsive at 1280/1024/768, keyboard access, reduced motion, contrast audit).

=====================================================================
7. VERIFICATION
=====================================================================
- Vitest + React Testing Library: primitives, theme toggle, verdict module (all four verdicts plus detector_error and NO_FACES_DETECTED), stage tracker driven by mocked SSE events, SSRF guard (private IPs, IPv6, DNS rebinding, allowlist, relay exemption), maskRtspUrl, ticket ownership.
- Integration: clean file run; duplicate video halt; flagged video to review queue; RTSP with credentials never exposed to the browser or logs; cancel a running job and confirm no orphaned python/ffmpeg processes.
- Regression on /, /login, /evidence, /analytics; light and dark screenshots of every Cyber page at 1280/1024/768.

=====================================================================
DELIVERABLE NOW
=====================================================================
Output the updated plan (same format as before, with file links and phases above), the Phase 0 report, and the static layout designs of the three pages. Wait for my approval before writing implementation code.

do all the thinsg in oen pas i dotn need impelmantation plan