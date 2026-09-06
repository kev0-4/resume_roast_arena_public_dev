import type { LucideIcon } from "lucide-react";

export function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="flex flex-col items-center rounded-2xl border-[3px] border-black bg-white px-4 py-4 text-center shadow-[5px_5px_0_#000]">
      <Icon size={18} className="mb-2 text-brand-blue" strokeWidth={2.3} />
      <span className="font-display text-2xl text-black tabular-nums md:text-3xl">{value}</span>
      <span className="mt-1 font-mono text-[10px] font-bold uppercase tracking-wide text-black/45 md:text-[11px]">{label}</span>
      {sub && <span className="mt-0.5 font-mono text-[10px] font-semibold text-black/35">{sub}</span>}
    </div>
  );
}
