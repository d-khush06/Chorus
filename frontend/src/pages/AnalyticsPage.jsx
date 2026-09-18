/**
 * AnalyticsPage.jsx
 * Enterprise Multimodal Video Intelligence Platform
 * Houses the fully dark ChatGPTGeneralView for General & Cyber Modes.
 */
import React from 'react';
import ChatGPTGeneralView from '../components/analytics/ChatGPTGeneralView.jsx';

export default function AnalyticsPage({ onBack }) {
  return <ChatGPTGeneralView onGoToEvidence={onBack} />;
}
