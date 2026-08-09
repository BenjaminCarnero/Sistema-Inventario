import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, XCircle, Info, AlertTriangle } from 'lucide-react';

type ToastType = 'success' | 'error' | 'info';
interface ToastItem { id: number; message: string; type: ToastType; }

interface ConfirmOptions {
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
}

interface UIContextValue {
  showToast: (message: string, type?: ToastType) => void;
  confirm: (options: ConfirmOptions | string) => Promise<boolean>;
}

const UIContext = createContext<UIContextValue | null>(null);

export function useUI() {
  const ctx = useContext(UIContext);
  if (!ctx) throw new Error('useUI must be used within UIProvider');
  return ctx;
}

const TOAST_STYLES: Record<ToastType, { icon: typeof CheckCircle2; classes: string }> = {
  success: { icon: CheckCircle2, classes: 'from-status-success to-[#059669]' },
  error: { icon: XCircle, classes: 'from-status-error to-[#B91C1C]' },
  info: { icon: Info, classes: 'from-brand to-accent' },
};

export function UIProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);
  const [confirmState, setConfirmState] = useState<(ConfirmOptions & { resolve: (v: boolean) => void }) | null>(null);

  const showToast = useCallback((message: string, type: ToastType = 'info') => {
    const id = ++idRef.current;
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500);
  }, []);

  const confirm = useCallback((options: ConfirmOptions | string) => {
    const opts = typeof options === 'string' ? { message: options } : options;
    return new Promise<boolean>((resolve) => {
      setConfirmState({ ...opts, resolve });
    });
  }, []);

  const resolveConfirm = (result: boolean) => {
    confirmState?.resolve(result);
    setConfirmState(null);
  };

  return (
    <UIContext.Provider value={{ showToast, confirm }}>
      {children}

      <div className="fixed top-6 left-1/2 -translate-x-1/2 z-[100] flex flex-col gap-2 items-center pointer-events-none w-full px-4">
        <AnimatePresence>
          {toasts.map(t => {
            const { icon: Icon, classes } = TOAST_STYLES[t.type];
            return (
              <motion.div
                key={t.id}
                initial={{ opacity: 0, y: -20, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -20, scale: 0.95 }}
                className={`pointer-events-auto flex items-center gap-2 bg-gradient-to-r ${classes} text-white px-5 py-3 rounded-full font-semibold shadow-lg text-sm max-w-[90vw]`}
              >
                <Icon size={18} className="shrink-0" />
                <span className="truncate">{t.message}</span>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {confirmState && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[110] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => resolveConfirm(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.9, opacity: 0 }}
              onClick={e => e.stopPropagation()}
              className="glass-card p-6 w-full max-w-sm"
            >
              <div className="flex items-center gap-3 mb-3">
                <div className={`p-2 rounded-full ${confirmState.danger ? 'bg-status-error/20 text-status-error' : 'bg-brand/20 text-brand-light'}`}>
                  <AlertTriangle size={22} />
                </div>
                <h3 className="text-lg font-bold">{confirmState.title || 'Confirmar'}</h3>
              </div>
              <p className="text-text-secondary mb-6 text-sm leading-relaxed">{confirmState.message}</p>
              <div className="flex gap-3">
                <button onClick={() => resolveConfirm(false)} className="flex-1 bg-neutral-bg3 hover:bg-neutral-bg4 text-text-secondary py-3 rounded-xl font-bold transition-colors">
                  {confirmState.cancelText || 'Cancelar'}
                </button>
                <button
                  onClick={() => resolveConfirm(true)}
                  className={`flex-[2] py-3 rounded-xl font-bold transition-all text-white ${confirmState.danger ? 'bg-status-error hover:bg-red-500' : 'bg-brand hover:bg-brand-hover'}`}
                >
                  {confirmState.confirmText || 'Confirmar'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </UIContext.Provider>
  );
}
