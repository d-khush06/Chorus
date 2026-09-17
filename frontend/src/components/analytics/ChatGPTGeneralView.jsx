import React, { useState, useEffect, useRef, useContext } from 'react';
import AuthContext from '../../context/AuthContext';
import './ChatGPTGeneralView.css';
import { Sparkles, MessageSquare, X, Folder, ArrowLeftRight, Play, BarChart2, Target, Clock, Lightbulb, Users, Pin, Check, Copy, RefreshCcw, Film } from 'lucide-react';

// Default initial history sessions
const INITIAL_HISTORY = [
  {
    id: 'hist-1',
    title: 'Q3 Quarterly Performance Review',
    timestamp: 'Today',
    videoName: 'Q3_Executive_Briefing.mp4',
    prompt: 'Summarize the Q3 executive review video and highlight major regional benchmarks and next steps.',
    summary: {
      title: 'Q3 Quarterly Performance Review & Financial Benchmarks',
      overview: 'A comprehensive executive review of Q3 organizational metrics, regional performance highlights, and strategic operational goals. Overall team delivery exceeded quarterly revenue targets by 12%, driven predominantly by rapid enterprise adoption of the newly released product line across the Asia-Pacific region.',
      takeaways: [
        { label: 'Exceeded Targets by 12%', detail: 'Overall organization outpaced performance benchmarks across all primary business divisions.' },
        { label: 'APAC Expansion Success', detail: 'The newly deployed product tier achieved unprecedented enterprise retention and expansion in Asia-Pacific.' },
        { label: 'Marketing Attribution Gap', detail: 'Identified a need to optimize marketing spend by implementing multi-touch attribution models before Q4 budget allocation.' },
        { label: 'Three Strategic Initiatives', detail: 'Greenlit three core cross-functional initiatives to automate pipeline workflows and streamline delivery.' }
      ],
      chapters: [
        { time: '00:04 – 00:22', title: 'Executive Welcome & Metric Benchmarks', desc: 'Speaker opens the meeting, presenting the live KPI dashboard highlighting the 12% over-target revenue milestone.' },
        { time: '00:25 – 00:55', title: 'Product Adoption & APAC Expansion', desc: 'Deep dive into the Asia-Pacific launch results, highlighting enterprise market demand and customer satisfaction.' },
        { time: '01:00 – 01:14', title: 'Operational Critique: Marketing ROI', desc: 'Critical evaluation of current marketing channels, calling for an immediate audit and improved attribution modeling.' },
        { time: '01:20 – 03:07', title: 'Strategic Roadmap & Final Directives', desc: 'Outline of three upcoming operational initiatives, resource allocations, and closing Q&A.' }
      ],
      dynamics: {
        tone: 'Confident, Collaborative & Analytical',
        sentiment: 'Predominantly Positive (62% Positive, 27% Neutral, 11% Constructive Critique)',
        speakers: '3 Active Speakers (VP Operations, Product Lead, Finance Director)',
        engagement: 'High (84%), with peak interaction occurring during the marketing attribution discussion.'
      },
      actionItems: [
        'Perform an end-to-end audit of digital marketing acquisition channels and implement multi-touch attribution.',
        'Accelerate regional deployment logistics in APAC to maintain current momentum.',
        'Finalize project charters and cross-functional teams for the three Q4 strategic initiatives by Friday.'
      ]
    },
    messages: []
  },
  {
    id: 'hist-2',
    title: 'Product Launch Keynote 2024',
    timestamp: 'Yesterday',
    videoName: 'Keynote_Product_Reveal.mp4',
    prompt: 'Provide an executive summary of the keynote reveal.',
    summary: {
      title: 'Univance Product Launch Keynote 2024',
      overview: 'The keynote presentation unveiled Univance v2.0, focusing on real-time neural multimodal video intelligence, sub-100ms latency inference, and decentralized evidence integrity verification.',
      takeaways: [
        { label: 'Next-Gen Platform Launch', detail: 'Univance 2.0 announced with automated video scene comprehension and tamper detection.' },
        { label: 'Enterprise Security Compliance', detail: 'Full SOC-2 and HIPAA compliance verification integrated into the ingest pipeline.' },
        { label: 'Developer SDK Availability', detail: 'Beta access opened for developer APIs with Python and Node.js client bindings.' }
      ],
      chapters: [
        { time: '00:00 – 05:30', title: 'Opening Address & Industry Vision', desc: 'Overview of modern video data overload and the emergence of multimodal AI.' },
        { time: '05:30 – 14:15', title: 'Live Product Demonstration', desc: 'Real-time scene segmentation, speaker diarization, and forensic threat analysis demonstrated on stage.' },
        { time: '14:15 – 22:00', title: 'Ecosystem & Availability', desc: 'Pricing tiers, enterprise rollout timeline, and community developer program launch.' }
      ],
      dynamics: {
        tone: 'Inspirational & High Energy',
        sentiment: 'Overwhelmingly Positive (89% Positive, 11% Neutral)',
        speakers: '2 Keynote Speakers (Chief Executive Officer, Head of AI Research)',
        engagement: 'Extremely High (94%)'
      },
      actionItems: [
        'Onboard initial enterprise tier beta partners.',
        'Publish public documentation and developer SDK packages.',
        'Schedule follow-up technical webinars for engineering teams.'
      ]
    },
    messages: []
  },
  {
    id: 'hist-3',
    title: 'Townhall: Engineering Roadmap',
    timestamp: 'Previous 7 Days',
    videoName: 'Engineering_All_Hands.mp4',
    prompt: 'Summarize the engineering all hands roadmap.',
    summary: {
      title: 'Engineering All-Hands: Technical Roadmap & Architecture',
      overview: 'Technical leadership review addressing cloud infrastructure optimization, microservices decoupling, and automated CI/CD security gating.',
      takeaways: [
        { label: 'Infrastructure Cost Reduction', detail: 'Cloud compute expenditure trimmed by 24% following GPU cluster autoscaling.' },
        { label: 'Model Latency Optimization', detail: 'Quantization and ONNX runtime integration reduced inference time from 4.2s to 1.1s.' }
      ],
      chapters: [
        { time: '00:00 – 08:20', title: 'Architecture Refactor Review', desc: 'Migration from monolithic ingestion to distributed event-driven microservices.' },
        { time: '08:20 – 18:00', title: 'Security & Quality Gate Standards', desc: 'Introduction of mandatory automated integrity tests for video ingest pipelines.' }
      ],
      dynamics: {
        tone: 'Technical, Methodical & Focused',
        sentiment: 'Balanced & Constructive (70% Positive, 25% Neutral, 5% Challenges noted)',
        speakers: '4 Engineering Leads',
        engagement: 'High (80%)'
      },
      actionItems: [
        'Complete Kubernetes cluster migration by end of month.',
        'Roll out automated testing suites across all media ingest workers.'
      ]
    },
    messages: []
  }
];

