import type { HTMLAttributes } from "react";

import { cn } from "../../lib/utils";

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: "teal" | "slate" | "amber" | "green";
};

const tones = {
  teal: "bg-teal-50 text-teal-800 ring-teal-700/10",
  slate: "bg-slate-100 text-slate-700 ring-slate-600/10",
  amber: "bg-amber-50 text-amber-800 ring-amber-700/10",
  green: "bg-emerald-50 text-emerald-800 ring-emerald-700/10",
};

export function Badge({ className, tone = "teal", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}
