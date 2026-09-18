import React, { useEffect, useRef } from 'react';
import './DataGridBackground.css';

export default function DataGridBackground() {
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

    const gridSize = 40;
    let time = 0;
    
    // Data trails travelling along the grid
    const trails = Array.from({ length: 15 }, () => ({
      x: Math.floor(Math.random() * (width / gridSize)) * gridSize,
      y: Math.floor(Math.random() * (height / gridSize)) * gridSize,
      length: Math.random() * 200 + 50,
      speed: (Math.random() * 2 + 1) * (Math.random() > 0.5 ? 1 : -1),
      direction: Math.random() > 0.5 ? 'h' : 'v', // horizontal or vertical
      color: `hsla(${Math.random() * 40 + 180}, 100%, 70%, 0.8)`, // Cyan-blue range
      headPos: 0
    }));

    const animate = () => {
      ctx.fillStyle = 'rgba(5, 5, 5, 0.2)'; // Fading trail effect
      ctx.fillRect(0, 0, width, height);

      time += 0.05;

      // Draw subtle grid dots
      ctx.fillStyle = 'rgba(255, 255, 255, 0.05)';
      for (let x = 0; x < width; x += gridSize) {
        for (let y = 0; y < height; y += gridSize) {
          ctx.beginPath();
          ctx.arc(x, y, 1, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Draw moving data trails
      trails.forEach((trail) => {
        trail.headPos += trail.speed;
        
        const headX = trail.direction === 'h' ? trail.x + trail.headPos : trail.x;
        const headY = trail.direction === 'v' ? trail.y + trail.headPos : trail.y;

        // Reset trail if it goes off screen
        if (headX > width || headX < 0 || headY > height || headY < 0) {
          trail.x = Math.floor(Math.random() * (width / gridSize)) * gridSize;
          trail.y = Math.floor(Math.random() * (height / gridSize)) * gridSize;
          trail.headPos = 0;
          trail.direction = Math.random() > 0.5 ? 'h' : 'v';
          trail.speed = (Math.random() * 3 + 1) * (Math.random() > 0.5 ? 1 : -1);
        }

        // Draw the trail
        const gradient = ctx.createLinearGradient(
          trail.direction === 'h' ? headX - (trail.speed > 0 ? trail.length : -trail.length) : headX,
          trail.direction === 'v' ? headY - (trail.speed > 0 ? trail.length : -trail.length) : headY,
          headX,
          headY
        );

        gradient.addColorStop(0, 'rgba(0, 0, 0, 0)');
        gradient.addColorStop(1, trail.color);

        ctx.strokeStyle = gradient;
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
        ctx.beginPath();
        
        if (trail.direction === 'h') {
          ctx.moveTo(headX - (trail.speed > 0 ? trail.length : -trail.length), headY);
          ctx.lineTo(headX, headY);
        } else {
          ctx.moveTo(headX, headY - (trail.speed > 0 ? trail.length : -trail.length));
          ctx.lineTo(headX, headY);
        }
        
        ctx.stroke();

        // Draw a bright spark at the head
        ctx.fillStyle = '#ffffff';
        ctx.shadowBlur = 10;
        ctx.shadowColor = trail.color;
        ctx.beginPath();
        ctx.arc(headX, headY, 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0; // Reset
      });
      
      // Draw random glowing numbers/hex codes on grid intersections occasionally
      if (Math.random() > 0.3) {
        const charX = Math.floor(Math.random() * (width / gridSize)) * gridSize;
        const charY = Math.floor(Math.random() * (height / gridSize)) * gridSize;
        ctx.fillStyle = `rgba(0, 240, 255, ${Math.random() * 0.5})`;
        ctx.font = '10px monospace';
        const hex = Math.floor(Math.random() * 255).toString(16).toUpperCase().padStart(2, '0');
        ctx.fillText(hex, charX + 5, charY - 5);
      }

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="datagrid-container">
      <canvas ref={canvasRef} className="datagrid-canvas" />
      <div className="datagrid-scanner-overlay"></div>
    </div>
  );
}
