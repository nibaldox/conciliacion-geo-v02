import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Canvas } from '@react-three/fiber';
import { BlastHolesLayer, type BlastHole3D } from '../../src/components/mesh/BlastHolesLayer';

declare global {
  interface Window {
    __gl?: WebGLRenderingContext | WebGL2RenderingContext;
    __setColors?: (first: string, second: string) => void;
    __setSelected?: (key: string | null) => void;
    __ready?: boolean;
  }
}

function Harness() {
  const [first, setFirst] = useState('#ff0000');
  const [second, setSecond] = useState('#00ff00');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  window.__setColors = (a: string, b: string) => {
    setFirst(a);
    setSecond(b);
  };
  window.__setSelected = (key: string | null) => setSelectedKey(key);
  const neutralHoles: BlastHole3D[] = [{ key: 'neutral', collar: [0, 0, 2], color: '#ff0000' }];
  const holes: BlastHole3D[] = [
    { key: 'red', collar: [-2, 0, 0], color: first },
    { key: 'green', collar: [2, 0, 0], color: second },
  ];
  return (
    <Canvas
      orthographic
      camera={{ position: [0, 0, 10], zoom: 40, near: 0.1, far: 100 }}
      gl={{ preserveDrawingBuffer: true, antialias: false }}
      style={{ width: 400, height: 400 }}
      onCreated={({ gl }) => {
        window.__gl = gl.getContext() as WebGL2RenderingContext;
        window.__ready = true;
      }}
    >
      <BlastHolesLayer holes={holes} center={[0, 0, 0]} collarRadius={0.9} selectedKey={selectedKey} />
      <BlastHolesLayer holes={neutralHoles} center={[0, 0, 0]} collarRadius={0.9} colorCollars={false} />
    </Canvas>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Harness />
  </StrictMode>,
);
