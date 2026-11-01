import './BoltLoader.css';

/** A code-native lightning mark shared by startup and engineering operations. */
export function BoltLoader({className = '', animated = true}: {className?: string; animated?: boolean}) {
  const outline = 'M30 2 7 28h14l-6 24 28-32H28Z';
  return (
    <span className={`bolt-loader ${animated ? 'bolt-loader--animated' : ''} ${className}`} aria-hidden="true">
      <svg viewBox="0 0 50 54" fill="none" focusable="false">
        <path className="bolt-loader__outline" d={outline} strokeLinejoin="miter" />
        <path className="bolt-loader__charge" d={outline} />
        <path className="bolt-loader__spark" d={outline} pathLength="100" />
      </svg>
    </span>
  );
}
