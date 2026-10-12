export function ErrorNotice({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="notice notice-error" role="alert">
      {message}
    </p>
  );
}
