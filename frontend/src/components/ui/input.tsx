import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, type, ...props }, ref) => (
  <input
    ref={ref}
    type={type}
    className={cn(
      "flex h-11 w-full rounded-lg border-b border-app-border border-t-0 border-l-0 border-r-0 bg-app-surface-muted px-4 text-sm text-app-text placeholder:text-app-text-quiet focus-visible:outline-none focus-visible:border-b-app-accent focus-visible:shadow-[0_1px_0_0_var(--accent)]",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";

export { Input };
