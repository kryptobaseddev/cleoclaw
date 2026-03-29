"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-xl text-sm font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--accent)] focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary:
          "bg-gradient-to-r from-[#2fd9f4] to-[#06b6d4] text-white shadow-sm hover:shadow-glow",
        secondary:
          "border border-[color:var(--border)] bg-[color:var(--surface)] text-strong hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]",
        outline:
          "border border-[color:var(--border-strong)] bg-transparent text-strong hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]",
        ghost:
          "bg-transparent text-strong hover:bg-[color:var(--surface-strong)]",
        danger:
          "bg-app-danger-soft text-app-danger hover:bg-[rgba(255,180,171,0.2)]",
        gold:
          "bg-gradient-to-r from-[#e9c349] to-[#d4af37] text-[#00363e] shadow-sm",
      },
      size: {
        sm: "h-9 px-4",
        md: "h-11 px-5",
        lg: "h-12 px-6 text-base",
        icon: "h-9 w-9 p-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

export interface ButtonProps
  extends
    React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export { Button, buttonVariants };
