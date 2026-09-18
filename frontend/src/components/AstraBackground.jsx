import React, { useEffect, useRef } from 'react';
import './AstraBackground.css';

export default function AstraBackground() {
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

    // Mouse tracking for interactive fluid
    let mouse = { x: width / 2, y: height / 2, tx: width / 2, ty: height / 2 };
    const onMouseMove = (e) => {
      mouse.tx = e.clientX;
      mouse.ty = e.clientY;
    };
    window.addEventListener('mousemove', onMouseMove);

    // Orb definitions
    // Colors inspired by futuristic AI (Cyan, Magenta, Deep Violet, Electric Blue)
    const orbs = [
      { color: 'rgba(0, 240, 255, 0.8)', radius: 400, x: 0, y: 0, vx: 0, vy: 0, speed: 0.001, angle: 0, distance: 200 },
      { color: 'rgba(162, 0, 255, 0.8)', radius: 500, x: 0, y: 0, vx: 0, vy: 0, speed: 0.0015, angle: Math.PI * 0.5, distance: 250 },
      { color: 'rgba(255, 0, 128, 0.7)', radius: 350, x: 0, y: 0, vx: 0, vy: 0, speed: 0.002, angle: Math.PI, distance: 180 },
      { color: 'rgba(0, 100, 255, 0.9)', radius: 450, x: 0, y: 0, vx: 0, vy: 0, speed: 0.0012, angle: Math.PI * 1.5, distance: 220 }
    ];

    let time = 0;

    const animate = () => {
      time += 1;
      
      // Smoothly interpolate mouse position (easing)
      mouse.x += (mouse.tx - mouse.x) * 0.02;
      mouse.y += (mouse.ty - mouse.y) * 0.02;

      ctx.clearRect(0, 0, width, height);

      // We use global composite operation for interesting blending
      ctx.globalCompositeOperation = 'screen';

      orbs.forEach((orb, i) => {
        orb.angle += orb.speed;
        
        // Base orbit
        let targetX = (width / 2) + Math.cos(orb.angle) * orb.distance;
        let targetY = (height / 2) + Math.sin(orb.angle) * orb.distance;

        // Add some complex wave motion (Lissajous curves)
        targetX += Math.sin(time * 0.005 + i) * 150;
        targetY += Math.cos(time * 0.004 + i) * 150;

        // Slight pull towards mouse to make it interactive
        const dx = mouse.x - targetX;
        const dy = mouse.y - targetY;
        targetX += dx * 0.15;
        targetY += dy * 0.15;

        // Smooth physics interpolation for the actual position
        orb.x += (targetX - orb.x) * 0.05;
        orb.y += (targetY - orb.y) * 0.05;

        // Draw radial gradient
        const gradient = ctx.createRadialGradient(orb.x, orb.y, 0, orb.x, orb.y, orb.radius);
        gradient.addColorStop(0, orb.color);
        gradient.addColorStop(1, 'rgba(0,0,0,0)');

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(orb.x, orb.y, orb.radius, 0, Math.PI * 2);
        ctx.fill();
      });

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', onMouseMove);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="astra-container">
      <div className="astra-noise-overlay"></div>
      <canvas ref={canvasRef} className="astra-canvas" />
      {/* Central glowing AI core visual */}
      <div className="astra-core-container">
          <div className="astra-core"></div>
      </div>
    </div>
  );
}
