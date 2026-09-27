export default function Spinner({ label = "Loading" }) {
  return (
    <div className="flex items-center gap-3 py-10 justify-center text-slate">
      <span className="h-4 w-4 rounded-full border-2 border-forest border-t-transparent animate-spin" />
      <span className="text-sm font-mono">{label}…</span>
    </div>
  );
}
