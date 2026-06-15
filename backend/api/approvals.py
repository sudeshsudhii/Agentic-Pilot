"""Approval API routes for human-in-the-loop decisions."""

from fastapi import APIRouter, HTTPException, Request

from backend.api.schemas import ApprovalDecisionRequest, ApprovalListResponse, ApprovalResponse

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=ApprovalListResponse)
async def list_approvals(request: Request) -> ApprovalListResponse:
    """Return pending approval requests."""

    approvals = await request.app.state.database.list_pending_approvals()
    return ApprovalListResponse(approvals=[ApprovalResponse(**approval.model_dump()) for approval in approvals])


@router.post("/{approval_id}/respond", response_model=ApprovalResponse)
async def respond_approval(
    approval_id: str,
    request_body: ApprovalDecisionRequest,
    request: Request,
) -> ApprovalResponse:
    """Apply a human approval decision and resume or fail the task."""

    approval = await request.app.state.database.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    await request.app.state.task_runner.approve(approval_id, request_body.decision)
    updated = await request.app.state.database.get_approval(approval_id)
    return ApprovalResponse(**updated.model_dump())
