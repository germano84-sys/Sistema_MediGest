"use client";

import { CheckCircle2, CircleAlert, X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { Button } from "./button";

type ToastMessage = {
  id: number;
  title: string;
  description?: string;
  tone: "success" | "error";
};

type ToastContextValue = {
  toast: (message: Omit<ToastMessage, "id">) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ToastMessage[]>([]);

  const dismiss = useCallback((id: number) => {
    setMessages((current) => current.filter((message) => message.id !== id));
  }, []);

  const toast = useCallback(
    (message: Omit<ToastMessage, "id">) => {
      const id = Date.now() + Math.random();
      setMessages((current) => [...current, { ...message, id }]);
      window.setTimeout(() => dismiss(id), 5000);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-label="Notificaciones"
        aria-live="polite"
        className="fixed bottom-4 right-4 z-[70] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
        role="region"
      >
        {messages.map((message) => (
          <div
            className="flex items-start gap-3 rounded-xl border border-border bg-white p-4 shadow-soft"
            key={message.id}
            role={message.tone === "error" ? "alert" : "status"}
          >
            {message.tone === "success" ? (
              <CheckCircle2 aria-hidden="true" className="mt-0.5 shrink-0 text-emerald-700" size={18} />
            ) : (
              <CircleAlert aria-hidden="true" className="mt-0.5 shrink-0 text-red-700" size={18} />
            )}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">{message.title}</p>
              {message.description ? (
                <p className="mt-1 text-sm leading-5 text-muted-foreground">
                  {message.description}
                </p>
              ) : null}
            </div>
            <Button
              aria-label="Descartar notificación"
              onClick={() => dismiss(message.id)}
              size="icon"
              variant="ghost"
            >
              <X aria-hidden="true" size={16} />
            </Button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within ToastProvider");
  return context;
}
