import * as React from "react";

import { cn } from "@/lib/utils";

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "min-h-[120px] w-full rounded-lg border-b border-app-border border-t-0 border-l-0 border-r-0 bg-app-surface-muted px-4 py-3 text-sm text-app-text placeholder:text-app-text-quiet focus-visible:outline-none focus-visible:border-b-app-accent focus-visible:shadow-[0_1px_0_0_var(--accent)]",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";

export { Textarea };
