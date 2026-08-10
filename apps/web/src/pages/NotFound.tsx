import { Link } from "react-router";

export function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 p-16 text-center">
      <h1 className="text-lg font-semibold">Page not found</h1>
      <p className="text-sm text-muted-foreground">
        That route doesn&apos;t exist.
      </p>
      <Link to="/chat" className="text-sm text-primary underline">
        Back to chat
      </Link>
    </div>
  );
}
