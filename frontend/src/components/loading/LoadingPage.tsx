import {BoltLoader} from '../common/BoltLoader';
import background from '../../assets/images/electrical-loading.jpg';
import './LoadingPage.css';

type LoadingPageProps = {
  error?: string;
  apiBase?: string;
  onRetry?: () => void;
};

export function LoadingPage({error, apiBase, onRetry}: LoadingPageProps) {
  return (
    <main className="startup-page" style={{backgroundImage: `url("${background}")`}}>
      <div className="startup-shade" aria-hidden="true" />
      <header className="startup-brand">
        <BoltLoader animated={false} />
        <span>PANEL<span className="startup-brand-light">STUDIO</span></span>
        <span className="startup-brand-divider" />
        <span className="startup-brand-description">Electrical panel engineering</span>
      </header>

      <section className="startup-content" aria-labelledby="startup-title">
        <span className="startup-eyebrow">FROM ELECTRICAL INTENT TO ENGINEERED DESIGN</span>
        <h1 id="startup-title">Power your<br /><span>next design.</span></h1>
        <p className="startup-description">One workspace for your requirements, schematics and panel assemblies.</p>

        <div className={`startup-connection ${error ? 'startup-connection--error' : ''}`}>
          <BoltLoader className="startup-bolt" animated={!error} />
          {error ? (
            <div>
              <h2>Could not reach the design API</h2>
              <p role="alert">{error} Start the required service or apply migrations, then retry.</p>
              {apiBase && <p className="startup-api">Configured API: <code>{apiBase}</code></p>}
              <button type="button" onClick={onRetry}>Retry connection <span aria-hidden="true">↗</span></button>
            </div>
          ) : (
            <div role="status" aria-live="polite">
              <h2>Preparing your workspace</h2>
              <p>Connecting to the design API and checking database readiness…</p>
            </div>
          )}
        </div>
      </section>

      <footer className="startup-footer">
        <span>DESIGN CONNECTED.</span>
        <span>Requirements <i /> Schematic <i /> 2D &amp; 3D <i /> Engineering</span>
      </footer>
      {!error && <div
        className="startup-progress"
        role="progressbar"
        aria-label="Workspace startup"
        aria-valuetext="Preparing your workspace and waiting for the design API"
      ><span /></div>}
    </main>
  );
}
