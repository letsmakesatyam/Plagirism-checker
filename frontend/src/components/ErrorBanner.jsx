export default function ErrorBanner({ message }) {
  if (!message) return null;
  return (
    <div className="border border-rust/30 bg-rust/5 text-rust text-sm rounded-sm px-4 py-3">
      {message}
    </div>
  );
}
