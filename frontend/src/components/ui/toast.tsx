import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

export type ToastVariant =
  | "default"
  | "success"
  | "warning"
  | "destructive"
  | "info";

export interface ToastOptions {
  /** Heading. Accepts a node so callers can embed interactive bits (e.g. a
   * clickable album name). */
  title?: ReactNode;
  /** Body. Accepts a node for the same reason as {@link title}. */
  description?: ReactNode;
  variant?: ToastVariant;
  /** Auto-dismiss after this many ms. `0` keeps the toast until dismissed. */
  duration?: number;
}

interface ToastItem extends ToastOptions {
  id: number;
  variant: ToastVariant;
}

type Listener = (toasts: ToastItem[]) => void;

const DEFAULT_DURATION = 6000;

let toasts: ToastItem[] = [];
const listeners = new Set<Listener>();
let counter = 0;

function emit() {
  for (const listener of listeners) listener(toasts);
}

function dismiss(id: number) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

function addToast(options: ToastOptions): number {
  const id = ++counter;
  const duration = options.duration ?? DEFAULT_DURATION;
  toasts = [...toasts, { id, variant: "default", ...options }];
  emit();
  if (duration > 0) {
    setTimeout(() => dismiss(id), duration);
  }
  return id;
}

type Helper = (options: Omit<ToastOptions, "variant">) => number;

/**
 * Module-level toast API. Calling `toast(...)` (or a variant helper) is safe
 * from anywhere — including after the calling component unmounts — because the
 * queue lives outside React. Render `<Toaster />` once near the app root.
 */
export const toast = Object.assign(
  (options: ToastOptions) => addToast(options),
  {
    success: ((o) => addToast({ ...o, variant: "success" })) as Helper,
    warning: ((o) => addToast({ ...o, variant: "warning" })) as Helper,
    error: ((o) => addToast({ ...o, variant: "destructive" })) as Helper,
    info: ((o) => addToast({ ...o, variant: "info" })) as Helper,
    dismiss,
  },
);

const variantStyles: Record<ToastVariant, string> = {
  default: "border bg-background text-foreground",
  success:
    "border-green-500/50 bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-300",
  warning:
    "border-yellow-500/50 bg-yellow-50 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300",
  destructive:
    "border-destructive/50 bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-300",
  info: "border-blue-500/50 bg-blue-50 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
};

const variantIcon: Record<ToastVariant, typeof Info | null> = {
  default: null,
  success: CheckCircle2,
  warning: AlertTriangle,
  destructive: XCircle,
  info: Info,
};

function ToastCard({ item }: { item: ToastItem }) {
  const Icon = variantIcon[item.variant];
  const assertive =
    item.variant === "destructive" || item.variant === "warning";
  return (
    <div
      role="status"
      aria-live={assertive ? "assertive" : "polite"}
      className={cn(
        "pointer-events-auto flex items-start gap-3 rounded-lg border p-4 shadow-lg",
        variantStyles[item.variant],
      )}
    >
      {Icon && <Icon className="h-5 w-5 shrink-0" />}
      <div className="flex-1 space-y-1">
        {item.title && (
          <p className="text-sm font-medium leading-none">{item.title}</p>
        )}
        {item.description && (
          <p className="text-sm leading-relaxed opacity-90">
            {item.description}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={() => dismiss(item.id)}
        aria-label="Dismiss notification"
        className="shrink-0 rounded-md opacity-60 transition-opacity hover:opacity-100"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

/**
 * Renders the live toast queue. Mount once near the app root.
 */
export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>(toasts);

  useEffect(() => {
    listeners.add(setItems);
    // Sync any toasts queued between render and effect.
    setItems(toasts);
    return () => {
      listeners.delete(setItems);
    };
  }, []);

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2"
      role="region"
      aria-label="Notifications"
    >
      {items.map((item) => (
        <ToastCard key={item.id} item={item} />
      ))}
    </div>,
    document.body,
  );
}
