import type { SiteConfig } from '../../lib/types.js';

export function SiteToggle(props: {
  site: SiteConfig;
  enabled: boolean;
  onChange: (enabled: boolean) => void;
}): JSX.Element {
  const { site, enabled, onChange } = props;
  return (
    <div className="site-row" role="group" aria-labelledby={`site-${site.id}`}>
      <span id={`site-${site.id}`} className="name">
        {site.label}
      </span>
      <button
        className="toggle"
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label={`Toggle ${site.label}`}
        onClick={() => onChange(!enabled)}
      >
        <span className="knob" aria-hidden="true" />
      </button>
    </div>
  );
}
