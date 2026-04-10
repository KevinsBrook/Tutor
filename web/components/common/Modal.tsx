"use client";

import { useEffect, useCallback } from "react";
import { X } from "lucide-react";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  titleIcon?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: "sm" | "md" | "lg" | "xl";
  closeOnBackdrop?: boolean;
  closeOnEscape?: boolean;
}

const widthClasses = {
  sm: "w-[440px]",
  md: "w-[560px]",
  lg: "w-[720px]",
  xl: "w-[920px]",
};

/**
 * Shared Modal base component
 */
export default function Modal({
  isOpen,
  onClose,
  title,
  titleIcon,
  children,
  footer,
  width = "md",
  closeOnBackdrop = true,
  closeOnEscape = true,
}: ModalProps) {
  // Handle escape key
  const handleEscape = useCallback(
    (e: KeyboardEvent) => {
      if (closeOnEscape && e.key === "Escape") {
        onClose();
      }
    },
    [closeOnEscape, onClose],
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
      // Prevent body scroll when modal is open
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = "";
    };
  }, [isOpen, handleEscape]);

  if (!isOpen) return null;

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (closeOnBackdrop && e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-4 backdrop-blur-md animate-in fade-in"
      onClick={handleBackdropClick}
    >
      <div
        className={`max-h-[90vh] ${widthClasses[width]} flex flex-col overflow-hidden rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/95 shadow-[0_24px_80px_rgba(2,6,23,0.28)] animate-in zoom-in-95 dark:border-slate-700/70 dark:bg-slate-900/90`}
      >
        {/* Header */}
        {(title || titleIcon) && (
          <div className="shrink-0 border-b border-slate-200/60 bg-white/70 p-4 dark:border-slate-700 dark:bg-slate-900/70">
            <div className="flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-900 dark:text-slate-100">
              {titleIcon}
              {title}
              </h3>
              <button
                onClick={onClose}
                className="rounded-xl border border-slate-200/80 bg-white p-1.5 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700"
              >
                <X className="h-5 w-5 text-slate-500 dark:text-slate-300" />
              </button>
            </div>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="shrink-0 border-t border-slate-200/60 bg-white/70 p-4 dark:border-slate-700 dark:bg-slate-900/70">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
