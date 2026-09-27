export default function EmptyState({ title, description, action }) {
  return (
    <div className="border border-dashed border-line rounded-sm py-14 px-6 text-center">
      <p className="font-display text-lg text-ink mb-1">{title}</p>
      {description && <p className="text-sm text-slate max-w-md mx-auto">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
