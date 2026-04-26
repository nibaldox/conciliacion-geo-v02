export function Header() {
  return (
    <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-mine-blue text-white font-bold text-lg">
          CG
        </div>
        <div>
          <h1 className="text-lg font-bold text-gray-900">
            Conciliación Geotécnica
          </h1>
          <p className="text-xs text-gray-500">
            Diseño vs As-Built
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs text-gray-400">v2.0</span>
      </div>
    </header>
  );
}
