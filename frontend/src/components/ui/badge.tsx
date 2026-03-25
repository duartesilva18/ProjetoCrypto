import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset transition-colors",
  {
    variants: {
      variant: {
        default: "bg-zinc-800 text-zinc-300 ring-zinc-700",
        success: "bg-emerald-950 text-emerald-400 ring-emerald-800",
        warning: "bg-amber-950 text-amber-400 ring-amber-800",
        danger: "bg-red-950 text-red-400 ring-red-800",
        info: "bg-blue-950 text-blue-400 ring-blue-800",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
