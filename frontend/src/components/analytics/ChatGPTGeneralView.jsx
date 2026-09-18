import React, { useState, useEffect, useRef, useContext } from 'react';
import { useNavigate } from 'react-router-dom';
import FusedEventCard from '../FusedEventCard.jsx';
import UserProfileModal from '../ui/UserProfileModal.jsx';
import AppSettingsModal from '../ui/AppSettingsModal.jsx';
import HelpSupportModal from '../ui/HelpSupportModal.jsx';
import AuthContext from '../../context/AuthContext';
import './ChatGPTGeneralView.css';
import {
  Search, PanelLeft, Plus, X, Sparkles, Brain, Mic, AudioLines,
  MessageSquare, Settings, PenLine, Scale, ShieldAlert, Film,
  ChevronDown, ChevronRight, Check, Copy, ThumbsUp, ThumbsDown, RotateCcw,
  ArrowUp, Clock, AlertTriangle, ShieldCheck, Zap, Sliders,
  CircleUser, HelpCircle, LogOut, Store, Pin, Trash2, UploadCloud, Activity
} from 'lucide-react';

const INITIAL_HISTORY = [
  {
    id: 'hist-1',
    title: 'CR-889 — CCTV Perimeter Tamper Audit',
    mode: 'cyber',
    timestamp: 'Today',
    isPinned: true,
    videoName: 'CCTV_Perimeter_Sector4.mp4',
    prompt: 'Audit CCTV_Perimeter_Sector4.mp4 for video manipulation, frame splices, and timestamp alteration.',
    cyberData: {
      threatScore: 87,
      threatLevel: 'HIGH',
      classification: 'Unauthorized Manipulation & Frame Splicing',
      anomalies: [
        { time: '00:14 – 00:18', type: 'Optical Flow Discontinuity', severity: 'CRITICAL', desc: 'Synthetic background loop injected to mask perimeter gate activity.' },
        { time: '00:14', type: 'I-Frame Splicing', severity: 'HIGH', desc: 'Compression quantization jump detected between frame 420 and 421.' },
        { time: '00:00 – 00:45', type: 'Audio Desynchronization', severity: 'MEDIUM', desc: 'Audio track zeroed out prior to file container creation.' }
      ],
      integrityStatus: 'Tampered / Compromised',
      hashMatch: 'Mismatch (SHA-256 diverges from camera ledger)',
      mitigationActions: [
        'Flag segment 00:14–00:18 for cryptographic preservation.',
        'Cross-reference badge swipe access logs for Sector 4.',
        'Notify physical security operations center.'
      ]
    },
    messages: []
  },
  {
    id: 'hist-2',
    title: 'Executive Briefing Q3 — Revenue & Growth',
    mode: 'general',
    timestamp: 'Today',
    isPinned: true,
    videoName: 'Q3_Executive_Briefing.mp4',
    prompt: 'Summarize the Q3 executive review video and highlight key financial metrics.',
    summary: {
      title: 'Q3 Executive Performance Briefing',
      overview: 'Executive briefing on Q3 organizational milestones. Exceeded quarterly revenue benchmarks by 14.8% through accelerated enterprise adoption of Chorus Multimodal Video Intelligence.',
      takeaways: [
        { label: 'Revenue Growth', detail: '14.8% outperformance across all core commercial segments.' },
        { label: 'Product Expansion', detail: 'Chorus Multimodal Intelligence active across 34 enterprise pilots.' }
      ],
      chapters: [
        { time: '00:00 – 03:15', title: 'Executive Welcome', desc: 'CEO opening remarks and operational context.' },
        { time: '03:15 – 09:40', title: 'Financial Metrics', desc: 'CFO review of margins, operating expenses, and ARR.' },
        { time: '09:40 – 14:20', title: 'Product Roadmap', desc: 'Overview of multimodal video processing pipelines.' }
      ],
      dynamics: {
        analyzedFrames: '25,800 frames @ 30fps',
        engine: 'Chorus DeepVideo'
      },
      actionItems: [
        'Distribute finalized Q3 financial packet to executive stakeholders.',
        'Schedule follow-up engineering briefing on real-time stream decoding.'
      ]
    },
    messages: []
  },
  {
    id: 'hist-3',
    title: 'Synthetic Voice & Deepfake Screen',
    mode: 'cyber',
    timestamp: 'Yesterday',
    isPinned: false,
    videoName: 'Executive_Public_Address.mp4',
    prompt: 'Verify authenticity of public address video. Check for neural face manipulation and synthetic audio cloning.',
    cyberData: {
      threatScore: 92,
      threatLevel: 'CRITICAL',
      classification: 'Generative Face Synthesis & Voice Cloning',
      anomalies: [
        { time: '00:04 – 00:38', type: 'Facial Boundary Blurring', severity: 'CRITICAL', desc: 'Deepfake diffusion boundary artifacts detected around jawline.' },
        { time: '00:00 – 00:40', type: 'Acoustic Vocoder Artifacts', severity: 'HIGH', desc: 'Synthetic neural vocoder frequencies identified in >16kHz band.' }
      ],
      integrityStatus: 'Synthetic Media Detected',
      hashMatch: 'Unregistered Source',
      mitigationActions: [
        'Tag media asset as synthetic deepfake in Evidence Registry.',
        'Issue verified communication advisory.'
      ]
    },
    messages: []
  }
];

