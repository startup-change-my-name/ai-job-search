export type ServiceState = "healthy" | "degraded" | "unavailable";

export interface ServiceStatus {
  name: string;
  state: ServiceState;
  checked_at: string;
  detail?: string | null;
}

export interface SystemStatus {
  generated_at: string;
  services: ServiceStatus[];
}
