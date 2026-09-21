import type { ServiceStatus } from "@/lib/status";

export function ServiceStatusCard({ service }: { service: ServiceStatus }) {
  const label = service.name.charAt(0).toUpperCase() + service.name.slice(1);

  return (
    <article className="service-card" data-state={service.state}>
      <div className="service-card__topline">
        <h3>{label}</h3>
        <span className="status-pill">{service.state}</span>
      </div>
      <p>{service.detail ?? "Responding normally"}</p>
      <time dateTime={service.checked_at}>
        Checked{" "}
        {new Date(service.checked_at).toLocaleTimeString("en-US", {
          timeZone: "America/Sao_Paulo",
        })}
      </time>
    </article>
  );
}
