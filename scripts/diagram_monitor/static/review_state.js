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

  return { candidateRound, reviewControls, preserveReviewDraft };
});
