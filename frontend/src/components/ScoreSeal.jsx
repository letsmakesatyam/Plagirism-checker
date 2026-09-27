/**
 * The project's signature visual element: a circular "originality seal", styled
 * after a certification stamp. Used anywhere a percentage score needs to read as
 * an authoritative verdict rather than just a number — dashboards, report headers,
 * comparison cards.
 */
export default function ScoreSeal({ label, value, size = 96, invert = false }) {
  const hasValue = value !== null && value !== undefined;
  const pct = hasValue ? Math.max(0, Math.min(100, value)) : 0;
  // For "originality" style scores, high = good (forest). For "plagiarism"/"AI"
  // style scores, high = bad (rust). `invert` flips which end is the "good" end.
  const good = invert ? pct <= 30 : pct >= 70;
  const warn = invert ? pct > 30 && pct <= 60 : pct >= 40 && pct < 70;
  const color = !hasValue ? "#8A9793" : good ? "#1F4B3F" : warn ? "#B8863B" : "#B23A2E";

  const radius = size / 2 - 6;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - pct / 100);

  return (
    <div className="flex flex-col items-center gap-2" style={{ width: size }}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#DBDED4" strokeWidth="5" />
          {hasValue && (
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={color}
              strokeWidth="5"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              style={{ transition: "stroke-dashoffset 0.6s ease" }}
            />
          )}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono font-semibold" style={{ color, fontSize: size * 0.24 }}>
            {hasValue ? `${pct.toFixed(0)}` : "—"}
          </span>
          {hasValue && <span className="text-[10px] font-mono text-slate-light -mt-0.5">%</span>}
        </div>
      </div>
      {label && <span className="text-xs uppercase tracking-wide text-slate text-center">{label}</span>}
    </div>
  );
}
