import { cn } from "@/lib/utils";

type StatusDotVariant = "agent" | "approval" | "task";

const AGENT_STATUS_DOT_CLASS_BY_STATUS: Record<string, string> = {
  online: "bg-app-success shadow-[0_0_8px_rgba(63,185,80,0.5)] animate-pulse",
  busy: "bg-app-warning shadow-[0_0_8px_rgba(233,195,73,0.5)]",
  provisioning: "bg-app-warning shadow-[0_0_8px_rgba(233,195,73,0.5)]",
  updating: "bg-app-accent shadow-[0_0_8px_rgba(47,217,244,0.5)]",
  deleting: "bg-app-danger",
  offline: "bg-app-text-quiet",
};

const APPROVAL_STATUS_DOT_CLASS_BY_STATUS: Record<string, string> = {
  approved: "bg-app-success",
  rejected: "bg-app-danger",
  pending: "bg-app-warning",
};

const TASK_STATUS_DOT_CLASS_BY_STATUS: Record<string, string> = {
  inbox: "bg-app-text-quiet",
  in_progress: "bg-app-warning",
  review: "bg-app-accent",
  done: "bg-app-success",
};

const STATUS_DOT_CLASS_BY_VARIANT: Record<
  StatusDotVariant,
  Record<string, string>
> = {
  agent: AGENT_STATUS_DOT_CLASS_BY_STATUS,
  approval: APPROVAL_STATUS_DOT_CLASS_BY_STATUS,
  task: TASK_STATUS_DOT_CLASS_BY_STATUS,
};

const DEFAULT_STATUS_DOT_CLASS: Record<StatusDotVariant, string> = {
  agent: "bg-app-text-quiet",
  approval: "bg-app-warning",
  task: "bg-app-text-quiet",
};

export const statusDotClass = (
  status: string | null | undefined,
  variant: StatusDotVariant = "agent",
) => {
  const normalized = (status ?? "").trim().toLowerCase();
  if (!normalized) {
    return DEFAULT_STATUS_DOT_CLASS[variant];
  }
  return (
    STATUS_DOT_CLASS_BY_VARIANT[variant][normalized] ??
    DEFAULT_STATUS_DOT_CLASS[variant]
  );
};

type StatusDotProps = {
  status?: string | null;
  variant?: StatusDotVariant;
  className?: string;
};

export function StatusDot({
  status,
  variant = "agent",
  className,
}: StatusDotProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-block h-2.5 w-2.5 rounded-full",
        statusDotClass(status, variant),
        className,
      )}
    />
  );
}
