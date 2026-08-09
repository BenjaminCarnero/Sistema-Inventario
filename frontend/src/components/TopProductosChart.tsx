import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

interface TopProducto {
  id: number;
  nombre: string;
  cantidad_vendida: number;
  total_recaudado: number;
}

function ChartTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as TopProducto;
  return (
    <div className="glass-card px-4 py-3 text-sm">
      <p className="font-semibold text-white mb-1">{p.nombre}</p>
      <p className="text-brand-light">${p.total_recaudado.toFixed(2)} recaudado</p>
      <p className="text-text-muted">{p.cantidad_vendida} unidades</p>
    </div>
  );
}

function formatCompact(value: number) {
  if (value >= 1000) return `$${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)}k`;
  return `$${value}`;
}

export function TopProductosChart({ data }: { data: TopProducto[] }) {
  const chartData = [...data].sort((a, b) => b.total_recaudado - a.total_recaudado).slice(0, 5);
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="barFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#8251EE" />
              <stop offset="100%" stopColor="#00F2FE" />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
          <XAxis
            dataKey="nombre"
            tick={{ fill: '#A1A1AA', fontSize: 12 }}
            axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
            tickLine={false}
            interval={0}
            tickFormatter={(v: string) => (v.length > 10 ? v.slice(0, 10) + '…' : v)}
          />
          <YAxis tick={{ fill: '#A1A1AA', fontSize: 12 }} axisLine={false} tickLine={false} width={52} tickFormatter={formatCompact} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
          <Bar dataKey="total_recaudado" fill="url(#barFill)" radius={[8, 8, 0, 0]} maxBarSize={48} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
