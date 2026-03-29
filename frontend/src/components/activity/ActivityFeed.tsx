import type { ReactNode } from "react";

type FeedItem = {
  id: string;
};

type ActivityFeedProps<TItem extends FeedItem> = {
  isLoading: boolean;
  errorMessage?: string | null;
  items: TItem[];
  renderItem: (item: TItem) => ReactNode;
};

export function ActivityFeed<TItem extends FeedItem>({
  isLoading,
  errorMessage,
  items,
  renderItem,
}: ActivityFeedProps<TItem>) {
  if (isLoading && items.length === 0) {
    return <p className="text-sm text-app-text-quiet">Loading feed…</p>;
  }

  const hasError = errorMessage !== null && errorMessage !== undefined;
  if (hasError) {
    return (
      <div className="rounded-lg border border-app-border bg-app-surface p-4 text-sm text-app-text-muted shadow-card">
        {errorMessage || "Unable to load feed."}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-app-border bg-app-surface p-10 text-center shadow-card">
        <p className="text-sm font-medium text-app-text">
          Waiting for new activity…
        </p>
        <p className="mt-1 text-sm text-app-text-quiet">
          When updates happen, they will show up here.
        </p>
      </div>
    );
  }

  return <div className="space-y-4">{items.map(renderItem)}</div>;
}
