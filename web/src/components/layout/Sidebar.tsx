import { useState } from 'react';

export function Sidebar() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed right-0 top-1/2 -translate-y-1/2 z-40 bg-mine-blue text-white px-2 py-4 rounded-l-lg shadow-lg hover:bg-blue-800 transition-colors"
        title="Configuración"
      >
        ⚙
      </button>

      {/* Sidebar panel */}
      {isOpen && (
        <div className="fixed right-0 top-0 h-full w-80 bg-white shadow-2xl z-50 overflow-y-auto">
          <div className="flex items-center justify-between p-4 border-b">
            <h2 className="font-bold text-gray-900">Configuración</h2>
            <button
              onClick={() => setIsOpen(false)}
              className="text-gray-400 hover:text-gray-600 text-xl"
            >
              ✕
            </button>
          </div>
          <div className="p-4">
            <p className="text-sm text-gray-500">
              Los ajustes de tolerancia y detección se configurarán aquí.
              Disponible tras conectar con la API.
            </p>
          </div>
        </div>
      )}

      {/* Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-40"
          onClick={() => setIsOpen(false)}
        />
      )}
    </>
  );
}
