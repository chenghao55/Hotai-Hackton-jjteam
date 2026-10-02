import { useState, useEffect } from "react";

const API_BASE = "http://127.0.0.1:8000";

const CATEGORY_LABEL = { scratch: "刮痕", collision_damage: "碰撞損傷", cleanliness: "清潔／汙損" };
const SEVERITY_LABEL = { minor: "輕微", moderate: "中等", severe: "嚴重" };
const REVIEW_LABEL = { needs_review: "待人工覆核", auto_accepted: "AI自動通過", confirmed: "已確認", rejected: "車體無問題", corrected: "已修正" };
const STATUS_LABEL = { unassigned: "未派工", dispatched: "已派工", processing: "處理中", pending_payment: "待付款", completed: "已結案" };
const STATUS_ORDER = ["unassigned", "dispatched", "processing", "pending_payment", "completed"];

// 依跟 D 同學討論的規格：每個案件 12 張照片，外觀 8 張 + 內裝 4 張，每張可以有「標記/沒標記」，標記來源是 AI 或人工
const EXTERIOR_POSITIONS = ["車頭", "車尾", "左側", "右側", "左前角", "右前角", "左後角", "右後角"];
const INTERIOR_POSITIONS = ["儀表板", "駕駛座", "後座", "後車廂"];
const ALL_POSITIONS = [...EXTERIOR_POSITIONS, ...INTERIOR_POSITIONS];

function generatePhotos(c) {
  return ALL_POSITIONS.map((label, i) => ({
    id: `${c.case_id}-P${i + 1}`,
    label,
    flagged: false,
    markType: null,
  }));
}

function reviewPillClass(state) {
  if (state === "needs_review") return "pill-amber";
  if (state === "rejected") return "pill-red";
  if (state === "corrected") return "pill-neutral";
  return "pill-lime";
}
function priorityClass(score) {
  if (score === null) return "pill-neutral";
  if (score >= 70) return "pill-red";
  if (score >= 40) return "pill-amber";
  return "pill-lime";
}
function PriorityBadge({ score }) {
  return <span className={`pill ${priorityClass(score)}`}>{score === null ? "尚未計算" : score}</span>;
}
function nextAction(status) {
  if (status === "unassigned") return { label: "派工", key: "dispatch" };
  if (status === "dispatched") return { label: "開始處理", key: "start" };
  if (status === "processing") return { label: "完成處理", key: "finish" };
  if (status === "pending_payment") return { label: "確認付款", key: "pay" };
  return null;
}

// 後端回傳的錯誤訊息可能是英文，統一顯示中文提示，原始訊息只留在瀏覽器 console
function notifyError(actionName, err) {
  console.error(`${actionName}失敗：`, err);
  alert(`${actionName}失敗，請確認案件目前的狀態後再試一次。`);
}

// 人工修正過就採用修正後的損傷類型／嚴重程度，changed 表示跟 AI 原判不同
function effectiveJudgement(d) {
  const adjusted = d.review_state === "corrected" && d.reviewed_category != null && d.reviewed_severity != null;
  return {
    category: adjusted ? d.reviewed_category : d.category,
    severity: adjusted ? d.reviewed_severity : d.severity,
    changed: adjusted && (d.reviewed_category !== d.category || d.reviewed_severity !== d.severity),
  };
}

function CarThumb() {
  return (
    <div className="thumb">
      <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6">
        <rect x="3" y="7" width="18" height="12" rx="2" />
        <circle cx="8" cy="19" r="1.6" /><circle cx="16" cy="19" r="1.6" />
      </svg>
    </div>
  );
}

function Header({ pendingCount }) {
  return (
    <header>
      <div className="brand">
        <div className="brand-mark">
          <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
          </svg>
        </div>
        <div>
          <div className="brand-text">車況信任鏈 · 案件決策與流程管理中心</div>
          <div className="brand-sub">依 AI 信心分數分流案件，追蹤覆核到結案的完整流程</div>
        </div>
      </div>
      <div className="header-right">
        <span>今日待處理 {pendingCount} 件</span>
        <div className="avatar">陳</div>
      </div>
    </header>
  );
}

