import React, { useEffect, useRef } from 'react';
import './SpotlightBackground.css';

export default function SpotlightBackground() {
  const containerRef = useRef(null);

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!containerRef.current) return;
      // Get mouse position relative to viewport
      const x = e.clientX;
      const y = e.clientY;
      
      // Update CSS variables for the spotlight position
      containerRef.current.style.setProperty('--mouse-x', `${x}px`);
      containerRef.current.style.setProperty('--mouse-y', `${y}px`);
    };

    window.addEventListener('mousemove', handleMouseMove);
    
    // Initial center position
    if (containerRef.current) {
      containerRef.current.style.setProperty('--mouse-x', `${window.innerWidth / 2}px`);
      containerRef.current.style.setProperty('--mouse-y', `${window.innerHeight / 2}px`);
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
    };
  }, []);

  return (
    <div ref={containerRef} className="spotlight-bg-container">
      {/* The base layer is pure black */}
      <div className="spotlight-bg-base"></div>
      
      {/* The grid layer, only visible where the spotlight shines */}
      <div className="spotlight-grid"></div>
    </div>
  );
}
