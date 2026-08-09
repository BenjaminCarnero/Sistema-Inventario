import type { LucideIcon } from 'lucide-react';

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-white/10 ${className}`} />;
}

export function EmptyState({ icon: Icon, title, description }: { icon: LucideIcon; title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-12 px-4">
      <div className="p-4 rounded-full bg-white/5 mb-4">
        <Icon size={28} className="text-text-muted" />
      </div>
      <p className="text-text-secondary font-semibold">{title}</p>
      {description && <p className="text-text-muted text-sm mt-1 max-w-xs">{description}</p>}
    </div>
  );
}
