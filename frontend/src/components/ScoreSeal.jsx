/**
 * Circular "originality seal" / metric badge.
 * Supports percentage scores as well as categorical signals (e.g. AI writing signal: Low/Elevated/Legacy/Unavailable).
 */
export default function ScoreSeal({
  label,
  value,
  textValue = null,
  unit = "%",
  size = 96,
  invert = false,
  status = null,
}) {
  const isNumeric = typeof value === "number" && !isNaN(value);
  const pct = isNumeric ? Math.max(0, Math.min(100, value)) : 0;

  // Status/color determination
  let color = "#8A9793";
  if (status === "legacy") {
    color = "#8A9793";
  } else if (status === "insufficient_text" || status === "unreliable_ocr" || status === "unavailable") {
    color = "#8A9793";
  } else if (isNumeric) {
    const good = invert ? pct <= 30 : pct >= 70;
    const warn = invert ? pct > 30 && pct <= 60 : pct >= 40 && pct < 70;
    color = good ? "#1F4B3F" : warn ? "#B8863B" : "#B23A2E";
  }

  const radius = size / 2 - 6;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - pct / 100);

  const displayMain = textValue !== null ? textValue : isNumeric ? `${pct.toFixed(0)}` : "—";
  const showUnit = textValue === null && isNumeric && unit;

  return (
    <div className="flex flex-col items-center gap-2" style={{ width: size }}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#DBDED4" strokeWidth="5" />
          {isNumeric && (
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
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-1">
          <span
            className="font-mono font-semibold truncate leading-tight"
            style={{
              color,
              fontSize: textValue ? Math.max(11, size * 0.17) : size * 0.24,
            }}
          >
            {displayMain}
          </span>
          {showUnit && <span className="text-[10px] font-mono text-slate-light -mt-0.5">{unit}</span>}
        </div>
      </div>
      {label && <span className="text-xs uppercase tracking-wide text-slate text-center">{label}</span>}
    </div>
  );
}
