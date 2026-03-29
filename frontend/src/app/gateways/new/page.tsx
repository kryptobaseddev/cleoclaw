"use client";

export const dynamic = "force-dynamic";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/auth/session";
import { useOrganizationMembership } from "@/lib/use-organization-membership";
import { GatewayWizard } from "@/components/gateways/GatewayWizard";
import { PairingApprovalModal } from "@/components/gateways/PairingApprovalModal";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";

export default function NewGatewayPage() {
  const { isSignedIn } = useAuth();
  const router = useRouter();
  const { isAdmin } = useOrganizationMembership(isSignedIn);

  const [showPairingModal, setShowPairingModal] = useState(false);
  const [pairingGatewayId, setPairingGatewayId] = useState<string | null>(null);
  const [pairingGatewayAddress, setPairingGatewayAddress] = useState("");

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to create a gateway.",
        forceRedirectUrl: "/gateways/new",
      }}
      title="Create gateway"
      description="Step-by-step setup for connecting an OpenClaw gateway."
      isAdmin={isAdmin}
      adminOnlyMessage="Only organization owners and admins can create gateways."
    >
      <GatewayWizard
        onComplete={(result) => {
          if (result.pairingRequired) {
            setPairingGatewayId(result.gatewayId);
            setPairingGatewayAddress("");
            setShowPairingModal(true);
          } else if (result.boardId) {
            router.push(`/boards/${result.boardId}?welcome=1`);
          } else {
            router.push(`/gateways/${result.gatewayId}`);
          }
        }}
        onCancel={() => router.push("/gateways")}
      />
      {showPairingModal && pairingGatewayId ? (
        <PairingApprovalModal
          gatewayId={pairingGatewayId}
          gatewayAddress={pairingGatewayAddress}
          onComplete={(boardId) => {
            setShowPairingModal(false);
            if (boardId) {
              router.push(`/boards/${boardId}?welcome=1`);
            } else {
              router.push(`/gateways/${pairingGatewayId}`);
            }
          }}
          onCancel={() => {
            setShowPairingModal(false);
            router.push(`/gateways/${pairingGatewayId}`);
          }}
        />
      ) : null}
    </DashboardPageLayout>
  );
}