export default function ChatGPTGeneralView({ onBack, onGoToEvidence }) {
  const { user, logout } = useContext(AuthContext);

  // Sessions / History
  const [history, setHistory] = useState(() => {
    try {
      const saved = localStorage.getItem('univance_general_history');
      return saved ? JSON.parse(saved) : INITIAL_HISTORY;
    } catch {
      return INITIAL_HISTORY;
    }
  });

  const [activeSessionId, setActiveSessionId] = useState(() => history[0]?.id || null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Active chat state
  const [activeSession, setActiveSession] = useState(() => history[0] || null);
  const [promptText, setPromptText] = useState('');
  const [attachedFile, setAttachedFile] = useState(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatingStep, setGeneratingStep] = useState('');
  const [copied, setCopied] = useState(false);

  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Save history on changes
  useEffect(() => {
    try {
      localStorage.setItem('univance_general_history', JSON.stringify(history));
    } catch (e) {
      console.warn('Could not save history to localStorage', e);
    }
  }, [history]);

  // Sync active session when selection changes
  useEffect(() => {
    if (activeSessionId) {
      const found = history.find(h => h.id === activeSessionId);
      if (found) {
        setActiveSession(found);
      }
    } else {
      setActiveSession(null);
    }
  }, [activeSessionId, history]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession?.messages, isGenerating]);

  // Handle creating a brand new chat
  const handleNewChat = () => {
    setActiveSessionId(null);
    setActiveSession(null);
    setPromptText('');
    setAttachedFile(null);
    setIsGenerating(false);
  };

  // Handle deleting a session
  const handleDeleteSession = (e, id) => {
    e.stopPropagation();
    const updated = history.filter(h => h.id !== id);
    setHistory(updated);
    if (activeSessionId === id) {
      if (updated.length > 0) {
        setActiveSessionId(updated[0].id);
      } else {
        handleNewChat();
      }
    }
  };

  // Generate a realistic, rich summary based on input
  const createSummaryResponse = (title, file) => {
    const cleanTitle = (file ? file.name : title)
      .replace(/\.[^/.]+$/, '')
      .replace(/[-_]/g, ' ')
      .trim();

    return {
      title: cleanTitle.length > 3 ? cleanTitle.charAt(0).toUpperCase() + cleanTitle.slice(1) : 'Video Content Analysis & Summary',
      overview: `A complete executive AI briefing synthesized from the ingested media. The video details operational milestones, performance assessments, and core strategic deliverables. The discussion highlights strong momentum in adoption, coupled with key recommendations for optimizing workflow execution and cross-team alignment.`,
      takeaways: [
        { label: 'Milestone Execution', detail: 'Key quarterly objectives delivered ahead of initial timeline projections with measurable positive impact.' },
        { label: 'Market Traction', detail: 'Strong customer validation observed across primary target segments and regional rollout zones.' },
        { label: 'Resource Realignment', detail: 'Recommended reallocation of focus toward automated attribution modeling and streamlined delivery pipelines.' },
        { label: 'Clear Strategic Directives', detail: 'Leadership agreed on prioritized workstreams for the upcoming operational cycle.' }
      ],
      chapters: [
        { time: '00:00 – 00:45', title: 'Introduction & Strategic Context', desc: 'Opening framing of core objectives, agenda alignment, and review of historical benchmark data.' },
        { time: '00:45 – 01:50', title: 'Performance Metrics & Evidence Review', desc: 'Detailed walkthrough of performance data, customer engagement metrics, and growth indicators.' },
        { time: '01:50 – 02:40', title: 'Discussion & Operational Recommendations', desc: 'Constructive critique addressing resource bottlenecks, attribution analysis, and optimization proposals.' },
        { time: '02:40 – End', title: 'Summary & Actionable Next Steps', desc: 'Consensus on immediate next steps, owner assignments, and timeline commitments.' }
      ],
      dynamics: {
        tone: 'Productive, Confident & Forward-Looking',
        sentiment: 'Predominantly Positive (68% Positive, 24% Neutral, 8% Critical)',
        speakers: 'Multi-speaker collaborative format',
        engagement: 'High (86%) sustained throughout the presentation.'
      },
      actionItems: [
        'Review and implement suggested pipeline attribution adjustments before the next review cycle.',
        'Distribute action item assignments and milestones to department leads.',
        'Schedule follow-up progress sync to verify deliverable completion.'
      ]
    };
  };

  // Submit a video for analysis or follow-up question
  const handleSend = async () => {
    const trimmed = promptText.trim();
    if (!trimmed && !attachedFile) return;

    // Case 1: Starting a new analysis or currently on empty chat
    if (!activeSession || !activeSession.summary) {
      const newId = 'hist-' + Date.now();
      const videoName = attachedFile ? attachedFile.name : (trimmed.length > 25 ? trimmed.substring(0, 25) + '...' : trimmed);
      const title = attachedFile ? attachedFile.name.replace(/\.[^/.]+$/, '') : (trimmed.length > 32 ? trimmed.substring(0, 32) + '...' : trimmed);

      const userMsg = {
        sender: 'user',
        text: trimmed || 'Please analyze this video and provide a comprehensive executive summary with key takeaways and action items.',
        attachment: attachedFile ? attachedFile.name : null
      };

      const newSessionStub = {
        id: newId,
        title: title || 'New Video Analysis',
        timestamp: 'Just now',
        videoName,
        prompt: userMsg.text,
        summary: null,
        messages: [userMsg]
      };

      setActiveSession(newSessionStub);
      setHistory(prev => [newSessionStub, ...prev]);
      setActiveSessionId(newId);
      setPromptText('');
      setAttachedFile(null);
      setIsGenerating(true);

      // Simulation of AI processing steps
      setGeneratingStep('Scanning video scenes & extracting audio transcripts...');
      await new Promise(r => setTimeout(r, 1100));

      setGeneratingStep('Analyzing speech sentiment & identifying key speakers...');
      await new Promise(r => setTimeout(r, 1100));

      setGeneratingStep('Synthesizing executive summary & action items...');
      await new Promise(r => setTimeout(r, 1200));

      const generatedSummary = createSummaryResponse(title, attachedFile);

      const completedSession = {
        ...newSessionStub,
        summary: generatedSummary,
        messages: [
          userMsg,
          {
            sender: 'assistant',
            isSummary: true,
            summaryData: generatedSummary
          }
        ]
      };

      setActiveSession(completedSession);
      setHistory(prev => prev.map(item => item.id === newId ? completedSession : item));
      setIsGenerating(false);
      setGeneratingStep('');
      return;
    }

    // Case 2: Follow-up question in existing session
    const userFollowUp = {
      sender: 'user',
      text: trimmed,
      attachment: attachedFile ? attachedFile.name : null
    };

    const updatedMessages = [...(activeSession.messages || []), userFollowUp];

    setActiveSession(prev => ({ ...prev, messages: updatedMessages }));
    setPromptText('');
    setAttachedFile(null);
    setIsGenerating(true);
    setGeneratingStep('Analyzing query against video transcript...');

    await new Promise(r => setTimeout(r, 1200));

    // Formulate intelligent conversational reply
    let replyText = '';
    const q = trimmed.toLowerCase();

    if (q.includes('market') || q.includes('spend') || q.includes('attribution')) {
      replyText = `Regarding the marketing evaluation: The review highlighted that while customer acquisition has been strong, the team needs to optimize digital marketing spend. Specifically, they decided to implement multi-touch attribution models before committing to next quarter's budget to avoid unnecessary ad spend.`;
    } else if (q.includes('action') || q.includes('next step') || q.includes('todo')) {
      replyText = `Here are the top action items established in the meeting:\n1. Audit digital marketing channels and deploy multi-touch attribution.\n2. Accelerate APAC distribution logistics to sustain growth momentum.\n3. Finalize project charters and cross-functional team assignments by this Friday.`;
    } else if (q.includes('speaker') || q.includes('who')) {
      replyText = `The discussion involved 3 primary participants: the Vice President of Operations (meeting host), the Product Lead (who presented regional performance), and the Finance Director (who evaluated marketing spend and budget allocation).`;
    } else if (q.includes('apac') || q.includes('asia') || q.includes('region')) {
      replyText = `The Asia-Pacific region was the top growth driver highlighted in the review, significantly exceeding adoption projections and driving the overall 12% revenue outperformance for the new product tier.`;
    } else {
      replyText = `Based on the video analysis for "${activeSession.title}": The primary consensus was that operational delivery is strong (12% above benchmark), with immediate priorities focused on streamlining marketing attribution and scaling regional logistics. Let me know if you would like specific timestamps or quotes from the transcript!`;
    }

    const aiReply = {
      sender: 'assistant',
      isSummary: false,
      text: replyText
    };

    const finalSession = {
      ...activeSession,
      messages: [...updatedMessages, aiReply]
    };

    setActiveSession(finalSession);
    setHistory(prev => prev.map(item => item.id === activeSession.id ? finalSession : item));
    setIsGenerating(false);
    setGeneratingStep('');
  };

  const handleCopySummary = (summary) => {
    if (!summary) return;
    const text = `
${summary.title}
==============================
EXECUTIVE OVERVIEW:
${summary.overview}

KEY TAKEAWAYS:
${summary.takeaways.map(t => `• ${t.label}: ${t.detail}`).join('\n')}

TIMELINE BREAKDOWN:
${summary.chapters.map(c => `[${c.time}] ${c.title} — ${c.desc}`).join('\n')}

ACTION ITEMS:
${summary.actionItems.map((a, i) => `${i + 1}. ${a}`).join('\n')}
    `.trim();

    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="cpt-container">
      
      {/* ── Left Sidebar: History & Navigation ── */}
      <aside className={`cpt-sidebar ${sidebarOpen ? '' : 'collapsed'}`}>
        <div className="cpt-sidebar__header">
          <div className="cpt-brand">
            <div className="cpt-logo">
              <svg viewBox="0 0 24 24" fill="none" className="cpt-logo-icon">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <span className="cpt-logo-title">UNIVANCE AI</span>
            </div>
            <span className="cpt-mode-badge">General</span>
          </div>

          <button className="cpt-new-btn" onClick={handleNewChat}>
            <span>+ New Analysis</span>
            <span className="cpt-new-btn__icon"><Sparkles size={16} /></span>
          </button>
        </div>

        {/* History list */}
        <div className="cpt-sidebar__history">
          <div className="cpt-history-group-label">Recent Summaries</div>
          {history.map((item) => (
            <div
              key={item.id}
              className={`cpt-history-item ${activeSessionId === item.id ? 'active' : ''}`}
              onClick={() => setActiveSessionId(item.id)}
            >
              <div className="cpt-history-item__left">
                <span className="cpt-history-item__icon"><MessageSquare size={14} /></span>
                <span className="cpt-history-item__title">{item.title}</span>
              </div>
              <button
                className="cpt-history-item__del"
                onClick={(e) => handleDeleteSession(e, item.id)}
                title="Delete summary"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>

        {/* Sidebar Footer */}
        <div className="cpt-sidebar__footer">
          <div className="cpt-user-badge">
            <div className="cpt-user-avatar">
              {(user?.email || 'U').charAt(0).toUpperCase()}
            </div>
            <span className="cpt-user-email">{user?.email || 'user@univance.ai'}</span>
          </div>

          <div className="cpt-footer-actions">
            {onGoToEvidence && (
              <button className="cpt-footer-btn" onClick={onGoToEvidence} title="Open Evidence Room">
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Folder size={14} /> Evidence</span>
              </button>
            )}
            {onBack && (
              <button className="cpt-footer-btn" onClick={onBack} title="Switch Mode">
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><ArrowLeftRight size={14} /> Mode</span>
              </button>
            )}
            <button
              className="cpt-footer-btn cpt-footer-btn--danger"
              onClick={() => { logout(); window.location.href = '/login'; }}
              title="Sign Out"
            >
              <span>Log out</span>
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main Chat Area ── */}
      <main className="cpt-main">
        {/* Top bar */}
        <header className="cpt-topbar">
          <div className="cpt-topbar__left">
            <button
              className="cpt-toggle-btn"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              title={sidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="2"/>
                <path d="M9 3v18" stroke="currentColor" strokeWidth="2"/>
              </svg>
            </button>

            <div className="cpt-model-selector">
              <span className="cpt-model-dot" />
              <span>Univance Intelligence 4o (General Video Mode)</span>
            </div>
          </div>

          <div className="cpt-topbar__right">
            {onGoToEvidence && (
              <button className="cpt-mode-switch-btn" onClick={onGoToEvidence}>
                <span>Evidence Room</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </button>
            )}
          </div>
        </header>

        {/* Chat Messages Stream */}
        <div className="cpt-chat-stream">
          <div className="cpt-content-width">
            
            {/* Empty State / Welcome Screen */}
            {(!activeSession || (!activeSession.summary && (!activeSession.messages || activeSession.messages.length === 0))) && (
              <div className="cpt-empty-state">
                <div className="cpt-empty-icon">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                    <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2v10z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
                <h1 className="cpt-empty-title">What video would you like to summarize?</h1>
                <p className="cpt-empty-subtitle">
                  Upload any video recording, meeting, or paste a URL to receive an executive AI briefing with key decisions and actionable takeaways.
                </p>

                <div className="cpt-suggestion-grid">
                  <div
                    className="cpt-suggestion-card"
                    onClick={() => {
                      setPromptText('Summarize Q3 Business Review video and extract the financial performance benchmarks.');
                    }}
                  >
                    <div className="cpt-suggestion-card__title"><BarChart2 size={16} style={{ marginRight: '6px', verticalAlign: 'text-bottom' }} /> Q3 Performance Review</div>
                    <div className="cpt-suggestion-card__desc">Synthesize revenue benchmarks, milestones, and over-target delivery.</div>
                  </div>

                  <div
                    className="cpt-suggestion-card"
                    onClick={() => {
                      setPromptText('Extract the top decisions, speaker disagreements, and action items from this meeting.');
                    }}
                  >
                    <div className="cpt-suggestion-card__title"><Target size={16} style={{ marginRight: '6px', verticalAlign: 'text-bottom' }} /> Key Decisions & Action Items</div>
                    <div className="cpt-suggestion-card__desc">Identify assignees, due dates, and strategic takeaways.</div>
                  </div>

                  <div
                    className="cpt-suggestion-card"
                    onClick={() => {
                      setPromptText('Generate a timestamped chapter breakdown and sentiment flow of this video call.');
                    }}
                  >
                    <div className="cpt-suggestion-card__title"><Clock size={16} style={{ marginRight: '6px', verticalAlign: 'text-bottom' }} /> Timestamped Chapter Brief</div>
                    <div className="cpt-suggestion-card__desc">Chronological chapter-by-chapter narrative with exact timestamps.</div>
                  </div>

                  <div
                    className="cpt-suggestion-card"
                    onClick={() => {
                      setPromptText('Summarize the product keynote reveal and market availability dates.');
                    }}
                  >
                    <div className="cpt-suggestion-card__title"><Lightbulb size={16} style={{ marginRight: '6px', verticalAlign: 'text-bottom' }} /> Product Launch Highlights</div>
                    <div className="cpt-suggestion-card__desc">Key announcements, feature capabilities, and rollout schedule.</div>
                  </div>
                </div>
              </div>
            )}

            {/* Conversation Stream */}
            {activeSession && (
              <div className="cpt-messages-list">
                
                {/* Initial User Prompt */}
                {activeSession.prompt && (
                  <div className="cpt-msg-row cpt-msg-row--user">
                    <div className="cpt-user-bubble">
                      {activeSession.videoName && (
                        <div className="cpt-user-attachment">
                          <span><Play size={12} fill="currentColor" /></span>
                          <span>{activeSession.videoName}</span>
                        </div>
                      )}
                      <div className="cpt-user-text">{activeSession.prompt}</div>
                    </div>
                  </div>
                )}

                {/* Generating / Thinking Indicator */}
                {isGenerating && (
                  <div className="cpt-msg-row cpt-msg-row--assistant">
                    <div className="cpt-ai-avatar"><Sparkles size={18} /></div>
                    <div className="cpt-ai-body">
                      <div className="cpt-thinking-box">
                        <span className="cpt-sparkle-spin"><Sparkles size={16} /></span>
                        <span className="cpt-thinking-text">{generatingStep || 'Thinking & synthesizing video summary...'}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Full Executive Summary Display */}
                {activeSession.summary && (
                  <div className="cpt-msg-row cpt-msg-row--assistant">
                    <div className="cpt-ai-avatar"><Sparkles size={18} /></div>
                    <div className="cpt-ai-body">
                      <div className="cpt-summary-card">
                        
                        {/* Header Hero */}
                        <div className="cpt-summary-card__hero">
                          <div className="cpt-summary-card__tag">
                            <span><Sparkles size={12} /></span>
                            <span>Executive Video Summary</span>
                          </div>
                          <h2 className="cpt-summary-card__title">{activeSession.summary.title}</h2>
                          <p className="cpt-summary-card__lead">{activeSession.summary.overview}</p>
                        </div>

                        {/* Core Key Takeaways */}
                        <div className="cpt-summary-card__section">
                          <div className="cpt-sec-heading">
                            <span><Target size={16} /></span>
                            <span>Core Takeaways & Findings</span>
                          </div>
                          <div className="cpt-takeaways-list">
                            {activeSession.summary.takeaways.map((t, idx) => (
                              <div key={idx} className="cpt-takeaway-item">
                                <span className="cpt-takeaway-bullet"><span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'currentColor', verticalAlign: 'middle' }} /></span>
                                <div className="cpt-takeaway-text">
                                  <strong>{t.label}:</strong> {t.detail}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Timeline Chapters */}
                        <div className="cpt-summary-card__section">
                          <div className="cpt-sec-heading">
                            <span><Clock size={16} /></span>
                            <span>Timestamped Narrative Breakdown</span>
                          </div>
                          <div className="cpt-timeline-list">
                            {activeSession.summary.chapters.map((c, idx) => (
                              <div key={idx} className="cpt-timeline-item">
                                <span className="cpt-timeline-pill">{c.time}</span>
                                <div className="cpt-timeline-content">
                                  <div className="cpt-timeline-title">{c.title}</div>
                                  <div className="cpt-timeline-desc">{c.desc}</div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Dynamics & Sentiment */}
                        {activeSession.summary.dynamics && (
                          <div className="cpt-summary-card__section">
                            <div className="cpt-sec-heading">
                              <span><Users size={16} /></span>
                              <span>Discussion Dynamics & Sentiment</span>
                            </div>
                            <div className="cpt-dynamics-grid">
                              <div className="cpt-dynamic-card">
                                <div className="cpt-dynamic-label">Discussion Tone</div>
                                <div className="cpt-dynamic-val">{activeSession.summary.dynamics.tone}</div>
                              </div>
                              <div className="cpt-dynamic-card">
                                <div className="cpt-dynamic-label">Audience Engagement</div>
                                <div className="cpt-dynamic-val">{activeSession.summary.dynamics.engagement}</div>
                              </div>
                              <div className="cpt-dynamic-card">
                                <div className="cpt-dynamic-label">Participants</div>
                                <div className="cpt-dynamic-val">{activeSession.summary.dynamics.speakers}</div>
                              </div>
                              <div className="cpt-dynamic-card">
                                <div className="cpt-dynamic-label">Sentiment Profile</div>
                                <div className="cpt-dynamic-val">{activeSession.summary.dynamics.sentiment}</div>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Action Items */}
                        <div className="cpt-summary-card__section">
                          <div className="cpt-sec-heading">
                            <span><Pin size={16} /></span>
                            <span>Recommended Action Items</span>
                          </div>
                          <div className="cpt-actions-list">
                            {activeSession.summary.actionItems.map((item, idx) => (
                              <div key={idx} className="cpt-action-item">
                                <span className="cpt-action-num">{idx + 1}</span>
                                <span>{item}</span>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Action Bar */}
                        <div className="cpt-summary-actions">
                          <div className="cpt-action-btn-group">
                            <button
                              className="cpt-tool-btn"
                              onClick={() => handleCopySummary(activeSession.summary)}
                            >
                              <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>{copied ? <Check size={14} /> : <Copy size={14} />} {copied ? 'Copied!' : 'Copy Summary'}</span>
                            </button>
                            <button
                              className="cpt-tool-btn"
                              onClick={() => {
                                handleSend();
                              }}
                            >
                              <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><RefreshCcw size={14} /> Regenerate</span>
                            </button>
                          </div>
                        </div>

                      </div>
                    </div>
                  </div>
                )}

                {/* Additional Follow-Up Q&A Messages */}
                {activeSession.messages && activeSession.messages.slice(2).map((msg, index) => (
                  <div
                    key={index}
                    className={`cpt-msg-row ${msg.sender === 'user' ? 'cpt-msg-row--user' : 'cpt-msg-row--assistant'}`}
                  >
                    {msg.sender === 'user' ? (
                      <div className="cpt-user-bubble">
                        {msg.attachment && (
                          <div className="cpt-user-attachment">
                            <span><Play size={12} fill="currentColor" /></span>
                            <span>{msg.attachment}</span>
                          </div>
                        )}
                        <div className="cpt-user-text">{msg.text}</div>
                      </div>
                    ) : (
                      <>
                        <div className="cpt-ai-avatar"><Sparkles size={18} /></div>
                        <div className="cpt-ai-body">
                          <div className="cpt-followup-text">
                            {msg.text}
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                ))}

                <div ref={messagesEndRef} />
              </div>
            )}

          </div>
        </div>

        {/* ── Bottom Input Area (ChatGPT Style) ── */}
        <div className="cpt-input-area">
          <div className="cpt-input-wrapper">
            
            {attachedFile && (
              <div className="cpt-file-chip">
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Film size={14} /> {attachedFile.name}</span>
                <button
                  className="cpt-file-chip__remove"
                  onClick={() => setAttachedFile(null)}
                >
                  <X size={12} />
                </button>
              </div>
            )}

            <div className="cpt-input-pill">
              <input
                ref={fileInputRef}
                type="file"
                className="sr-only"
                accept=".mp4,.mov,.avi,.webm,.mkv,.mp3,.wav"
                onChange={(e) => {
                  const f = e.target.files[0];
                  if (f) setAttachedFile(f);
                }}
              />

              <button
                className="cpt-attach-btn"
                onClick={() => fileInputRef.current?.click()}
                title="Attach video or audio file"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>

              <textarea
                className="cpt-textarea"
                placeholder={
                  activeSession?.summary
                    ? "Ask a follow-up question about this summary (e.g. 'What was said about marketing?')..."
                    : "Paste a video URL or describe the video to summarize..."
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

              <button
                className={`cpt-send-btn ${(promptText.trim() || attachedFile) && !isGenerating ? 'active' : ''}`}
                disabled={(!promptText.trim() && !attachedFile) || isGenerating}
                onClick={handleSend}
                title="Send"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <path d="M12 19V5M5 12l7-7 7 7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
            </div>

            <div className="cpt-disclaimer">
              Univance AI analyzes full multimodal timelines. Verify important dates and figures.
            </div>

          </div>
        </div>

      </main>

    </div>
  );
}
