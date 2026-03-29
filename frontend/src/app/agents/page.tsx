"use client";

export const dynamic = "force-dynamic";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { useAuth } from "@/auth/session";
import { useQueryClient } from "@tanstack/react-query";
import { Bot } from "lucide-react";

import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";

import { ApiError } from "@/api/mutator";
import {
  type listAgentsApiV1AgentsGetResponse,
  getListAgentsApiV1AgentsGetQueryKey,
  useDeleteAgentApiV1AgentsAgentIdDelete,
  useListAgentsApiV1AgentsGet,
} from "@/api/generated/agents/agents";
import {
  type listBoardsApiV1BoardsGetResponse,
  getListBoardsApiV1BoardsGetQueryKey,
  useListBoardsApiV1BoardsGet,
} from "@/api/generated/boards/boards";
import { type AgentRead } from "@/api/generated/model";
import { createOptimisticListDeleteMutation } from "@/lib/list-delete";
import { cn } from "@/lib/utils";
import { formatRelativeTimestamp } from "@/lib/formatters";
import { useOrganizationMembership } from "@/lib/use-organization-membership";
import { useUrlSorting } from "@/lib/use-url-sorting";

const AGENT_SORTABLE_COLUMNS = [
  "name",
  "status",
  "openclaw_session_id",
  "board_id",
  "last_seen_at",
  "updated_at",
];