export default function ChatGPTGeneralView({ onBack, onGoToEvidence }) {
  const navigate = useNavigate();
  const { user, logout } = useContext(AuthContext);

  // Active Mode: 'general' or 'cyber'
  const [activeMode, setActiveMode] = useState('general');

  const [history, setHistory] = useState(() => {
    try {
      const saved = localStorage.getItem('chorus_history');
      return saved ? JSON.parse(saved) : INITIAL_HISTORY;
    } catch {
      return INITIAL_HISTORY;
    }
  });

  const [activeSessionId, setActiveSessionId] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeSession, setActiveSession] = useState(null);
  const [promptText, setPromptText] = useState('');
  const [attachedFile, setAttachedFile] = useState(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [copiedId, setCopiedId] = useState(null);
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [searchFilter, setSearchFilter] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [suggestionCardDismissed, setSuggestionCardDismissed] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showHelpModal, setShowHelpModal] = useState(false);

  const [selectedModel, setSelectedModel] = useState(() => {
    return localStorage.getItem('chorus_selected_model') || 'flash';
  });
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [commandNotification, setCommandNotification] = useState(null);
  const [showCommandSuggestions, setShowCommandSuggestions] = useState(false);
  const [expandedThoughts, setExpandedThoughts] = useState({});

  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const userMenuRef = useRef(null);
  const modelDropdownRef = useRef(null);

  const switchModel = (newModel, viaCommand = false) => {
    setSelectedModel(newModel);
    try {
      localStorage.setItem('chorus_selected_model', newModel);
    } catch { }
    setModelDropdownOpen(false);
    setShowCommandSuggestions(false);
    const name = newModel === 'deepthink' ? 'Chorus Deepthink' : 'Chorus Flash';
    setCommandNotification({
      text: name
    });
    setTimeout(() => {
      setCommandNotification(null);
    }, 1500);
  };

  const toggleThought = (msgId) => {
    setExpandedThoughts(prev => ({
      ...prev,
      [msgId]: !prev[msgId]
    }));
  };

  // Close model dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e) {
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(e.target)) {
        setModelDropdownOpen(false);
      }
    }
    if (modelDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [modelDropdownOpen]);

  // Shortcut: Ctrl + M toggles model
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'm') {
        e.preventDefault();
        const next = selectedModel === 'flash' ? 'deepthink' : 'flash';
        switchModel(next, true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedModel]);

  // Close user profile popover on outside click
  useEffect(() => {
    function handleClickOutside(e) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
        setUserMenuOpen(false);
      }
    }
    if (userMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [userMenuOpen]);

  // Sync history to local storage
  useEffect(() => {
    try {
      localStorage.setItem('chorus_history', JSON.stringify(history));
    } catch (e) { }
  }, [history]);

  // Handle session selection
  useEffect(() => {
    if (activeSessionId) {
      const found = history.find(h => h.id === activeSessionId);
      if (found) {
        setActiveSession(found);
        if (found.mode) setActiveMode(found.mode);
      }
    } else {
      setActiveSession(null);
    }
  }, [activeSessionId, history]);

  // Auto scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession?.messages, isGenerating]);

  // Auto resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [promptText]);

  // Guaranteed direct navigation to Evidence Room
  const handleOpenEvidenceRoom = (e) => {
    if (e && e.preventDefault) e.preventDefault();
    if (onGoToEvidence) onGoToEvidence();
    navigate('/evidence');
    setTimeout(() => {
      if (window.location.pathname !== '/evidence') {
        window.location.href = '/evidence';
      }
    }, 50);
  };

  const handleNewChat = () => {
    setActiveSessionId(null);
    setActiveSession(null);
    setPromptText('');
    setAttachedFile(null);
    setIsGenerating(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleTogglePin = (id, e) => {
    e.stopPropagation();
    setHistory(prev => prev.map(item => {
      if (item.id === id) {
        return { ...item, isPinned: !item.isPinned };
      }
      return item;
    }));
  };

  const handleDeleteHistory = (id, e) => {
    e.stopPropagation();
    setHistory(prev => prev.filter(item => item.id !== id));
    if (activeSessionId === id) {
      setActiveSessionId(null);
      setActiveSession(null);
    }
  };

  const handleSwitchMode = (newMode) => {
    setActiveMode(newMode);
    if (!activeSession) {
      // Stay on empty state in the new mode
    }
  };

  const handleSend = async (customPrompt) => {
    const textToSend = typeof customPrompt === 'string' ? customPrompt : promptText;
    const trimmed = textToSend.trim();
    if (!trimmed && !attachedFile) return;

    // Check if input is a model switch command
    const rawLower = trimmed.toLowerCase();
    if (rawLower === '/flash' || rawLower === '/fast') {
      switchModel('flash', true);
      setPromptText('');
      return;
    }
    if (rawLower === '/deepthink' || rawLower === '/think') {
      switchModel('deepthink', true);
      setPromptText('');
      return;
    }
    if (rawLower === '/model' || rawLower === '/switch') {
      const next = selectedModel === 'flash' ? 'deepthink' : 'flash';
      switchModel(next, true);
      setPromptText('');
      return;
    }

    let effectiveModel = selectedModel;
    let actualPrompt = trimmed;

    if (rawLower.startsWith('/flash ')) {
      effectiveModel = 'flash';
      switchModel('flash', true);
      actualPrompt = trimmed.substring(7).trim();
    } else if (rawLower.startsWith('/deepthink ')) {
      effectiveModel = 'deepthink';
      switchModel('deepthink', true);
      actualPrompt = trimmed.substring(11).trim();
    } else if (rawLower.startsWith('/think ')) {
      effectiveModel = 'deepthink';
      switchModel('deepthink', true);
      actualPrompt = trimmed.substring(7).trim();
    }

    const isCyberQuery = activeMode === 'cyber' || /tamper|cyber|threat|hack|fake|manipulat|forge|deepfake|splice|anomaly/i.test(actualPrompt);
    const sessionMode = isCyberQuery ? 'cyber' : 'general';

    if (!activeSession) {
      const newId = 'hist-' + Date.now();
      const videoName = attachedFile ? attachedFile.name : null;
      const title = attachedFile
        ? attachedFile.name.replace(/\.[^/.]+$/, '')
        : (actualPrompt.length > 36 ? actualPrompt.substring(0, 36) + '...' : actualPrompt);

      const userMsg = {
        id: 'msg-' + Date.now(),
        sender: 'user',
        text: actualPrompt || (videoName ? `Analyze video evidence: ${videoName}` : 'Run video intelligence analysis.'),
        attachment: attachedFile ? attachedFile.name : null
      };

      const newSessionStub = {
        id: newId,
        title: title || (isCyberQuery ? 'Cyber Threat Scan' : 'Video Intelligence Analysis'),
        mode: sessionMode,
        timestamp: 'Just now',
        isPinned: false,
        videoName,
        prompt: userMsg.text,
        summary: null,
        cyberData: null,
        modelUsed: effectiveModel,
        messages: [userMsg]
      };

      setActiveSession(newSessionStub);
      setHistory(prev => [newSessionStub, ...prev]);
      setActiveSessionId(newId);
      setPromptText('');
      setAttachedFile(null);
      setIsGenerating(true);
      if (effectiveModel === 'deepthink') {
        setIsThinking(true);
      }

      // Simulate analysis time: Flash is fast (800ms), Deepthink does multi-step thinking (2400ms)
      const delay = effectiveModel === 'deepthink' ? 2400 : 800;
      await new Promise(r => setTimeout(r, delay));
      setIsThinking(false);

      if (sessionMode === 'cyber') {
        const generatedCyberData = {
          threatScore: 84,
          threatLevel: 'HIGH',
          classification: 'Temporal Frame Anomaly & Tamper Risk',
          modelUsed: effectiveModel,
          anomalies: [
            { time: '00:08 – 00:15', type: 'Discontinuous Optical Vector', severity: 'CRITICAL', desc: 'Frame sequence displays artificial frame injection and temporal displacement.' },
            { time: '00:12', type: 'Compression Rate Jump', severity: 'HIGH', desc: 'Macroblock rate variance exceeds standard encoder thresholds by 32%.' },
            { time: '00:00 – End', type: 'Metadata Audit', severity: 'MEDIUM', desc: 'Container timestamp header does not match camera hardware firmware signature.' }
          ],
          integrityStatus: 'Tamper Detected (High Confidence)',
          hashMatch: 'Mismatch with Ledger Registry',
          mitigationActions: [
            'Isolate and preserve target timestamp segment (00:08–00:15).',
            'Cross-check camera custody chain in Evidence Room.',
            'Export tamper digest for incident response.'
          ]
        };

        const assistantMsg = {
          id: 'msg-' + (Date.now() + 1),
          sender: 'assistant',
          isCyberReport: true,
          cyberData: generatedCyberData,
          modelUsed: effectiveModel,
          thoughtTime: effectiveModel === 'deepthink' ? '3.4s' : null,
          thoughtProcess: effectiveModel === 'deepthink' ? [
            "Deconstructed frame buffer from 00:00 to 00:45 across camera sector 4.",
            "Computed optical flow vector derivatives; identified discontinuity spike at 00:14.",
            "Verified container timestamp against camera SHA-256 ledger: checksum diverged by 4 blocks.",
            "Formulated tamper probability score: 84/100 (HIGH)."
          ] : null
        };

        const completedSession = {
          ...newSessionStub,
          cyberData: generatedCyberData,
          modelUsed: effectiveModel,
          messages: [userMsg, assistantMsg]
        };

        setActiveSession(completedSession);
        setHistory(prev => prev.map(item => item.id === newId ? completedSession : item));
        setIsGenerating(false);
        return;
      }

      // General Mode Output
      const generatedSummary = {
        title: title ? `${title} — Summary` : 'Chorus Video Intelligence Summary',
        modelUsed: effectiveModel,
        overview: 'Automated multimodal breakdown completed. Identified primary scene themes, visual action sequences, and high-priority operational takeaways.',
        takeaways: [
          { label: 'Primary Activity', detail: 'High visual coherence across primary scene intervals.' },
          { label: 'Audio Clarity', detail: 'Speech audio transcribed with verified voiceprint synchronization.' },
          { label: 'Key Finding', detail: 'Target event milestones cataloged and indexed.' }
        ],
        chapters: [
          { time: '00:00 – 01:10', title: 'Introductory Segment', desc: 'Initial subject entry and environment framing.' },
          { time: '01:10 – 03:20', title: 'Core Activity Window', desc: 'Primary subject actions and recorded interactions.' },
          { time: '03:20 – End', title: 'Conclusion', desc: 'Scene wrap-up and departures.' }
        ],
        dynamics: {
          analyzedFrames: '1,620 frames @ 30fps',
          engine: effectiveModel === 'deepthink' ? 'Chorus Deepthink (Forensic Engine)' : 'Chorus Flash'
        },
        actionItems: [
          'Log intelligence summary into case archive.',
          'Review flagged scene timestamps.'
        ]
      };

      const assistantMsg = {
        id: 'msg-' + (Date.now() + 1),
        sender: 'assistant',
        isSummary: true,
        summaryData: generatedSummary,
        modelUsed: effectiveModel,
        thoughtTime: effectiveModel === 'deepthink' ? '2.8s' : null,
        thoughtProcess: effectiveModel === 'deepthink' ? [
          "Indexed speech transcripts and visual keyframes across 3 distinct chapters.",
          "Evaluated multimodal consistency between audio track and visual actions.",
          "Generated structured executive summary takeaways."
        ] : null
      };

      const completedSession = {
        ...newSessionStub,
        summary: generatedSummary,
        modelUsed: effectiveModel,
        messages: [userMsg, assistantMsg]
      };

      setActiveSession(completedSession);
      setHistory(prev => prev.map(item => item.id === newId ? completedSession : item));
      setIsGenerating(false);
      return;
    }

    // Follow-up message
    const userFollowUp = {
      id: 'msg-' + Date.now(),
      sender: 'user',
      text: actualPrompt,
      attachment: attachedFile ? attachedFile.name : null
    };

    const updatedMessages = [...(activeSession.messages || []), userFollowUp];
    setActiveSession(prev => ({ ...prev, messages: updatedMessages }));
    setPromptText('');
    setAttachedFile(null);
    setIsGenerating(true);
    if (effectiveModel === 'deepthink') {
      setIsThinking(true);
    }

    const delay = effectiveModel === 'deepthink' ? 2200 : 700;
    await new Promise(r => setTimeout(r, delay));
    setIsThinking(false);

    const aiReply = {
      id: 'msg-' + (Date.now() + 1),
      sender: 'assistant',
      modelUsed: effectiveModel,
      thoughtTime: effectiveModel === 'deepthink' ? '2.1s' : null,
      thoughtProcess: effectiveModel === 'deepthink' ? [
        `Analyzed prompt intent: "${actualPrompt}".`,
        "Cross-referenced prior temporal context and timeline metadata.",
        "Verified consistency against current case timeline ledger."
      ] : null,
      text: `Chorus ${effectiveModel === 'deepthink' ? 'Deepthink' : 'Flash'} ${activeMode === 'cyber' ? 'Cyber Intelligence' : 'Analysis'}:\n\nIn response to "${actualPrompt}":\nThe video feed confirms the requested parameters. Temporal coherence is verified across adjacent keyframes without metric divergence.`
    };

    const finalSession = {
      ...activeSession,
      messages: [...updatedMessages, aiReply]
    };

    setActiveSession(finalSession);
    setHistory(prev => prev.map(item => item.id === activeSession.id ? finalSession : item));
    setIsGenerating(false);
  };

  const handleCopy = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Filter history
  const filteredHistory = history.filter(h =>
    h.title.toLowerCase().includes(searchFilter.toLowerCase())
  );
  const pinnedHistory = filteredHistory.filter(h => h.isPinned);
  const recentHistory = filteredHistory.filter(h => !h.isPinned);

  const userName = user?.name || (user?.email ? (user.email.toLowerCase().includes('khush') ? 'Khush Desai' : user.email.split('@')[0]) : 'Khush Desai');
  const userFirstName = (userName.split(' ')[0] || 'Khush').replace(/^\w/, c => c.toUpperCase());
  const capitalizedUserName = userName.includes(' ')
    ? userName.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
    : userName.charAt(0).toUpperCase() + userName.slice(1);

  // Chat Input Component
  const ChatInput = ({ centered }) => (
    <div className={`cpt-input-container ${centered ? 'cpt-input-centered' : ''}`}>
      {/* Command Palette Popup */}
      {promptText.startsWith('/') && (
        <div className="cpt-command-popup">
          <div 
            className="cpt-command-popup-item"
            onClick={() => {
              switchModel('flash', true);
              setPromptText('');
            }}
          >
            <span className="cpt-command-popup-cmd">/flash</span>
            <span className="cpt-command-popup-desc">Chorus Flash</span>
          </div>

          <div 
            className="cpt-command-popup-item"
            onClick={() => {
              switchModel('deepthink', true);
              setPromptText('');
            }}
          >
            <span className="cpt-command-popup-cmd">/deepthink</span>
            <span className="cpt-command-popup-desc">Chorus Deepthink</span>
          </div>
        </div>
      )}

      <div className={`cpt-input-wrapper ${activeMode === 'cyber' ? 'cyber-border' : ''}`}>
        {attachedFile && (
          <div className="cpt-file-chip">
            <Film size={13} className="cpt-file-icon" />
            <span className="cpt-file-name">{attachedFile.name}</span>
            <button className="cpt-file-chip__remove" onClick={() => setAttachedFile(null)}>
              <X size={12} />
            </button>
          </div>
        )}

        <div className="cpt-input-box">
          <input
            ref={fileInputRef}
            type="file"
            className="sr-only"
            accept=".mp4,.mov,.avi,.webm,.mkv,.ts,.wav,.mp3"
            onChange={(e) => {
              const f = e.target.files[0];
              if (f) setAttachedFile(f);
            }}
          />
          <button
            className="cpt-icon-btn cpt-attach-btn"
            onClick={() => fileInputRef.current?.click()}
            title="Attach video file"
          >
            <Plus size={18} />
          </button>

          <textarea
            ref={textareaRef}
            className="cpt-textarea"
            placeholder={activeMode === 'cyber'
              ? "Audit video for deepfakes, frame splices, or tamper analysis..."
              : "Ask video questions, summarize chapters, or paste video URL..."
            }
            value={promptText}
            onChange={(e) => setPromptText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            rows={1}
          />

          <div className="cpt-input-actions-right">
            {/* Gemini-style Model Selector Pill inside Input */}
            <div className="cpt-gemini-pill-wrapper" ref={modelDropdownRef}>
              <button
                type="button"
                className="cpt-gemini-pill-btn"
                onClick={() => setModelDropdownOpen(!modelDropdownOpen)}
                title="Select model"
              >
                <span>{selectedModel === 'deepthink' ? 'Deepthink' : 'Flash'}</span>
                <ChevronDown size={14} className={`cpt-gemini-pill-caret ${modelDropdownOpen ? 'open' : ''}`} />
              </button>

              {modelDropdownOpen && (
                <div className={`cpt-gemini-dropdown ${centered ? 'dropdown-down' : 'dropdown-up'}`}>
                  <div 
                    className={`cpt-gemini-option ${selectedModel === 'flash' ? 'active' : ''}`}
                    onClick={() => switchModel('flash')}
                  >
                    <div className="cpt-gemini-check-col">
                      {selectedModel === 'flash' && <Check size={14} />}
                    </div>
                    <div className="cpt-gemini-option-text">
                      <div className="cpt-gemini-option-title">Chorus Flash</div>
                      <div className="cpt-gemini-option-sub">Fastest answers</div>
                    </div>
                  </div>

                  <div 
                    className={`cpt-gemini-option ${selectedModel === 'deepthink' ? 'active' : ''}`}
                    onClick={() => switchModel('deepthink')}
                  >
                    <div className="cpt-gemini-check-col">
                      {selectedModel === 'deepthink' && <Check size={14} />}
                    </div>
                    <div className="cpt-gemini-option-text">
                      <div className="cpt-gemini-option-title">Chorus Deepthink</div>
                      <div className="cpt-gemini-option-sub">Advanced reasoning</div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {promptText.trim().length > 0 || attachedFile ? (
              <button
                className={`cpt-send-btn ${activeMode === 'cyber' ? 'cyber-send' : ''}`}
                onClick={() => handleSend()}
                title="Send"
              >
                <ArrowUp size={18} />
              </button>
            ) : (
              <button
                className={`cpt-icon-btn cpt-voice-btn ${activeMode === 'cyber' ? 'cyber-voice' : ''} ${isVoiceActive ? 'pulsing' : ''}`}
                onClick={() => setIsVoiceActive(!isVoiceActive)}
                title="Voice Mode"
              >
                <Mic size={18} />
              </button>
            )}
          </div>
        </div>
      </div>
      <div className="cpt-disclaimer">
        Chorus AI can make mistakes. Verify critical evidence.
      </div>
    </div>
  );

  return (
    <div className={`cpt-app ${activeMode === 'cyber' ? 'mode-cyber' : 'mode-general'}`}>

      {/* ──────────────── SIDEBAR ──────────────── */}
      <aside className={`cpt-sidebar ${sidebarOpen ? '' : 'collapsed'}`}>

        {/* Brand & Toggle */}
        <div className="cpt-sidebar-header">
          <div className="cpt-sidebar-brand" onClick={handleNewChat}>
            <span className="cpt-brand-name">Chorus</span>
            {activeMode === 'cyber' ? (
              <span className="cpt-brand-badge cyber">CYBER</span>
            ) : (
              <span className="cpt-brand-badge">ANALYTICS</span>
            )}
          </div>
          <div className="cpt-sidebar-header-actions">
            <button
              className="cpt-icon-btn"
              onClick={() => setSearchOpen(!searchOpen)}
              title="Search investigations"
            >
              <Search size={16} />
            </button>
            <button
              className="cpt-icon-btn"
              onClick={() => setSidebarOpen(false)}
              title="Close sidebar"
            >
              <PanelLeft size={16} />
            </button>
          </div>
        </div>

        {/* Search Bar */}
        {searchOpen && (
          <div className="cpt-sidebar-search">
            <input
              type="text"
              placeholder="Search investigations..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              autoFocus
            />
            {searchFilter && (
              <button onClick={() => setSearchFilter('')}><X size={13} /></button>
            )}
          </div>
        )}

        {/* New Chat / Investigation Button */}
        <div className="cpt-sidebar-newchat">
          <button className="cpt-new-btn" onClick={handleNewChat}>
            <div className="cpt-new-btn-left">
              <span className="cpt-new-icon"><PenLine size={15} /></span>
              <span>New investigation</span>
            </div>
            <span className="cpt-new-badge">Ctrl K</span>
          </button>
        </div>

        {/* Core Intelligence Modules */}
        <div className="cpt-sidebar-nav">
          <div
            className={`cpt-nav-item ${activeMode === 'general' ? 'active-general-nav' : ''}`}
            onClick={() => {
              handleSwitchMode('general');
              handleNewChat();
            }}
            title="Video Analytics & Summarizer Workspace"
          >
            <Film size={15} className={`cpt-nav-icon ${activeMode === 'general' ? 'general-color' : ''}`} />
            <span>Video Analytics</span>
            <span className={`cpt-nav-badge ${activeMode === 'general' ? 'analytics-active' : ''}`}>
              {activeMode === 'general' ? 'Active' : 'Switch'}
            </span>
          </div>

          <div
            className={`cpt-nav-item ${activeMode === 'cyber' ? 'active-cyber-nav' : ''}`}
            onClick={() => {
              handleSwitchMode('cyber');
              handleNewChat();
            }}
            title="Toggle Deepfake & Manipulation Forensic Mode"
          >
            <ShieldAlert size={15} className={`cpt-nav-icon ${activeMode === 'cyber' ? 'cyber-color' : ''}`} />
            <span>Cyber Forensics</span>
            <span className={`cpt-nav-badge ${activeMode === 'cyber' ? 'threat' : ''}`}>
              {activeMode === 'cyber' ? 'Active' : 'Switch'}
            </span>
          </div>

          <div
            className="cpt-nav-item"
            onClick={handleOpenEvidenceRoom}
            title="Open Evidence Room Registry & Timeline Scrubber"
          >
            <Scale size={15} className="cpt-nav-icon" />
            <span>Evidence Room</span>
            <span className="cpt-nav-badge">3 Cases</span>
          </div>

          <div
            className="cpt-nav-item"
            onClick={() => fileInputRef.current?.click()}
            title="Attach and ingest video evidence"
          >
            <UploadCloud size={15} className="cpt-nav-icon" />
            <span>Ingest Media</span>
            <span className="cpt-nav-badge-subtle">Upload</span>
          </div>
        </div>

        {/* History Sections */}
        <div className="cpt-sidebar-history-scroll">
          {pinnedHistory.length > 0 && (
            <div className="cpt-history-section">
              <div className="cpt-history-label">Pinned Investigations</div>
              {pinnedHistory.map(item => (
                <div
                  key={item.id}
                  className={`cpt-history-item ${activeSessionId === item.id ? 'active' : ''}`}
                  onClick={() => setActiveSessionId(item.id)}
                  title={item.title}
                >
                  {item.mode === 'cyber' ? (
                    <ShieldAlert size={14} className="cpt-hist-icon cyber" />
                  ) : item.videoName ? (
                    <Film size={14} className="cpt-hist-icon" />
                  ) : (
                    <MessageSquare size={14} className="cpt-hist-icon" />
                  )}
                  <span className="cpt-hist-title">{item.title}</span>

                  <div className="cpt-hist-actions">
                    <button
                      className="cpt-hist-action-btn"
                      onClick={(e) => handleTogglePin(item.id, e)}
                      title="Unpin"
                    >
                      <Pin size={12} className="pinned" />
                    </button>
                    <button
                      className="cpt-hist-action-btn delete"
                      onClick={(e) => handleDeleteHistory(item.id, e)}
                      title="Delete"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {recentHistory.length > 0 && (
            <div className="cpt-history-section">
              <div className="cpt-history-label">Recent Investigations</div>
              {recentHistory.map(item => (
                <div
                  key={item.id}
                  className={`cpt-history-item ${activeSessionId === item.id ? 'active' : ''}`}
                  onClick={() => setActiveSessionId(item.id)}
                  title={item.title}
                >
                  {item.mode === 'cyber' ? (
                    <ShieldAlert size={14} className="cpt-hist-icon cyber" />
                  ) : item.videoName ? (
                    <Film size={14} className="cpt-hist-icon" />
                  ) : (
                    <MessageSquare size={14} className="cpt-hist-icon" />
                  )}
                  <span className="cpt-hist-title">{item.title}</span>

                  <div className="cpt-hist-actions">
                    <button
                      className="cpt-hist-action-btn"
                      onClick={(e) => handleTogglePin(item.id, e)}
                      title="Pin to top"
                    >
                      <Pin size={12} />
                    </button>
                    <button
                      className="cpt-hist-action-btn delete"
                      onClick={(e) => handleDeleteHistory(item.id, e)}
                      title="Delete"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Pipeline Quality Gate Status Indicator */}
        <div className="cpt-sidebar-status">
          <div className="cpt-status-left">
            <span className="cpt-status-dot" />
            <span>Quality Gate 8/8</span>
          </div>
          <span className="cpt-status-tsa">RFC-3161 TSA</span>
        </div>

        {/* User Profile & Popover Menu */}
        <div className="cpt-sidebar-footer" ref={userMenuRef}>
          {userMenuOpen && (
            <div className="cpt-user-popover">
              <div 
                className="cpt-popover-header-item"
                onClick={() => {
                  setUserMenuOpen(false);
                  setShowProfileModal(true);
                }}
              >
                <div className="cpt-popover-avatar">
                  <img src={`https://ui-avatars.com/api/?name=${encodeURIComponent(userName)}&background=222222&color=ffffff&bold=true`} alt="User" />
                </div>
                <div className="cpt-popover-user-info">
                  <span className="cpt-popover-name">{capitalizedUserName}</span>
                </div>
                <ChevronRight size={16} className="cpt-popover-arrow" />
              </div>

              <div className="cpt-popover-divider" />

              <button 
                className="cpt-popover-item"
                onClick={() => {
                  setUserMenuOpen(false);
                  setShowProfileModal(true);
                }}
              >
                <CircleUser size={16} className="cpt-popover-icon" />
                <span>Profile</span>
              </button>

              <button 
                className="cpt-popover-item"
                onClick={() => {
                  setUserMenuOpen(false);
                  setShowSettingsModal(true);
                }}
              >
                <Settings size={16} className="cpt-popover-icon" />
                <span>Settings</span>
              </button>

              <div className="cpt-popover-divider" />

              <button 
                className="cpt-popover-item"
                onClick={() => {
                  setUserMenuOpen(false);
                  setShowHelpModal(true);
                }}
              >
                <HelpCircle size={16} className="cpt-popover-icon" />
                <span>Help</span>
                <ChevronRight size={15} className="cpt-popover-arrow" />
              </button>

              <button 
                className="cpt-popover-item cpt-popover-logout"
                onClick={() => {
                  setUserMenuOpen(false);
                  logout();
                  window.location.href = '/login';
                }}
              >
                <LogOut size={16} className="cpt-popover-icon" />
                <span>Log out</span>
              </button>
            </div>
          )}

          <div 
            className={`cpt-user-profile ${userMenuOpen ? 'active' : ''}`}
            onClick={() => setUserMenuOpen(!userMenuOpen)}
          >
            <div className="cpt-user-avatar">
              <img src={`https://ui-avatars.com/api/?name=${encodeURIComponent(userName)}&background=222222&color=ffffff&bold=true`} alt="User" />
            </div>
            <div className="cpt-user-info">
              <span className="cpt-user-name">{capitalizedUserName}</span>
            </div>
            <div className="cpt-user-profile-trailing">
              <Store size={15} />
            </div>
          </div>
        </div>
      </aside>

      {/* ──────────────── MAIN AREA ──────────────── */}
      <main className="cpt-main">

        {/* Command Toast Notification */}
        {commandNotification && (
          <div className="cpt-command-toast">
            <span>{commandNotification.text}</span>
          </div>
        )}

        {/* Topbar */}
        <header className="cpt-topbar">
          <div className="cpt-topbar-left">
            {!sidebarOpen ? (
              <div className="cpt-topbar-brand-wrap">
                <button
                  className="cpt-icon-btn"
                  onClick={() => setSidebarOpen(true)}
                  title="Open sidebar"
                >
                  <PanelLeft size={18} />
                </button>
                <div className="cpt-topbar-brand" onClick={handleNewChat}>
                  <span className="cpt-brand-name">Chorus</span>
                  <span className="cpt-brand-badge">{activeMode === 'cyber' ? 'CYBER' : 'AI'}</span>
                </div>
              </div>
            ) : (
              <div />
            )}
          </div>

          {/* Mode Pill Toggle */}
          <div className="cpt-topbar-center">
            <div className="cpt-mode-toggle">
              <button
                className={`cpt-toggle-btn ${activeMode === 'general' ? 'active' : ''}`}
                onClick={() => handleSwitchMode('general')}
                title="Video Analytics & Summarizer"
              >
                <Film size={13} style={{ marginRight: '6px', verticalAlign: '-1px' }} />
                <span>Video Analytics & Summarizer</span>
              </button>
              <button
                className={`cpt-toggle-btn ${activeMode === 'cyber' ? 'active-cyber' : ''}`}
                onClick={() => handleSwitchMode('cyber')}
                title="Forensic Cyber Threat & Deepfake Audit"
              >
                <ShieldAlert size={13} style={{ marginRight: '6px', verticalAlign: '-1px' }} />
                <span>Cyber Forensics</span>
              </button>
            </div>
          </div>

          <div className="cpt-topbar-right" />
        </header>

        {/* Dedicated Distinct Modals */}
        <UserProfileModal 
          isOpen={showProfileModal} 
          onClose={() => setShowProfileModal(false)} 
          userName={capitalizedUserName} 
          userEmail={user?.email} 
        />
        <AppSettingsModal 
          isOpen={showSettingsModal} 
          onClose={() => setShowSettingsModal(false)} 
        />
        <HelpSupportModal 
          isOpen={showHelpModal} 
          onClose={() => setShowHelpModal(false)} 
          onOpenEvidence={handleOpenEvidenceRoom} 
        />

        {/* Content Area */}
        <div className="cpt-content">

          {/* EMPTY STATE */}
          {!activeSession && (
            <div className="cpt-empty-state">
              <h1 className="cpt-greeting">
                {activeMode === 'cyber' ? 'Chorus Cyber Forensics' : `What's next, ${userFirstName}?`}
              </h1>
              <p className="cpt-sub-greeting">
                {activeMode === 'cyber' 
                  ? 'Neural Deepfake Detection, Frame Tampering & Forensic Timeline Integrity'
                  : 'Video Analytics, Chapter Summarization & Multimodal Intelligence'
                }
              </p>

              <ChatInput centered={true} />

              {/* Mode-Specific Quick Suggestion Chips */}
              <div className="cpt-suggestions-row">
                {activeMode === 'cyber' ? (
                  <>
                    <button 
                      className="cpt-suggestion-chip"
                      onClick={() => handleSend("Audit video for facial manipulation, deepfakes, and synthetic artifacts.")}
                    >
                      <ShieldAlert size={13} className="cpt-chip-icon cyber" />
                      <span>Audit for Deepfakes</span>
                    </button>
                    <button 
                      className="cpt-suggestion-chip"
                      onClick={() => handleSend("Inspect optical flow vectors and check for temporal frame splicing.")}
                    >
                      <Zap size={13} className="cpt-chip-icon cyber" />
                      <span>Detect Frame Splices</span>
                    </button>
                    <button 
                      className="cpt-suggestion-chip"
                      onClick={() => handleSend("Verify cryptographic video hash against RFC-3161 TSA ledger.")}
                    >
                      <Scale size={13} className="cpt-chip-icon cyber" />
                      <span>Verify Hash Ledger</span>
                    </button>
                  </>
                ) : (
                  <>
                    <button 
                      className="cpt-suggestion-chip"
                      onClick={() => handleSend("Summarize this video into key chronological chapters and topics.")}
                    >
                      <Film size={13} className="cpt-chip-icon" />
                      <span>Summarize Chapters</span>
                    </button>
                    <button 
                      className="cpt-suggestion-chip"
                      onClick={() => handleSend("Analyze multimodal video dynamics, speaker sentiment, and key metrics.")}
                    >
                      <Brain size={13} className="cpt-chip-icon" />
                      <span>Multimodal Analytics</span>
                    </button>
                    <button 
                      className="cpt-suggestion-chip"
                      onClick={() => handleSend("Extract the primary action sequences and actionable takeaways.")}
                    >
                      <Sparkles size={13} className="cpt-chip-icon" />
                      <span>Actionable Takeaways</span>
                    </button>
                  </>
                )}
              </div>
            </div>
          )}

          {/* CHAT STREAM */}
          {activeSession && (
            <div className="cpt-chat-stream">
              <div className="cpt-messages-container">

                {/* Initial Prompt */}
                {activeSession.prompt && (
                  <div className="cpt-msg user-msg">
                    <div className="cpt-msg-bubble">
                      {activeSession.videoName && (
                        <div className="cpt-msg-attachment-badge">
                          <Film size={13} />
                          <span>{activeSession.videoName}</span>
                        </div>
                      )}
                      {activeSession.prompt}
                    </div>
                  </div>
                )}

                {/* Cyber Mode Report Output */}
                {activeSession.cyberData && (
                  <div className="cpt-msg ai-msg">
                    <div className="cpt-ai-icon cyber-icon">
                      <ShieldAlert size={16} />
                    </div>
                    <div className="cpt-ai-content">
                      <div className="cpt-markdown">

                        {/* Threat Header & Score Gauge */}
                        <div className="cpt-cyber-header">
                          <div>
                            <div className="cpt-cyber-tag-row">
                              <span className="cpt-cyber-tag">CYBER MODE ANALYSIS</span>
                              <span className="cpt-model-indicator-badge">
                                {activeSession.modelUsed === 'deepthink' ? 'Chorus Deepthink' : 'Chorus Flash'}
                              </span>
                            </div>
                            <h2 className="cpt-cyber-title">{activeSession.cyberData.classification}</h2>
                          </div>

                          <div className={`cpt-threat-badge ${activeSession.cyberData.threatLevel.toLowerCase()}`}>
                            <div className="cpt-threat-score">{activeSession.cyberData.threatScore}<span>/100</span></div>
                            <div className="cpt-threat-label">{activeSession.cyberData.threatLevel} THREAT</div>
                          </div>
                        </div>

                        {/* Collapsible Deepthink Thought Process if available */}
                        {activeSession.messages?.[1]?.thoughtProcess && (
                          <div className="cpt-thought-container">
                            <button
                              type="button"
                              className="cpt-thought-toggle"
                              onClick={() => toggleThought(activeSession.messages[1].id)}
                            >
                              <div className="cpt-thought-header-left">
                                <Brain size={14} className="cpt-thought-icon" />
                                <span className="cpt-thought-label">
                                  {expandedThoughts[activeSession.messages[1].id] ? 'Forensic Reasoning Steps' : `Thought for ${activeSession.messages[1].thoughtTime || '3.4s'}`}
                                </span>
                              </div>
                              <ChevronDown size={14} className={`cpt-thought-arrow ${expandedThoughts[activeSession.messages[1].id] ? 'expanded' : ''}`} />
                            </button>
                            {expandedThoughts[activeSession.messages[1].id] && (
                              <div className="cpt-thought-content">
                                {activeSession.messages[1].thoughtProcess.map((step, sIdx) => (
                                  <div key={sIdx} className="cpt-thought-step">
                                    <span className="cpt-thought-step-num">{sIdx + 1}</span>
                                    <span className="cpt-thought-step-text">{step}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Status bar */}
                        <div className="cpt-cyber-status-bar">
                          <div className="cpt-status-item">
                            <span className="cpt-status-label">Integrity Status:</span>
                            <span className="cpt-status-val danger">{activeSession.cyberData.integrityStatus}</span>
                          </div>
                          <div className="cpt-status-item">
                            <span className="cpt-status-label">Ledger Hash:</span>
                            <span className="cpt-status-val">{activeSession.cyberData.hashMatch}</span>
                          </div>
                        </div>

                        {/* Anomalies Detected */}
                        <h3>Detected Anomalies & Tamper Indicators</h3>
                        <div className="cpt-cyber-anomalies">
                          {activeSession.cyberData.anomalies.map((ano, i) => (
                            <div key={i} className="cpt-anomaly-card">
                              <div className="cpt-anomaly-header">
                                <span className="cpt-anomaly-time">{ano.time}</span>
                                <span className="cpt-anomaly-type">{ano.type}</span>
                                <span className={`cpt-anomaly-sev ${ano.severity.toLowerCase()}`}>{ano.severity}</span>
                              </div>
                              <p className="cpt-anomaly-desc">{ano.desc}</p>
                            </div>
                          ))}
                        </div>

                        {/* Mitigation Actions */}
                        <h3>Cyber Mitigation & Follow-up Actions</h3>
                        <ul className="cpt-action-list">
                          {activeSession.cyberData.mitigationActions.map((act, i) => (
                            <li key={i}>{act}</li>
                          ))}
                        </ul>

                        {/* Action buttons */}
                        <div className="cpt-ai-actions-bar">
                          <button
                            className="cpt-msg-action-btn"
                            onClick={() => handleCopy(JSON.stringify(activeSession.cyberData, null, 2), 'cyber-data')}
                          >
                            {copiedId === 'cyber-data' ? <Check size={14} /> : <Copy size={14} />}
                            <span>{copiedId === 'cyber-data' ? 'Copied' : 'Copy'}</span>
                          </button>
                          <button className="cpt-msg-action-btn"><ThumbsUp size={14} /></button>
                          <button className="cpt-msg-action-btn"><ThumbsDown size={14} /></button>
                          <button
                            className="cpt-msg-action-btn"
                            onClick={() => handleSend(activeSession.prompt)}
                          >
                            <RotateCcw size={14} />
                            <span>Rescan</span>
                          </button>
                          <button
                            className="cpt-msg-action-btn highlight-evidence"
                            onClick={handleOpenEvidenceRoom}
                            title="Verify in Evidence Room Scrubber"
                          >
                            <Scale size={14} />
                            <span>Open in Evidence Room ↗</span>
                          </button>
                        </div>

                      </div>
                    </div>
                  </div>
                )}

                {/* General Mode Summary Output */}
                {activeSession.summary && (
                  <div className="cpt-msg ai-msg">
                    <div className="cpt-ai-icon">
                      <Sparkles size={16} />
                    </div>
                    <div className="cpt-ai-content">
                      <div className="cpt-markdown">

                        <div className="cpt-summary-header">
                          <div>
                            <div className="cpt-summary-title-row">
                              <h2>{activeSession.summary.title}</h2>
                              <span className="cpt-model-indicator-badge">
                                {activeSession.modelUsed === 'deepthink' ? 'Chorus Deepthink' : 'Chorus Flash'}
                              </span>
                            </div>
                          </div>
                          {activeSession.summary.dynamics && (
                            <div className="cpt-status-pills">
                              <span className="cpt-pill neutral">
                                <Clock size={12} /> {activeSession.summary.dynamics.analyzedFrames}
                              </span>
                            </div>
                          )}
                        </div>

                        {/* Collapsible Deepthink Thought Process if available */}
                        {activeSession.messages?.[1]?.thoughtProcess && (
                          <div className="cpt-thought-container">
                            <button
                              type="button"
                              className="cpt-thought-toggle"
                              onClick={() => toggleThought(activeSession.messages[1].id)}
                            >
                              <div className="cpt-thought-header-left">
                                <Brain size={14} className="cpt-thought-icon" />
                                <span className="cpt-thought-label">
                                  {expandedThoughts[activeSession.messages[1].id] ? 'Multimodal Reasoning Steps' : `Thought for ${activeSession.messages[1].thoughtTime || '2.8s'}`}
                                </span>
                              </div>
                              <ChevronDown size={14} className={`cpt-thought-arrow ${expandedThoughts[activeSession.messages[1].id] ? 'expanded' : ''}`} />
                            </button>
                            {expandedThoughts[activeSession.messages[1].id] && (
                              <div className="cpt-thought-content">
                                {activeSession.messages[1].thoughtProcess.map((step, sIdx) => (
                                  <div key={sIdx} className="cpt-thought-step">
                                    <span className="cpt-thought-step-num">{sIdx + 1}</span>
                                    <span className="cpt-thought-step-text">{step}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        <p className="cpt-overview-text">{activeSession.summary.overview}</p>

                        <h3>Key Takeaways</h3>
                        <div className="cpt-takeaways-grid">
                          {activeSession.summary.takeaways.map((t, i) => (
                            <div key={i} className="cpt-takeaway-card">
                              <span className="cpt-takeaway-label">{t.label}</span>
                              <span className="cpt-takeaway-detail">{t.detail}</span>
                            </div>
                          ))}
                        </div>

                        {activeSession.summary.chapters?.length > 0 && (
                          <>
                            <h3>Scene Chapters</h3>
                            <div className="cpt-chapters-list">
                              {activeSession.summary.chapters.map((c, i) => (
                                <div key={i} className="cpt-chapter-row">
                                  <span className="cpt-chapter-time">{c.time}</span>
                                  <div className="cpt-chapter-body">
                                    <strong>{c.title}</strong>
                                    <p>{c.desc}</p>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </>
                        )}

                        {activeSession.summary.actionItems?.length > 0 && (
                          <>
                            <h3>Action Items</h3>
                            <ul className="cpt-action-list">
                              {activeSession.summary.actionItems.map((a, i) => (
                                <li key={i}>{a}</li>
                              ))}
                            </ul>
                          </>
                        )}

                        <div className="cpt-ai-actions-bar">
                          <button
                            className="cpt-msg-action-btn"
                            onClick={() => handleCopy(activeSession.summary.overview, 'summary')}
                          >
                            {copiedId === 'summary' ? <Check size={14} /> : <Copy size={14} />}
                            <span>{copiedId === 'summary' ? 'Copied' : 'Copy'}</span>
                          </button>
                          <button className="cpt-msg-action-btn"><ThumbsUp size={14} /></button>
                          <button className="cpt-msg-action-btn"><ThumbsDown size={14} /></button>
                          <button
                            className="cpt-msg-action-btn"
                            onClick={() => handleSend(activeSession.prompt)}
                          >
                            <RotateCcw size={14} />
                            <span>Regenerate</span>
                          </button>
                          <button
                            className="cpt-msg-action-btn highlight-evidence"
                            onClick={handleOpenEvidenceRoom}
                          >
                            <Scale size={14} />
                            <span>Evidence Room ↗</span>
                          </button>
                        </div>

                      </div>
                    </div>
                  </div>
                )}

                {/* Follow-up messages */}
                {activeSession.messages?.slice(2).map((msg) => (
                  <div key={msg.id || Math.random()} className={`cpt-msg ${msg.sender === 'user' ? 'user-msg' : 'ai-msg'}`}>
                    {msg.sender === 'assistant' && (
                      <div className={`cpt-ai-icon ${activeMode === 'cyber' ? 'cyber-icon' : (msg.modelUsed === 'deepthink' ? 'deepthink-icon' : '')}`}>
                        {activeMode === 'cyber' ? <ShieldAlert size={16} /> : (msg.modelUsed === 'deepthink' ? <Brain size={16} /> : <Sparkles size={16} />)}
                      </div>
                    )}
                    <div className={msg.sender === 'user' ? 'cpt-msg-bubble' : 'cpt-ai-content'}>
                      {msg.sender === 'user' ? (
                        msg.text
                      ) : (
                        <div className="cpt-markdown">
                          {msg.modelUsed && (
                            <div style={{ marginBottom: '8px' }}>
                              <span className="cpt-model-indicator-badge">
                                {msg.modelUsed === 'deepthink' ? 'Chorus Deepthink' : 'Chorus Flash'}
                              </span>
                            </div>
                          )}

                          {/* Collapsible Deepthink Thought Process if available */}
                          {msg.thoughtProcess && (
                            <div className="cpt-thought-container">
                              <button
                                type="button"
                                className="cpt-thought-toggle"
                                onClick={() => toggleThought(msg.id)}
                              >
                                <div className="cpt-thought-header-left">
                                  <Brain size={14} className="cpt-thought-icon" />
                                  <span className="cpt-thought-label">
                                    {expandedThoughts[msg.id] ? 'Forensic Reasoning Steps' : `Thought for ${msg.thoughtTime || '2.1s'}`}
                                  </span>
                                </div>
                                <ChevronDown size={14} className={`cpt-thought-arrow ${expandedThoughts[msg.id] ? 'expanded' : ''}`} />
                              </button>
                              {expandedThoughts[msg.id] && (
                                <div className="cpt-thought-content">
                                  {msg.thoughtProcess.map((step, sIdx) => (
                                    <div key={sIdx} className="cpt-thought-step">
                                      <span className="cpt-thought-step-num">{sIdx + 1}</span>
                                      <span className="cpt-thought-step-text">{step}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}

                          <p style={{ whiteSpace: 'pre-line' }}>{msg.text}</p>
                          <div className="cpt-ai-actions-bar">
                            <button
                              className="cpt-msg-action-btn"
                              onClick={() => handleCopy(msg.text, msg.id)}
                            >
                              {copiedId === msg.id ? <Check size={14} /> : <Copy size={14} />}
                            </button>
                            <button className="cpt-msg-action-btn"><ThumbsUp size={14} /></button>
                            <button className="cpt-msg-action-btn"><ThumbsDown size={14} /></button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {/* Loading indicator */}
                {isGenerating && (
                  <div className="cpt-msg ai-msg">
                    <div className={`cpt-ai-icon ${activeMode === 'cyber' ? 'cyber-icon' : (selectedModel === 'deepthink' ? 'deepthink-icon' : '')}`}>
                      {activeMode === 'cyber' ? <ShieldAlert size={16} /> : (selectedModel === 'deepthink' ? <Brain size={16} /> : <Zap size={16} />)}
                    </div>
                    <div className="cpt-ai-content cpt-loading">
                      {isThinking ? (
                        <div className="cpt-thinking-step">
                          <Brain size={14} className="cpt-spin-slow" />
                          <span>{activeMode === 'cyber' ? 'Chorus Deepthink: Analyzing optical vectors & tamper signatures...' : 'Chorus Deepthink: Synthesizing multimodal video intelligence & reasoning...'}</span>
                        </div>
                      ) : (
                        <div className="cpt-thinking-step">
                          <Zap size={14} />
                          <span>Chorus Flash: Streaming real-time response...</span>
                        </div>
                      )}
                      <div className="cpt-dot-flashing"></div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Chat Input pinned to bottom */}
              <div className="cpt-bottom-input-container">
                <ChatInput centered={false} />
              </div>

            </div>
          )}
        </div>
      </main>
    </div>
  );
}
