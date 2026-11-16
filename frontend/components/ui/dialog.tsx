"use client";

import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

import { Button } from "./button";

type DialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
};

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      aria-describedby={description ? "dialog-description" : undefined}
      aria-labelledby="dialog-title"
      className="w-[calc(100%-2rem)] max-w-lg rounded-2xl border border-border bg-white p-0 text-foreground shadow-soft backdrop:bg-slate-950/40"
      onClose={() => onOpenChange(false)}
      onClick={(event) => {
        if (event.target === event.currentTarget) onOpenChange(false);
      }}
      ref={dialogRef}
    >
      <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-5 sm:px-6">
        <div>
          <h2 className="text-lg font-semibold" id="dialog-title">
            {title}
          </h2>
          {description ? (
            <p className="mt-1 text-sm leading-6 text-muted-foreground" id="dialog-description">
              {description}
            </p>
          ) : null}
        </div>
        <Button
          aria-label="Cerrar diálogo"
          className="-mr-2 -mt-2 shrink-0"
          onClick={() => onOpenChange(false)}
          size="icon"
          variant="ghost"
        >
          <X aria-hidden="true" size={18} />
        </Button>
      </div>
      <div className="p-5 sm:p-6">{children}</div>
    </dialog>
  );
}
