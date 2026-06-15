import { ShieldCheck, X } from "lucide-react";
import { Approval } from "../api/client";

type Props = {
  approvals: Approval[];
  onDecision: (approvalId: string, decision: "approved" | "rejected") => Promise<void>;
};

export function ApprovalModal({ approvals, onDecision }: Props) {
  const approval = approvals.find((item) => item.status === "pending");
  if (!approval) {
    return null;
  }

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <div className="modal-title">
          <ShieldCheck size={22} />
          <h2>Approval Required</h2>
        </div>
        <p>{approval.prompt}</p>
        <div className="risk-line">
          <span>Risk</span>
          <strong>{approval.risk_level}</strong>
        </div>
        <div className="modal-actions">
          <button className="secondary-button" onClick={() => onDecision(approval.approval_id, "rejected")}>
            <X size={17} />
            Reject
          </button>
          <button className="primary-button" onClick={() => onDecision(approval.approval_id, "approved")}>
            <ShieldCheck size={17} />
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
