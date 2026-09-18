import React, { useEffect, useRef } from 'react';
import './RadarBackground.css';

export default function RadarBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    let animationFrameId;

    let width = window.innerWidth;
    let height = window.innerHeight;

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width;
      canvas.height = height;
    };

    window.addEventListener('resize', resize);
    resize();

    // Radar properties
    let angle = 0;
    const radarSpeed = 0.02;

    // Generate random "blips" (threats/nodes)
    const blips = Array.from({ length: 15 }, () => ({
      x: (Math.random() - 0.5) * 2, // Normalized coordinates (-1 to 1)
      y: (Math.random() - 0.5) * 2,
      opacity: 0,
      size: Math.random() * 3 + 2,
    }));

    const animate = () => {
      // Clear with slight opacity to create motion trails (though we don't need it for radar, 
      // we'll just clear completely and redraw)
      ctx.clearRect(0, 0, width, height);

      const centerX = width / 2;
      const centerY = height / 2;
      const radius = Math.min(width, height) * 0.8;

      // Draw faint background grid circles
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
      ctx.lineWidth = 1;
      for (let i = 1; i <= 4; i++) {
        ctx.beginPath();
        ctx.arc(centerX, centerY, (radius / 4) * i, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Draw crosshairs
      ctx.beginPath();
      ctx.moveTo(centerX - radius, centerY);
      ctx.lineTo(centerX + radius, centerY);
      ctx.moveTo(centerX, centerY - radius);
      ctx.lineTo(centerX, centerY + radius);
      ctx.stroke();

      // Update and draw radar sweep (conical gradient effect)
      angle += radarSpeed;
      if (angle >= Math.PI * 2) angle = 0;

      // We simulate a conical gradient by drawing a sweeping arc
      ctx.save();
      ctx.translate(centerX, centerY);
      ctx.rotate(angle);
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, radius, 0, -Math.PI / 4, true); // Sweep angle
      ctx.lineTo(0, 0);
      
      const sweepGradient = ctx.createLinearGradient(0, 0, 0, -radius);
      sweepGradient.addColorStop(0, 'rgba(255, 255, 255, 0.0)');
      sweepGradient.addColorStop(1, 'rgba(255, 255, 255, 0.1)');
      
      ctx.fillStyle = sweepGradient;
      ctx.fill();

      // Draw the solid sweep line
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(radius, 0);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.restore();

      // Update and draw blips
      blips.forEach(blip => {
        const blipX = centerX + blip.x * radius;
        const blipY = centerY + blip.y * radius;
        
        // Calculate angle of blip relative to center
        let blipAngle = Math.atan2(blipY - centerY, blipX - centerX);
        if (blipAngle < 0) blipAngle += Math.PI * 2;

        // If the radar sweep just passed over it, flash it!
        // We use a small threshold to detect passing
        let diff = angle - blipAngle;
        if (diff < 0) diff += Math.PI * 2;

        if (diff < 0.2) {
          blip.opacity = 1; // Full brightness when hit
        } else {
          blip.opacity *= 0.98; // Slowly fade out
        }

        if (blip.opacity > 0.01) {
          ctx.beginPath();
          ctx.arc(blipX, blipY, blip.size, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(255, 255, 255, ${blip.opacity})`;
          ctx.fill();
          
          // Outer glow for blip
          ctx.beginPath();
          ctx.arc(blipX, blipY, blip.size * 2.5, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(255, 255, 255, ${blip.opacity * 0.5})`;
          ctx.stroke();
        }
      });

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="radar-background-container">
      <canvas ref={canvasRef} className="radar-canvas" />
      <div className="radar-vignette"></div>
    </div>
  );
}
