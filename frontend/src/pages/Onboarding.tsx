import { useState } from 'react'
import { Fingerprint, LockKeyhole, Scale, ShieldCheck } from 'lucide-react'
import { useJobs } from '../jobs'
import type { Bootstrap } from '../types'

export function Onboarding({ bootstrap, onExplore }: { bootstrap: Bootstrap; onExplore: () => void }) {
  const { start, busy } = useJobs()
  const [garmin, setGarmin] = useState({ email: '', password: '' })
  const [renpho, setRenpho] = useState({ email: '', password: '' })
  return <main className="onboarding">
    <section className="onboarding__intro"><div className="brand brand--dark"><span className="brand__mark"><Fingerprint /></span><span>Garmin Health Sync</span></div><span className="eyebrow">Welcome to your private health cockpit</span><h1>Your data, connected locally.</h1><p>Bring Garmin, RENPHO and manual measurements into one calm view. The web interface stays on this device.</p><div className="privacy-points"><span><ShieldCheck />Loopback-only interface</span><span><LockKeyhole />Secrets stay in Keychain or encrypted storage</span><span><Scale />No analytics or cloud database</span></div></section>
    <section className="onboarding__setup"><div className="step-heading"><span>1</span><div><h2>Connect Garmin</h2><p>Required for training, recovery and blood pressure.</p></div></div>{bootstrap.sources.garmin.connected ? <Connected label={bootstrap.sources.garmin.detail} /> : <form onSubmit={(event) => { event.preventDefault(); void start('/auth/garmin/login', garmin) }}><label>Email<input type="email" value={garmin.email} onChange={(event) => setGarmin({ ...garmin, email: event.target.value })} autoComplete="username" required /></label><label>Password<input type="password" value={garmin.password} onChange={(event) => setGarmin({ ...garmin, password: event.target.value })} autoComplete="current-password" required /></label><button className="button button--primary" disabled={busy}>Connect Garmin</button><small>MFA will appear in the Activity Center when Garmin requests it.</small></form>}
      <div className="step-heading"><span>2</span><div><h2>Connect RENPHO</h2><p>Optional. Adds body composition and measurement history.</p></div></div>{bootstrap.sources.renpho.connected ? <Connected label={bootstrap.sources.renpho.detail} /> : <form onSubmit={(event) => { event.preventDefault(); void start('/auth/renpho/login', renpho) }}><label>Email<input type="email" value={renpho.email} onChange={(event) => setRenpho({ ...renpho, email: event.target.value })} autoComplete="username" required /></label><label>Password<input type="password" value={renpho.password} onChange={(event) => setRenpho({ ...renpho, password: event.target.value })} autoComplete="current-password" required /></label><button className="button" disabled={busy}>Connect RENPHO</button></form>}
      <button className="button button--quiet" onClick={onExplore}>Explore available data</button>
    </section>
  </main>
}

function Connected({ label }: { label: string }) { return <div className="connected-panel"><ShieldCheck /><div><b>Connected</b><small>{label}</small></div></div> }