export default function AgentsPage() {
  const { isSignedIn } = useAuth();
  const queryClient = useQueryClient();
  const router = useRouter();

  const { isAdmin } = useOrganizationMembership(isSignedIn);
  const { sorting, onSortingChange } = useUrlSorting({
    allowedColumnIds: AGENT_SORTABLE_COLUMNS,
    defaultSorting: [{ id: "name", desc: false }],
    paramPrefix: "agents",
  });

  const [deleteTarget, setDeleteTarget] = useState<AgentRead | null>(null);

  const boardsKey = getListBoardsApiV1BoardsGetQueryKey();
  const agentsKey = getListAgentsApiV1AgentsGetQueryKey();

  const boardsQuery = useListBoardsApiV1BoardsGet<
    listBoardsApiV1BoardsGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchInterval: 30_000,
      refetchOnMount: "always",
    },
  });

  const agentsQuery = useListAgentsApiV1AgentsGet<
    listAgentsApiV1AgentsGetResponse,
    ApiError
  >(undefined, {
    query: {
      enabled: Boolean(isSignedIn && isAdmin),
      refetchInterval: 15_000,
      refetchOnMount: "always",
    },
  });

  const boards = useMemo(
    () =>
      boardsQuery.data?.status === 200
        ? (boardsQuery.data.data.items ?? [])
        : [],
    [boardsQuery.data],
  );
  const agents = useMemo(
    () =>
      agentsQuery.data?.status === 200
        ? (agentsQuery.data.data.items ?? [])
        : [],
    [agentsQuery.data],
  );

  const deleteMutation = useDeleteAgentApiV1AgentsAgentIdDelete<
    ApiError,
    { previous?: listAgentsApiV1AgentsGetResponse }
  >(
    {
      mutation: createOptimisticListDeleteMutation<
        AgentRead,
        listAgentsApiV1AgentsGetResponse,
        { agentId: string }
      >({
        queryClient,
        queryKey: agentsKey,
        getItemId: (agent) => agent.id,
        getDeleteId: ({ agentId }) => agentId,
        onSuccess: () => {
          setDeleteTarget(null);
        },
        invalidateQueryKeys: [agentsKey, boardsKey],
      }),
    },
    queryClient,
  );

  const handleDelete = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate({ agentId: deleteTarget.id });
  };

  return (
    <>
      <DashboardPageLayout
        signedOut={{
          message: "Sign in to view agents.",
          forceRedirectUrl: "/agents",
          signUpForceRedirectUrl: "/agents",
        }}
        title="Agents Roster"
        description={`${agents.length} agent${agents.length === 1 ? "" : "s"} total.`}
        headerActions={
          agents.length > 0 ? (
            <Button onClick={() => router.push("/agents/new")}>
              New agent
            </Button>
          ) : null
        }
        isAdmin={isAdmin}
        adminOnlyMessage="Only organization owners and admins can access agents."
        stickyHeader
      >
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.map((agent) => {
            const isOnline =
              (agent.status ?? "").toLowerCase() === "online";
            const isBusy = ["busy", "provisioning"].includes(
              (agent.status ?? "").toLowerCase(),
            );
            const board = boards.find((b) => b.id === agent.board_id);
            return (
              <Link
                key={agent.id}
                href={`/agents/${agent.id}`}
                className="p-6 rounded-xl bg-app-surface-strong backdrop-blur-glass border border-app-border relative overflow-hidden group hover:border-app-accent/20 transition-all"
              >
                {/* Background icon watermark */}
                <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                  <Bot className="h-10 w-10" />
                </div>

                {/* Agent header: 48px status circle + name */}
                <div className="flex items-center gap-4 mb-6">
                  <div
                    className={cn(
                      "w-12 h-12 rounded-full bg-app-surface-muted border flex items-center justify-center",
                      isOnline &&
                        "border-app-accent/30 shadow-[0_0_15px_rgba(47,217,244,0.4)]",
                      isBusy &&
                        "border-app-warning/30 shadow-[0_0_15px_rgba(233,195,73,0.3)]",
                      !isOnline && !isBusy && "border-app-border",
                    )}
                  >
                    <Bot
                      className={cn(
                        "h-5 w-5",
                        isOnline && "text-app-accent",
                        isBusy && "text-app-warning",
                        !isOnline && !isBusy && "text-app-text-quiet",
                      )}
                    />
                  </div>
                  <div>
                    <h3 className="font-display text-xl text-app-text">
                      {agent.name}
                    </h3>
                    <p className="font-label text-[10px] text-app-text-quiet tracking-wider uppercase">
                      {board?.name || "Unassigned"}
                    </p>
                  </div>
                </div>

                {/* Status + last seen */}
                <div className="space-y-4">
                  <div className="flex justify-between items-end">
                    <div>
                      <div className="font-label text-[9px] uppercase text-app-text-quiet mb-1">
                        Status
                      </div>
                      <div
                        className={cn(
                          "text-sm font-medium",
                          isOnline && "text-app-accent",
                          isBusy && "text-app-warning",
                          !isOnline && !isBusy && "text-app-text-quiet",
                        )}
                      >
                        {agent.status || "Unknown"}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-label text-[9px] uppercase text-app-text-quiet mb-1">
                        Last Seen
                      </div>
                      <div className="text-xs text-app-text-quiet">
                        {agent.last_seen_at
                          ? formatRelativeTimestamp(agent.last_seen_at)
                          : "Never"}
                      </div>
                    </div>
                  </div>
                  <div className="flex justify-between items-center text-[10px] text-app-text-quiet">
                    <span>ID: {agent.id.slice(0, 8)}...</span>
                    {agent.openclaw_session_id ? (
                      <span className="text-app-accent">Session active</span>
                    ) : null}
                  </div>
                </div>
              </Link>
            );
          })}
        </div>

        {/* Empty state */}
        {agents.length === 0 && !agentsQuery.isLoading && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-16 h-16 rounded-full bg-app-surface-muted flex items-center justify-center mb-4">
              <Bot className="h-8 w-8 text-app-text-quiet" />
            </div>
            <h3 className="text-lg font-display text-app-text mb-2">
              No Agents Provisioned
            </h3>
            <p className="text-sm text-app-text-quiet mb-6 max-w-md">
              Agents are created when you connect a gateway. Connect your first
              gateway to provision an agent.
            </p>
            <Link
              href="/gateways/new"
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#2fd9f4] to-[#06b6d4] px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:shadow-glow"
            >
              Connect Gateway
            </Link>
          </div>
        )}

        {agentsQuery.error ? (
          <p className="mt-4 text-sm text-red-500">
            {agentsQuery.error.message}
          </p>
        ) : null}
      </DashboardPageLayout>

      <ConfirmActionDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null);
          }
        }}
        ariaLabel="Delete agent"
        title="Delete agent"
        description={
          <>
            This will remove {deleteTarget?.name}. This action cannot be undone.
          </>
        }
        errorMessage={deleteMutation.error?.message}
        onConfirm={handleDelete}
        isConfirming={deleteMutation.isPending}
      />
    </>
  );
}
