import { createRootRoute, Outlet } from "@tanstack/react-router";

export const Route = createRootRoute({
  component: () => <Outlet />,
  notFoundComponent: () => (
    <div className="grid min-h-[60vh] place-items-center text-center">
      <div>
        <p className="font-mono text-sm text-ink-3">404</p>
        <h1 className="mt-1 font-display text-2xl font-semibold">This page doesn't exist</h1>
        <a href="/" className="mt-4 inline-block text-sm text-brand hover:underline">
          Go to the dashboard
        </a>
      </div>
    </div>
  ),
});
