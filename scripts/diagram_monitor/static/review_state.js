(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.DiagramReviewState = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const BUSY = new Set(["queued", "revision_running"]);

  function reviewControls({ status = "unreviewed", deterministicAudit = "missing" } = {}) {
    const busy = BUSY.has(status);
    const accepted = status === "accepted";
    const auditCanAccept = deterministicAudit === "pass";
    return {
      busy,
      acceptDisabled: busy || accepted || !auditCanAccept,
      submitDisabled: busy || accepted,
      feedbackDisabled: busy || accepted,
      acceptReason: accepted || auditCanAccept ? "" : "确定性审核未通过，不能接受当前图",
    };
  }

  function preserveReviewDraft(drafts, key, value) {
    if (value) drafts[key] = value;
    return drafts[key] || "";
  }

  function candidateRound(job = {}) {
    const rounds = Array.isArray(job.rounds) ? job.rounds : [];
    const indexes = rounds.map((item) => item.round_index).filter(Number.isInteger);
    const exists = (roundIndex) => Number.isInteger(roundIndex) && indexes.includes(roundIndex);
    const requested = job.human_review?.requested_round;
    const revisionState = ["queued", "revision_running", "revision_completed", "revision_failed"].includes(job.human_review?.status);
    if (revisionState && exists(requested)) return requested;
    if (exists(job.selected_round)) return job.selected_round;
    if (exists(job.effective_round)) return job.effective_round;
    return indexes.length ? Math.max(...indexes) : 0;
  }

  function candidatePreview(job = {}, roundIndex = candidateRound(job)) {
    const rounds = Array.isArray(job.rounds) ? job.rounds : [];
    const round = rounds.find((item) => item.round_index === roundIndex);
    if (round?.preview_path) return round.preview_path;

    const isRecordedFinal = roundIndex === job.selected_round || roundIndex === job.effective_round;
    const isUnversionedInitial = (
      rounds.length === 1
      && rounds[0]?.round_index === roundIndex
      && !Number.isInteger(job.selected_round)
      && !Number.isInteger(job.effective_round)
    );
    return (isRecordedFinal || isUnversionedInitial) ? (job.preview_path || "") : "";
  }

  function codexTaskBinding(review = {}, submitting = false) {
    const threadId = String(review.agent_thread_id || "").trim();
    if (threadId) return { status: "created", label: "已创建", threadId };
    const status = submitting ? "creating" : String(review.codex_task_status || "");
    if (status === "creating") return { status, label: "正在创建", threadId: "" };
    if (status === "failed") return { status, label: "创建失败", threadId: "" };
    return null;
  }

  return { candidatePreview, candidateRound, codexTaskBinding, reviewControls, preserveReviewDraft };
});
