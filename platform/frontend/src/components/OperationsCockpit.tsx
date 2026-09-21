import type { SystemStatus } from "@/lib/status";
import { ServiceStatusCard } from "./ServiceStatusCard";

const queues = [
  ["Approval ready", "0"],
  ["Manual actions", "0"],
  ["Follow-ups due", "0"],
  ["Uncertain", "0"],
] as const;

export function OperationsCockpit({ status }: { status: SystemStatus }) {
  return (
    <main className="cockpit">
      <header className="cockpit__header">
        <div>
          <p className="eyebrow">JOB CONTROL / PRIVATE</p>
          <h1>Operations cockpit</h1>
          <p className="lede">
            Foundation services and queues from one secure view.
          </p>
        </div>
        <div className="live-badge">
          <span />
          Private link active
        </div>
      </header>

      <section aria-label="Workflow queues" className="queue-grid">
        {queues.map(([label, value]) => (
          <article className="queue-card" key={label}>
            <strong>{value}</strong>
            <span>{label}</span>
          </article>
        ))}
      </section>

      <section className="panel" aria-labelledby="service-health-title">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">SYSTEM</p>
            <h2 id="service-health-title">Service health</h2>
          </div>
          <time dateTime={status.generated_at}>
            {new Date(status.generated_at).toLocaleString("en-US", {
              timeZone: "America/Sao_Paulo",
            })}
          </time>
        </div>
        <div className="service-grid">
          {status.services.map((service) => (
            <ServiceStatusCard key={service.name} service={service} />
          ))}
        </div>
      </section>

      <nav className="mobile-actions" aria-label="Primary">
        <a href="#inbox">Inbox</a>
        <a href="#jobs">Jobs</a>
        <a href="#runs">Runs</a>
      </nav>
    </main>
  );
}
