import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import './VoidBackground.css';

export default function VoidBackground() {
  const mountRef = useRef(null);

  useEffect(() => {
    // 1. Scene Setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000); // True pitch black
    // Very faint fog so the edges of the disk fade into the void
    scene.fog = new THREE.FogExp2(0x000000, 0.0008); 

    const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 1, 4000);
    // Position camera to look at the accretion disk from a slight angle
    camera.position.z = 800;
    camera.position.y = 300;
    camera.lookAt(scene.position);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(window.innerWidth, window.innerHeight);

    if (mountRef.current.children.length === 0) {
      mountRef.current.appendChild(renderer.domElement);
    }

    // 2. Accretion Disk (Particle Ring) Setup
    const particleCount = 12000;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const opacities = new Float32Array(particleCount);

    const innerRadius = 200;
    const outerRadius = 800;

    for (let i = 0; i < particleCount; i++) {
      // Random angle
      const theta = Math.random() * Math.PI * 2;
      // Bias distance towards the inner radius for a denser core, tapering off outwards
      const radius = innerRadius + Math.pow(Math.random(), 1.5) * (outerRadius - innerRadius);
      
      // Calculate position
      const x = Math.cos(theta) * radius;
      const z = Math.sin(theta) * radius;
      // Slight vertical noise for a 3D dust effect rather than a perfectly flat plane
      const y = (Math.random() - 0.5) * (30 + (radius - innerRadius) * 0.05);

      positions[i * 3] = x;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = z;

      // Random opacity for twinkling/dust variation
      opacities[i] = Math.random() * 0.5 + 0.1;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('opacity', new THREE.BufferAttribute(opacities, 1));

    // Custom shader for soft circular dots with individual opacities
    const material = new THREE.ShaderMaterial({
      uniforms: {
        color: { value: new THREE.Color(0xdddddd) } // Very light grey/white
      },
      vertexShader: `
        attribute float opacity;
        varying float vOpacity;
        void main() {
          vOpacity = opacity;
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = (120.0 / -mvPosition.z); // Scale by distance
          gl_Position = projectionMatrix * mvPosition;
        }
      `,
      fragmentShader: `
        uniform vec3 color;
        varying float vOpacity;
        void main() {
          float dist = length(gl_PointCoord - vec2(0.5, 0.5));
          if (dist > 0.5) discard;
          
          // Extremely soft edge
          float alpha = (1.0 - smoothstep(0.1, 0.5, dist)) * vOpacity;
          gl_FragColor = vec4(color, alpha);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending
    });

    const disk = new THREE.Points(geometry, material);
    // Tilt the disk slightly for a better visual angle
    disk.rotation.x = 0.2;
    scene.add(disk);

    // 3. Mouse Interaction (Subtle Parallax)
    let mouseX = 0;
    let mouseY = 0;
    const windowHalfX = window.innerWidth / 2;
    const windowHalfY = window.innerHeight / 2;

    const onDocumentMouseMove = (event) => {
      mouseX = (event.clientX - windowHalfX) * 0.1;
      mouseY = (event.clientY - windowHalfY) * 0.1;
    };
    
    window.addEventListener('mousemove', onDocumentMouseMove);

    const onWindowResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    };

    window.addEventListener('resize', onWindowResize);

    // 4. Animation Loop
    let animationFrameId;

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      render();
    };

    const render = () => {
      // Smoothly pan camera based on mouse for subtle parallax
      camera.position.x += (mouseX - camera.position.x) * 0.02;
      camera.position.y += (-mouseY + 300 - camera.position.y) * 0.02;
      camera.lookAt(scene.position);

      // Rotate the entire accretion disk very slowly
      disk.rotation.y -= 0.0005;

      renderer.render(scene, camera);
    };

    animate();

    return () => {
      window.removeEventListener('mousemove', onDocumentMouseMove);
      window.removeEventListener('resize', onWindowResize);
      cancelAnimationFrame(animationFrameId);
      
      if (mountRef.current && mountRef.current.contains(renderer.domElement)) {
        mountRef.current.removeChild(renderer.domElement);
      }
      
      geometry.dispose();
      material.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <div className="void-background-container">
      <div ref={mountRef} className="void-canvas-wrapper" />
      <div className="void-vignette"></div>
    </div>
  );
}