function PendingTable({ cases, onOpen }) {
  return (
    <div className="table-card">
      <table>
        <thead>
          <tr><th>處理狀態</th><th>車牌號碼</th><th>借車時間</th><th>還車時間</th><th>借車前照片</th><th>借車後照片</th><th>借車人</th><th>優先級</th></tr>
        </thead>
        <tbody>
          {cases.map((c) => {
            const d = c.detections[0];
            return (
              <tr key={c.case_id} onClick={() => onOpen(c)}>
                <td>
                  {d ? <span className={`pill ${reviewPillClass(d.review_state)}`}>{REVIEW_LABEL[d.review_state]}</span> : <span className="pill pill-neutral">無判讀結果</span>}
                </td>
                <td className="plate">{c.plate}</td>
                <td>{c.out}</td>
                <td>{c.in}</td>
                <td><CarThumb /></td>
                <td><CarThumb /></td>
                <td>{c.borrower.split(" · ")[0]}</td>
                <td><PriorityBadge score={c.priority_score} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ProcessingList({ cases, onOpen }) {
  return (
    <div className="proc-list">
      {cases.map((c) => {
        const currentIdx = STATUS_ORDER.indexOf(c.status);
        const d = c.detections[0];
        const j = d ? effectiveJudgement(d) : null;
        return (
          <div className="proc-card" key={c.case_id} onClick={() => onOpen(c)}>
            <div className="proc-top">
              <div>
                <div className="proc-title">
                  {c.case_id} · {c.borrower}
                </div>
                <div className="proc-sub">車牌 {c.plate} · {j ? `${CATEGORY_LABEL[j.category]}・${SEVERITY_LABEL[j.severity]}` : "無判讀結果"} · 優先度分數 {c.priority_score ?? "尚未計算"}</div>
              </div>
              <span className={`pill ${priorityClass(c.priority_score)}`}>{STATUS_LABEL[c.status]}</span>
            </div>
            <div className="stepper">
              {STATUS_ORDER.map((s, i) => (
                <div className={`step ${i < currentIdx ? "done" : i === currentIdx ? "current" : ""}`} key={s}>
                  <div className="step-line"></div><div className="step-dot"></div><div className="step-label">{STATUS_LABEL[s]}</div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DoneTable({ cases, onOpen }) {
  return (
    <div className="table-card">
      <table>
        <thead>
          <tr><th>處理紀錄</th><th>車牌號碼</th><th>借車時間</th><th>還車時間</th><th>借車前照片</th><th>借車後照片</th><th>借車人</th><th>付款狀態</th></tr>
        </thead>
        <tbody>
          {cases.map((c) => {
            const d = c.detections[0];
            return (
              <tr key={c.case_id} onClick={() => onOpen(c)}>
                <td>
                  <span className="pill pill-neutral">{d ? REVIEW_LABEL[d.review_state] : "無判讀結果"} → 已結案</span>
                </td>
                <td className="plate">{c.plate}</td>
                <td>{c.out}</td>
                <td>{c.in}</td>
                <td><CarThumb /></td>
                <td><CarThumb /></td>
                <td>{c.borrower}</td>
                <td><span className={`pill ${c.payment_amount > 0 ? "pill-lime" : "pill-neutral"}`}>{c.payment_amount > 0 ? `已收款 NT$${c.payment_amount}` : "無需收款"}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PhotoGallery({ photos, editable, onToggle }) {
  return (
    <div className="photo-gallery">
      {photos.map((p) => (
        <div
          className={`photo-tile ${p.markType === "rejected" ? "rejected" : p.flagged ? "flagged" : ""} ${editable ? "editable" : ""}`}
          key={p.id}
          onClick={editable ? () => onToggle(p.label) : undefined}
        >
          <div className="photo-tile-frame">
            <CarThumbBig />
            {p.markType === "ai" && <span className="flag-badge flag-badge-ai">AI</span>}
            {p.markType === "human" && <span className="flag-badge flag-badge-human">人工</span>}
            {p.markType === "draft" && <span className="flag-badge flag-badge-draft">編輯中</span>}
            {p.markType === "rejected" && <span className="flag-badge flag-badge-rejected">✕</span>}
          </div>
          <div className="photo-tile-label">{p.label}</div>
        </div>
      ))}
    </div>
  );
}

function emptyDetectionRow() {
  return { category: "scratch", severity: "minor", confidence: "", borrow: "", return_: "" };
}

function NewCaseForm({ onClose, onCreate }) {
  const [caseId, setCaseId] = useState("");
  const [plate, setPlate] = useState("");
  const [borrower, setBorrower] = useState("");
  const [rows, setRows] = useState([emptyDetectionRow()]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function updateRow(i, patch) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }
  function addRow() {
    setRows((prev) => [...prev, emptyDetectionRow()]);
  }
  function removeRow(i) {
    setRows((prev) => (prev.length > 1 ? prev.filter((_, idx) => idx !== i) : prev));
  }

  function validate() {
    if (!caseId.trim()) return "請輸入案件編號。";
    for (const r of rows) {
      const conf = Number(r.confidence);
      if (r.confidence.trim() === "" || Number.isNaN(conf) || conf < 0 || conf > 1) return "每一筆判讀的信心度都要是 0 到 1 之間的數字。";
      if (!r.borrow.trim() || !r.return_.trim()) return "每一筆判讀都要填借車照片 ID 和還車照片 ID。";
    }
    return "";
  }

  function handleSubmit() {
    const msg = validate();
    if (msg) {
      setError(msg);
      return;
    }
    setError("");
    setSaving(true);
    const payload = {
      case_id: caseId.trim(),
      detections: rows.map((r, i) => ({
        detection_id: `${caseId.trim()}-D${i + 1}`,
        borrow_photo_id: r.borrow.trim(),
        return_photo_id: r.return_.trim(),
        category: r.category,
        severity: r.severity,
        confidence: Number(r.confidence),
      })),
    };
    const decor = { plate: plate.trim() || "—", borrower: borrower.trim() || "（後端尚未提供借車人資訊）" };
    Promise.resolve(onCreate(payload, decor)).then((result) => {
      setSaving(false);
      if (result && result.ok) {
        onClose();
      } else {
        setError((result && result.error) || "新增案件失敗，請稍後再試一次。");
      }
    });
  }

  return (
    <>
      <div className="backdrop show" onClick={onClose}></div>
      <div className="new-case-modal">
        <div className="new-case-head">
          <h2>新增案件</h2>
          <div className="drawer-close" onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </div>
        </div>

        <div className="new-case-body">
          <div className="form-row-group">
            <label className="edit-field">案件編號
              <input type="text" value={caseId} onChange={(e) => setCaseId(e.target.value)} placeholder="例如 CASE-4001" />
            </label>
            <label className="edit-field">車牌號碼（選填）
              <input type="text" value={plate} onChange={(e) => setPlate(e.target.value)} />
            </label>
            <label className="edit-field">借車人（選填）
              <input type="text" value={borrower} onChange={(e) => setBorrower(e.target.value)} />
            </label>
          </div>

          <div className="section-label" style={{ marginTop: 18 }}>判讀結果（可以新增多筆）</div>
          {rows.map((r, i) => (
            <div className="det-row" key={i}>
              <label className="edit-field">損傷類型
                <select value={r.category} onChange={(e) => updateRow(i, { category: e.target.value })}>
                  {Object.keys(CATEGORY_LABEL).map((k) => <option key={k} value={k}>{CATEGORY_LABEL[k]}</option>)}
                </select>
              </label>
              <label className="edit-field">嚴重程度
                <select value={r.severity} onChange={(e) => updateRow(i, { severity: e.target.value })}>
                  {Object.keys(SEVERITY_LABEL).map((k) => <option key={k} value={k}>{SEVERITY_LABEL[k]}</option>)}
                </select>
              </label>
              <label className="edit-field">信心度（0～1）
                <input type="text" inputMode="decimal" value={r.confidence} onChange={(e) => updateRow(i, { confidence: e.target.value })} placeholder="0.80" />
              </label>
              <label className="edit-field">借車照片 ID
                <input type="text" value={r.borrow} onChange={(e) => updateRow(i, { borrow: e.target.value })} />
              </label>
              <label className="edit-field">還車照片 ID
                <input type="text" value={r.return_} onChange={(e) => updateRow(i, { return_: e.target.value })} />
              </label>
              <button className="btn btn-ghost btn-row-remove" onClick={() => removeRow(i)} disabled={rows.length === 1}>移除</button>
            </div>
          ))}
          <button className="btn btn-secondary" onClick={addRow}>新增一筆判讀</button>

          {error && <div className="form-error" style={{ marginTop: 14 }}>{error}</div>}

          <div className="actions" style={{ marginTop: 18 }}>
            <button className="btn btn-primary" onClick={handleSubmit} disabled={saving}>建立案件</button>
            <button className="btn btn-ghost" onClick={onClose} disabled={saving}>取消</button>
          </div>
        </div>
      </div>
    </>
  );
}

function Drawer({ item, onClose, onReview, onTransition, onCompleteWithoutAction, onDispute, onCorrect, onSetPayment, connected }) {
  const [editMode, setEditMode] = useState(false);
  const [draftCategory, setDraftCategory] = useState("scratch");
  const [draftSeverity, setDraftSeverity] = useState("minor");
  const [editError, setEditError] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [payEdit, setPayEdit] = useState(false);
  const [draftAmount, setDraftAmount] = useState("");
  const [payError, setPayError] = useState("");
  const [paySaving, setPaySaving] = useState(false);

  useEffect(() => {
    setEditMode(false);
    setEditError("");
    setEditSaving(false);
    setPayEdit(false);
    setPayError("");
    setPaySaving(false);
  }, [item && item.case_id]);

  if (!item) return null;
  const d = item.detections[0];
  const j = d ? effectiveJudgement(d) : null;
  const action = nextAction(item.status);
  const noContentToHandle =
    (item.status === "unassigned" || item.status === "dispatched") &&
    item.payment_amount === 0 &&
    item.detections.every((det) => det.review_state === "rejected");
  // 後端規定：只有未派工／已派工／處理中可以改金額，進入待付款或已結案就鎖住
  const canEditPayment = ["unassigned", "dispatched", "processing"].includes(item.status);

  function startEdit() {
    setDraftCategory(d.reviewed_category ?? d.category);
    setDraftSeverity(d.reviewed_severity ?? d.severity);
    setEditError("");
    setEditMode(true);
  }
  function cancelEdit() {
    setEditMode(false);
    setEditError("");
  }
  function saveEdit() {
    // 後端規定：修正時損傷類型或嚴重程度至少要有一項跟 AI 原判不同，否則會被拒絕
    if (draftCategory === d.category && draftSeverity === d.severity) {
      setEditError("修正時，損傷類型或嚴重程度至少要有一項和 AI 原判不同，才能儲存。");
      return;
    }
    setEditError("");
    setEditSaving(true);
    Promise.resolve(onCorrect(item.case_id, d.detection_id, { category: draftCategory, severity: draftSeverity })).then((ok) => {
      setEditSaving(false);
      if (ok) setEditMode(false);
    });
  }

  function startPay() {
    setDraftAmount(item.payment_amount > 0 ? String(item.payment_amount) : "");
    setPayError("");
    setPayEdit(true);
  }
  function cancelPay() {
    setPayEdit(false);
    setPayError("");
  }
  function savePay() {
    // 全形數字（２４００）與千分位逗號先轉成一般數字，再檢查是否為 0 以上的整數
    const cleaned = draftAmount.trim().replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xFEE0)).replace(/[,，]/g, "");
    if (!/^\d+$/.test(cleaned) || !Number.isSafeInteger(Number(cleaned))) {
      setPayError("請輸入 0 以上的整數（新台幣），不能有小數點或負號。");
      return;
    }
    const amount = Number(cleaned);
    if (amount === item.payment_amount) {
      cancelPay();
      return;
    }
    setPayError("");
    setPaySaving(true);
    Promise.resolve(onSetPayment(item.case_id, amount)).then((ok) => {
      setPaySaving(false);
      if (ok) setPayEdit(false);
    });
  }

  return (
    <>
      <div className="backdrop show" onClick={onClose}></div>
      <div className="drawer show">
        <div className="drawer-close" onClick={onClose}>
          <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
        </div>
        <h2>{item.case_id} · {item.borrower}</h2>
        <div className="sub">車牌 {item.plate} · 借車 {item.out} → 還車 {item.in}</div>

        <div className="section-label">照片版位（後端尚未提供照片清單）</div>
        <PhotoGallery photos={generatePhotos(item)} editable={false} />

        <div className="section-label">AI 判讀結果</div>
        {d ? <>
          {editMode ? (
            <div className="edit-fields">
              <label className="edit-field">損傷類型
                <select value={draftCategory} onChange={(e) => setDraftCategory(e.target.value)}>
                  {Object.keys(CATEGORY_LABEL).map((k) => <option key={k} value={k}>{CATEGORY_LABEL[k]}</option>)}
                </select>
              </label>
              <label className="edit-field">嚴重程度
                <select value={draftSeverity} onChange={(e) => setDraftSeverity(e.target.value)}>
                  {Object.keys(SEVERITY_LABEL).map((k) => <option key={k} value={k}>{SEVERITY_LABEL[k]}</option>)}
                </select>
              </label>
            </div>
          ) : (
            <div className="diff-chip"><span className="dot"></span><b>{CATEGORY_LABEL[j.category]}</b><span className="conf-text">嚴重程度：{SEVERITY_LABEL[j.severity]}</span></div>
          )}
          {(editMode || j.changed) && (
            <div className="orig-note">AI 原判：{CATEGORY_LABEL[d.category]}・{SEVERITY_LABEL[d.severity]}{!editMode && "（已由人工調整）"}</div>
          )}
          <br />
          {typeof d.confidence === "number" && (
            <div className="diff-chip"><span className="dot" style={{ background: "var(--text-muted)" }}></span><b>信心度</b><span className="conf-text">{d.confidence.toFixed(2)}</span></div>
          )}
        </> : <div className="gap-note">此案件沒有判讀結果；仍可依目前案件狀態執行合法的工作流程操作。</div>}

        <div className="checklist">
          <div className="section-label">案件資訊</div>
          <div className="check-row"><span>優先度分數</span><PriorityBadge score={item.priority_score} /></div>
          <div className="check-row"><span>審核狀態</span>{d ? <span className={`pill ${reviewPillClass(d.review_state)}`}>{REVIEW_LABEL[d.review_state]}</span> : <span className="pill pill-neutral">無判讀結果</span>}</div>
          <div className="check-row pay-row">
            <span>付款金額</span>
            {payEdit ? (
              <span className="pay-edit">
                <span className="pay-prefix">NT$</span>
                <input
                  className="pay-input"
                  type="text"
                  inputMode="numeric"
                  aria-label="付款金額"
                  autoFocus
                  value={draftAmount}
                  onChange={(e) => setDraftAmount(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") savePay(); if (e.key === "Escape") cancelPay(); }}
                />
                <button className="pay-btn" onClick={savePay} disabled={paySaving}>儲存</button>
                <button className="pay-btn pay-btn-ghost" onClick={cancelPay} disabled={paySaving}>取消</button>
              </span>
            ) : (
              <span className="pay-view">
                {item.payment_amount > 0 ? `NT$ ${item.payment_amount}` : "—"}
                {canEditPayment && <button className="pay-link" onClick={startPay}>設定金額</button>}
              </span>
            )}
          </div>
          {payEdit && payError && <div className="pay-error">{payError}</div>}
          {!canEditPayment && <div className="pay-hint">此階段不能修改金額</div>}
          {item.status === "processing" && <div className="pay-hint">完成處理時，金額大於 0 會進入待付款，等於 0 直接結案</div>}
        </div>

        <div className="section-label">操作</div>
        {connected && !editMode && <div className="gap-note">此畫面的可用操作會直接呼叫 Module E。</div>}
        {editMode && editError && <div className="form-error">{editError}</div>}
        {editMode ? (
          <div className="actions">
            <button className="btn btn-primary" onClick={saveEdit} disabled={editSaving}>儲存修正</button>
            <button className="btn btn-ghost" onClick={cancelEdit} disabled={editSaving}>取消</button>
          </div>
        ) : (
          <div className="actions">
            {d?.review_state === "needs_review" && (
              <>
                <button className="btn btn-primary" onClick={() => onReview(item.case_id, d.detection_id, "confirmed")}>確認</button>
                <button className="btn btn-secondary" onClick={startEdit}>修正</button>
                <button className="btn btn-ghost" onClick={() => onReview(item.case_id, d.detection_id, "rejected")}>車體無問題</button>
              </>
            )}
            {action && !(action.key === "finish" && item.detections.some((det) => det.review_state === "needs_review")) && (
              <button className="btn btn-primary" onClick={() => onTransition(item.case_id)}>{action.label}</button>
            )}
            {noContentToHandle && (
              <button className="btn btn-ghost" onClick={() => onCompleteWithoutAction(item.case_id)}>無需處理／結案</button>
            )}
            {d && d.review_state !== "needs_review" && (
              <button className="btn btn-ghost" onClick={() => onDispute(item.case_id, d.detection_id)}>顧客申訴（重新審核）</button>
            )}
          </div>
        )}
        {action && action.key === "finish" && item.detections.some((det) => det.review_state === "needs_review") && (
          <div className="gap-note">還有 Detection 待人工覆核，finish_processing() 目前會拒絕完成處理，需先完成審核。</div>
        )}
      </div>
    </>
  );
}

function CarThumbBig() {
  return (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="7" width="18" height="12" rx="2" /><circle cx="8" cy="19" r="1.6" /><circle cx="16" cy="19" r="1.6" /><path d="M5 7l1.5-3h11L19 7" />
    </svg>
  );
}

function normalizeCase(c) {
  // 真後端回傳的 Case 沒有租車情境欄位（plate/out/in/borrower），這些原本就是我方後台自己畫面加的裝飾欄位
  return { plate: "—", out: "—", in: "—", borrower: "（後端尚未提供借車人資訊）", ...c };
}

export default function CaseQueueConsole() {
  const [activeTab, setActiveTab] = useState("pending");
  const [cases, setCases] = useState([]);
  const [selected, setSelected] = useState(null);
  const [connected, setConnected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showNewCase, setShowNewCase] = useState(false);

  useEffect(() => {
    let cancelled = false;
    try {
      fetch(`${API_BASE}/cases`)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then((data) => {
          if (cancelled) return;
          setCases(data.map(normalizeCase));
          setConnected(true);
          setLoading(false);
        })
        .catch(() => {
          if (cancelled) return;
          setConnected(false);
          setLoading(false);
        });
    } catch (err) {
      // 有些預覽環境的沙盒會直接擋下對外 fetch，這裡確保不會讓整個畫面掛掉
      setConnected(false);
      setLoading(false);
    }
    return () => { cancelled = true; };
  }, []);

  const pending = cases.filter((c) => c.status === "unassigned");
  const processing = cases.filter((c) => ["dispatched", "processing", "pending_payment"].includes(c.status));
  const done = cases.filter((c) => c.status === "completed");

  function updateCase(case_id, updater) {
    setCases((prev) => prev.map((c) => (c.case_id === case_id ? updater(c) : c)));
    setSelected((prev) => (prev && prev.case_id === case_id ? updater(prev) : prev));
  }

  function handleReview(case_id, detection_id, newState) {
    if (connected && (newState === "confirmed" || newState === "rejected")) {
      fetch(`${API_BASE}/cases/${case_id}/detections/${detection_id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result: newState }),
      })
        .then((res) => {
          if (!res.ok) return res.json().then((body) => { throw new Error(body.detail || `HTTP ${res.status}`); });
          return res.json();
        })
        .then((updated) => updateCase(case_id, (c) => normalizeAndKeepDecor(c, updated)))
        .catch((err) => notifyError("審核", err));
      return;
    }
    alert("審核失敗：後端尚未連線，或此審核結果尚未支援");
  }

  const TRANSITION_ENDPOINT = {
    dispatch: (id) => `${API_BASE}/cases/${id}/dispatch`,
    start: (id) => `${API_BASE}/cases/${id}/start-processing`,
    finish: (id) => `${API_BASE}/cases/${id}/finish-processing`,
    pay: (id) => `${API_BASE}/cases/${id}/confirm-payment`,
  };

  function handleTransition(case_id) {
    const current = cases.find((c) => c.case_id === case_id);
    const action = current && nextAction(current.status);
    if (connected && action) {
      fetch(TRANSITION_ENDPOINT[action.key](case_id), { method: "POST" })
        .then((res) => {
          if (!res.ok) return res.json().then((body) => { throw new Error(body.detail || `HTTP ${res.status}`); });
          return res.json();
        })
        .then((updated) => updateCase(case_id, (c) => normalizeAndKeepDecor(c, updated)))
        .catch((err) => notifyError("操作", err));
      return;
    }
    alert("操作失敗：後端尚未連線");
  }

  function normalizeAndKeepDecor(oldCase, updatedFromApi) {
    // API 回傳的 Case 沒有 plate/out/in/borrower，沿用原本畫面上顯示的那些
    const { plate, out, in: inTime, borrower } = oldCase;
    return { plate, out, in: inTime, borrower, ...updatedFromApi };
  }

  // complete_without_action()：案件根本沒有需要處理的內容，直接結案
  function handleCompleteWithoutAction(case_id) {
    if (connected) {
      fetch(`${API_BASE}/cases/${case_id}/complete-without-action`, { method: "POST" })
        .then((res) => {
          if (!res.ok) return res.json().then((body) => { throw new Error(body.detail || `HTTP ${res.status}`); });
          return res.json();
        })
        .then((updated) => updateCase(case_id, (c) => normalizeAndKeepDecor(c, updated)))
        .catch((err) => notifyError("結案", err));
      return;
    }
    alert("結案失敗：後端尚未連線");
  }

  // 顧客認為 AI 判斷有誤：對應真後端的 appeal_detection()。
  // 注意：appeal 不會改變 Case 的 status，只會把該 Detection 退回 needs_review 並重算 priority_score。
  function handleDispute(case_id, detection_id) {
    if (connected) {
      fetch(`${API_BASE}/cases/${case_id}/detections/${detection_id}/appeal`, { method: "POST" })
        .then((res) => {
          if (!res.ok) return res.json().then((body) => { throw new Error(body.detail || `HTTP ${res.status}`); });
          return res.json();
        })
        .then((updated) => updateCase(case_id, (c) => normalizeAndKeepDecor(c, updated)))
        .catch((err) => notifyError("申訴", err));
      return;
    }
    alert("申訴失敗：後端尚未連線");
  }

  // 修正審核：人工調整 AI 判讀的損傷類型／嚴重程度，對應 POST /cases/{id}/detections/{id}/review（result: corrected）。
  // 回傳 Promise<boolean>：成功才讓畫面離開修正狀態，失敗時保留使用者已經選好的內容。
  function handleCorrection(case_id, detection_id, { category, severity }) {
    if (!connected) {
      alert("修正失敗：後端尚未連線");
      return Promise.resolve(false);
    }
    return fetch(`${API_BASE}/cases/${case_id}/detections/${detection_id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result: "corrected", reviewed_category: category, reviewed_severity: severity }),
    })
      .then((res) => {
        if (!res.ok) return res.json().then((body) => { throw new Error(body.detail || `HTTP ${res.status}`); });
        return res.json();
      })
      .then((updated) => {
        updateCase(case_id, (c) => normalizeAndKeepDecor(c, updated));
        return true;
      })
      .catch((err) => { notifyError("修正", err); return false; });
  }

  // 設定付款金額：對應 PUT /cases/{id}/payment（body: { amount: 整數 }），後端只允許在未派工／已派工／處理中修改。
  function handleSetPayment(case_id, amount) {
    if (!connected) {
      alert("設定金額失敗：後端尚未連線");
      return Promise.resolve(false);
    }
    return fetch(`${API_BASE}/cases/${case_id}/payment`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount }),
    })
      .then((res) => {
        if (!res.ok) return res.json().then((body) => { throw new Error(body.detail || `HTTP ${res.status}`); });
        return res.json();
      })
      .then((updated) => {
        updateCase(case_id, (c) => normalizeAndKeepDecor(c, updated));
        return true;
      })
      .catch((err) => { notifyError("設定金額", err); return false; });
  }

  // 新增案件：對應 POST /cases，可以一次帶多筆判讀（detections）。
  // 回傳 { ok, error? }，由表單自己決定要不要關閉、要不要保留輸入內容。
  function handleCreateCase(payload, decor) {
    if (!connected) {
      return Promise.resolve({ ok: false, error: "新增案件失敗：後端尚未連線" });
    }
    return fetch(`${API_BASE}/cases`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          if (res.status === 409) return { ok: false, error: "案件編號已存在，請換一個。" };
          const detail = typeof body.detail === "string" ? body.detail : "請確認欄位內容是否正確。";
          return { ok: false, error: `新增案件失敗：${detail}` };
        }
        const created = await res.json();
        setCases((prev) => [{ out: "—", in: "—", ...decor, ...created }, ...prev]);
        return { ok: true };
      })
      .catch((err) => {
        console.error("新增案件失敗：", err);
        return { ok: false, error: "新增案件失敗，請確認後端是否正常運作。" };
      });
  }

  const tabs = [
    { key: "pending", label: "待處理案件", count: pending.length },
    { key: "processing", label: "處理中案件", count: processing.length },
    { key: "done", label: "已處理案件", count: done.length },
  ];

  return (
    <div className="app-root">
      <style>{`
        .app-root{
          --bg-page:#EFEEE5; --surface-light:#E2E1D5; --surface-light-2:#EAE9DE;
          --surface-dark:#12201A; --surface-dark-2:#1A2C22;
          --accent-lime:#AEDB3C; --accent-lime-soft:#DCEAB0; --accent-lime-deep:#3D5417;
          --text-dark:#1A1E16; --text-muted:#5C6055; --text-onDark:#F4F6EC; --text-onDark-muted:#9FAC94;
          --border-hair:rgba(20,34,25,0.14); --border-hair-dark:rgba(244,246,236,0.12);
          --amber:#D69A3B; --amber-soft:#F2E2BE; --red-soft:#E9C6BC; --red-deep:#8A3F27;
          font-family:'Noto Sans TC', sans-serif; background:var(--bg-page); color:var(--text-dark); min-height:100vh;
        }
        .app-root *{box-sizing:border-box;}
        .app-root header{background:var(--surface-dark);color:var(--text-onDark);padding:18px 28px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border-hair-dark);}
        .brand{display:flex;align-items:center;gap:12px;}
        .brand-mark{width:34px;height:34px;border-radius:10px;background:var(--accent-lime);display:flex;align-items:center;justify-content:center;}
        .brand-mark svg{width:18px;height:18px;stroke:var(--surface-dark);}
        .brand-text{font-weight:700;font-size:16px;}
        .brand-sub{font-size:12px;color:var(--text-onDark-muted);margin-top:1px;}
        .header-right{display:flex;align-items:center;gap:18px;font-size:13px;color:var(--text-onDark-muted);}
        .avatar{width:32px;height:32px;border-radius:50%;background:var(--surface-dark-2);border:1px solid var(--border-hair-dark);display:flex;align-items:center;justify-content:center;color:var(--text-onDark);font-size:13px;font-weight:600;}
        .main{max-width:1240px;margin:0 auto;padding:28px 32px 80px;}
        .page-head{margin-bottom:22px;}
        .page-head h1{font-size:19px;font-weight:800;margin:0 0 5px;}
        .page-head p{font-size:13px;color:var(--text-muted);margin:0;}
        .tabs{display:flex;gap:8px;margin-bottom:20px;}
        .tab{font-size:13px;font-weight:600;padding:9px 18px;border-radius:100px;background:var(--surface-light);color:var(--text-muted);cursor:pointer;border:none;display:flex;align-items:center;gap:8px;font-family:inherit;}
        .tab .count{font-size:11px;font-weight:700;background:rgba(0,0,0,0.06);padding:1px 7px;border-radius:100px;}
        .tab.active{background:var(--surface-dark);color:var(--text-onDark);}
        .tab.active .count{background:rgba(255,255,255,0.14);}
        .gap-note{background:var(--amber-soft);color:#6B4A12;font-size:12px;line-height:1.6;padding:12px 16px;border-radius:12px;margin-bottom:16px;}
        .conn-banner{font-size:12.5px;font-weight:600;padding:10px 16px;border-radius:12px;margin-bottom:18px;}
        .conn-ok{background:var(--accent-lime-soft);color:var(--accent-lime-deep);}
        .conn-off{background:var(--amber-soft);color:#6B4A12;}
        .table-card{background:var(--surface-light-2);border-radius:20px;padding:6px 6px 14px;}
        table{width:100%;border-collapse:collapse;}
        thead th{text-align:left;font-size:11.5px;font-weight:700;color:var(--text-muted);padding:16px 14px 10px;white-space:nowrap;}
        tbody tr{cursor:pointer;transition:background .12s;}
        tbody tr:hover{background:rgba(20,34,25,0.05);}
        tbody td{padding:12px 14px;font-size:13px;border-top:1px solid var(--border-hair);white-space:nowrap;}
        .plate{font-weight:700;letter-spacing:0.3px;}
        .thumb{width:36px;height:36px;border-radius:9px;background:linear-gradient(135deg,#D6D5C8,#C7C6B7);display:flex;align-items:center;justify-content:center;}
        .thumb svg{width:16px;height:16px;stroke:#8A8C7D;}
        .pill{font-size:11.5px;font-weight:600;padding:4px 10px;border-radius:100px;display:inline-block;}
        .pill-amber{background:var(--amber-soft);color:#6B4A12;}
        .pill-lime{background:var(--accent-lime-soft);color:var(--accent-lime-deep);}
        .pill-red{background:var(--red-soft);color:var(--red-deep);}
        .pill-neutral{background:rgba(20,34,25,0.08);color:var(--text-muted);}
        .proc-list{display:flex;flex-direction:column;gap:12px;}
        .proc-card{background:var(--surface-light-2);border-radius:20px;padding:18px 22px;cursor:pointer;}
        .proc-top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;}
        .proc-title{font-size:14.5px;font-weight:700;}
        .proc-sub{font-size:12px;color:var(--text-muted);margin-top:2px;}
        .stepper{display:flex;align-items:center;}
        .step{display:flex;flex-direction:column;align-items:center;gap:8px;flex:1;position:relative;}
        .step-dot{width:12px;height:12px;border-radius:50%;background:var(--border-hair);z-index:1;}
        .step.done .step-dot{background:var(--accent-lime);}
        .step.current .step-dot{background:var(--surface-dark);width:14px;height:14px;box-shadow:0 0 0 4px var(--accent-lime-soft);}
        .step-label{font-size:11px;color:var(--text-muted);text-align:center;}
        .step.current .step-label{color:var(--text-dark);font-weight:700;}
        .step-line{position:absolute;top:6px;left:-50%;width:100%;height:2px;background:var(--border-hair);z-index:0;}
        .step.done .step-line{background:var(--accent-lime);}
        .step:first-child .step-line{display:none;}
        .backdrop{position:fixed;inset:0;background:rgba(18,32,26,0.35);z-index:10;}
        .drawer{position:fixed;top:0;right:0;height:100%;width:460px;max-width:92vw;background:var(--bg-page);box-shadow:-8px 0 30px rgba(0,0,0,0.15);z-index:11;overflow-y:auto;padding:26px 26px 40px;}
        .drawer-close{width:30px;height:30px;border-radius:50%;background:var(--surface-light);display:flex;align-items:center;justify-content:center;cursor:pointer;margin-bottom:18px;}
        .drawer-close svg{width:14px;height:14px;stroke:var(--text-dark);}
        .drawer h2{font-size:18px;font-weight:800;margin:0 0 4px;}
        .drawer .sub{font-size:12.5px;color:var(--text-muted);margin-bottom:22px;}
        .section-label{font-size:12.5px;font-weight:700;margin:0 0 10px;}
        .photo-gallery{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:22px;}
        .photo-tile{display:flex;flex-direction:column;gap:6px;}
        .photo-tile-frame{position:relative;aspect-ratio:1/1;border-radius:10px;background:linear-gradient(135deg,#D6D5C8,#C7C6B7);display:flex;align-items:center;justify-content:center;}
        .photo-tile-frame svg{width:22px;height:22px;stroke:#8A8C7D;opacity:0.7;}
        .photo-tile.flagged .photo-tile-frame{box-shadow:0 0 0 2.5px var(--red-deep);}
        .photo-tile.rejected .photo-tile-frame{outline:2px dashed var(--text-muted);outline-offset:2px;opacity:0.65;}
        .photo-tile-label{font-size:10.5px;color:var(--text-muted);text-align:center;}
        .photo-tile.flagged .photo-tile-label{color:var(--red-deep);font-weight:700;}
        .photo-tile.rejected .photo-tile-label{color:var(--text-muted);text-decoration:line-through;}
        .flag-badge{position:absolute;top:3px;right:3px;font-size:9px;font-weight:700;padding:2px 5px;border-radius:6px;line-height:1.3;}
        .photo-tile.editable{cursor:pointer;}
        .photo-tile.editable .photo-tile-frame{transition:transform .1s;}
        .photo-tile.editable:hover .photo-tile-frame{transform:scale(1.04);}
        .compare{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:22px;}
        .photo-block{background:var(--surface-light);border-radius:16px;padding:12px;}
        .photo-block-head{display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:8px;color:var(--text-muted);}
        .photo-frame{aspect-ratio:4/3;border-radius:11px;background:linear-gradient(135deg,#D6D5C8,#C7C6B7);display:flex;align-items:center;justify-content:center;position:relative;}
        .photo-frame svg{width:34px;height:34px;stroke:#8A8C7D;opacity:0.7;}
        .flag-dot{position:absolute;width:12px;height:12px;border-radius:50%;background:var(--amber);border:2px solid #FFF8E8;}
        .diff-chip{display:inline-flex;align-items:center;gap:7px;background:var(--surface-light);border-radius:100px;padding:7px 13px 7px 9px;font-size:12px;margin-bottom:6px;}
        .diff-chip .dot{width:7px;height:7px;border-radius:50%;background:var(--amber);}
        .diff-chip b{font-weight:700;}
        .diff-chip .conf-text{color:var(--text-muted);font-weight:400;}
        .checklist{background:var(--surface-dark);color:var(--text-onDark);border-radius:18px;padding:18px 20px;margin:16px 0 22px;}
        .checklist .section-label{color:var(--text-onDark);}
        .check-row{display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border-hair-dark);font-size:12.5px;}
        .check-row:last-child{border-bottom:none;padding-bottom:0;}
        .check-row:first-child{padding-top:0;}
        .actions{display:flex;flex-wrap:wrap;gap:10px;}
        .btn{border:none;border-radius:100px;padding:11px 18px;font-family:inherit;font-size:13px;font-weight:600;cursor:pointer;}
        .btn:disabled{cursor:not-allowed;opacity:.55;}
        .btn-primary{background:var(--surface-dark);color:var(--text-onDark);}
        .btn-secondary{background:var(--surface-light);color:var(--text-dark);}
        .btn-ghost{background:transparent;color:var(--text-muted);border:1px solid var(--border-hair);}
        .orig-note{font-size:11.5px;color:var(--text-muted);margin:2px 0 4px 4px;}
        .edit-fields{display:flex;gap:10px;margin-bottom:8px;}
        .edit-field{flex:1;display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--text-muted);font-weight:600;}
        .edit-field select{font-family:inherit;font-size:13px;padding:8px 10px;border-radius:10px;border:1px solid var(--border-hair);background:var(--surface-light-2);color:var(--text-dark);}
        .form-error{background:var(--red-soft);color:var(--red-deep);font-size:12.5px;font-weight:600;line-height:1.6;padding:10px 14px;border-radius:12px;margin-bottom:12px;}
        .check-row.pay-row{border-bottom:none;padding-bottom:0;}
        .pay-view{display:inline-flex;align-items:center;}
        .pay-edit{display:inline-flex;align-items:center;gap:6px;}
        .pay-prefix{color:var(--text-onDark-muted);font-size:12px;}
        .pay-input{width:104px;font-family:inherit;font-size:13px;padding:6px 10px;border-radius:8px;border:1px solid var(--border-hair-dark);background:rgba(244,246,236,0.08);color:var(--text-onDark);}
        .pay-input:focus{outline:2px solid var(--accent-lime);outline-offset:1px;}
        .pay-btn{border:none;border-radius:100px;padding:5px 12px;font-family:inherit;font-size:12px;font-weight:600;cursor:pointer;background:var(--accent-lime);color:var(--surface-dark);}
        .pay-btn:disabled{opacity:0.5;cursor:default;}
        .pay-btn-ghost{background:transparent;color:var(--text-onDark-muted);border:1px solid var(--border-hair-dark);}
        .pay-link{background:none;border:none;margin-left:10px;padding:0;font-family:inherit;font-size:12px;font-weight:600;color:var(--accent-lime);text-decoration:underline;cursor:pointer;}
        .pay-hint{font-size:11.5px;line-height:1.6;color:var(--text-onDark-muted);padding-top:8px;}
        .pay-error{font-size:12px;line-height:1.6;color:#F2B8A2;padding-top:8px;}
        .tabs-row{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px;}
        .tabs-row .tabs{margin-bottom:0;}
        .new-case-modal{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);width:640px;max-width:92vw;max-height:86vh;overflow-y:auto;background:var(--bg-page);border-radius:24px;box-shadow:0 20px 60px rgba(0,0,0,0.25);z-index:12;padding:26px 30px 30px;}
        .new-case-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;}
        .new-case-head h2{font-size:18px;font-weight:800;margin:0;}
        .form-row-group{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;}
        .det-row{display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr auto;gap:10px;align-items:end;background:var(--surface-light-2);border-radius:14px;padding:12px;margin-bottom:10px;}
        .edit-field input{font-family:inherit;font-size:13px;padding:8px 10px;border-radius:10px;border:1px solid var(--border-hair);background:var(--surface-light-2);color:var(--text-dark);}
        .det-row .edit-field input, .det-row .edit-field select{background:var(--bg-page);}
        .btn-row-remove{padding:8px 12px;height:fit-content;}
      `}</style>

      <Header pendingCount={pending.length} />

      <div className="main">
        <div className="page-head">
          <h1>案件佇列</h1>
          <p>待人工覆核的案件也會計算優先度分數（方便依優先度排審核順序），只有標為「車體無問題」的判斷不計分。</p>
        </div>

        {!loading && (
          <div className={connected ? "conn-banner conn-ok" : "conn-banner conn-off"}>
            {connected
              ? `已連線到後端 ${API_BASE}，資料為即時 /cases 內容。`
              : `無法連線到 ${API_BASE}（後端可能沒有啟動），目前沒有載入任何案件。`}
          </div>
        )}

        <div className="tabs-row">
          <div className="tabs">
            {tabs.map((t) => (
              <button key={t.key} className={`tab ${activeTab === t.key ? "active" : ""}`} onClick={() => setActiveTab(t.key)}>
                {t.label} <span className="count">{t.count}</span>
              </button>
            ))}
          </div>
          <button className="btn btn-primary" onClick={() => setShowNewCase(true)}>+ 新增案件</button>
        </div>

        {activeTab === "pending" && <PendingTable cases={pending} onOpen={setSelected} />}
        {activeTab === "processing" && <ProcessingList cases={processing} onOpen={setSelected} />}
        {activeTab === "done" && <DoneTable cases={done} onOpen={setSelected} />}
      </div>

      <Drawer item={selected} onClose={() => setSelected(null)} onReview={handleReview} onTransition={handleTransition} onCompleteWithoutAction={handleCompleteWithoutAction} onDispute={handleDispute} onCorrect={handleCorrection} onSetPayment={handleSetPayment} connected={connected} />
      {showNewCase && <NewCaseForm onClose={() => setShowNewCase(false)} onCreate={handleCreateCase} />}
    </div>
  );
}
