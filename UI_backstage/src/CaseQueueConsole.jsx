import { useState, useEffect } from "react";

const API_BASE = "http://127.0.0.1:8000";

const CATEGORY_LABEL = { scratch: "刮痕", collision_damage: "碰撞損傷", cleanliness: "清潔／汙損" };
const SEVERITY_LABEL = { minor: "輕微", moderate: "中等", severe: "嚴重" };
const REVIEW_LABEL = { needs_review: "待人工覆核", auto_accepted: "AI自動通過", confirmed: "已確認", rejected: "已退回", corrected: "已修正" };
const STATUS_LABEL = { unassigned: "未派工", dispatched: "已派工", processing: "處理中", pending_payment: "待付款", completed: "已結案" };
const STATUS_ORDER = ["unassigned", "dispatched", "processing", "pending_payment", "completed"];

// 對應優先度表（白板版本）
const PRIORITY_TABLE = {
  scratch: { minor: 20, moderate: 45, severe: 70 },
  collision_damage: { minor: 50, moderate: 75, severe: 95 },
  cleanliness: { minor: 10, moderate: 35, severe: 60 },
};
const ACTIONABLE = new Set(["auto_accepted", "confirmed", "corrected"]);
function calcPriority(detections) {
  const usable = detections.filter((d) => ACTIONABLE.has(d.review_state));
  if (usable.length === 0) return null;
  return Math.max(...usable.map((d) => {
    const cat = d.review_state === "corrected" ? d.reviewed_category : d.category;
    const sev = d.review_state === "corrected" ? d.reviewed_severity : d.severity;
    return PRIORITY_TABLE[cat][sev];
  }));
}

const INITIAL_CASES = [
  // 顧客申訴案例：AI 原本判斷已經 auto_accepted，但顧客認為判斷有誤，退回未處理事件並特別標出
  {
    case_id: "CASE-3041", status: "unassigned", priority_score: null, payment_amount: 0, plate: "RST-7777", out: "09:00", in: "12:30", borrower: "顏先生 · Toyota Altis",
    detections: [{ detection_id: "DET-5999", borrow_photo_id: "borrow-299", return_photo_id: "return-299", category: "scratch", severity: "minor", confidence: 0.88, review_state: "needs_review", disputed: true }]
  },

  // 待處理（status: unassigned，還沒派工，通常還有 detection 待覆核）
  {
    case_id: "CASE-3042", status: "unassigned", priority_score: null, payment_amount: 0, plate: "ABC-1234", out: "09:10", in: "14:20", borrower: "林先生 · Toyota Corolla",
    detections: [{ detection_id: "DET-6001", borrow_photo_id: "borrow-301", return_photo_id: "return-301", category: "scratch", severity: "moderate", confidence: 0.42, review_state: "needs_review" }]
  },
  {
    case_id: "CASE-3043", status: "unassigned", priority_score: null, payment_amount: 0, plate: "EFG-5678", out: "08:30", in: "13:00", borrower: "黃小姐 · Honda Fit",
    detections: [{ detection_id: "DET-6002", borrow_photo_id: "borrow-302", return_photo_id: "return-302", category: "cleanliness", severity: "minor", confidence: 0.44, review_state: "rejected" }]
  },
  {
    case_id: "CASE-3044", status: "unassigned", priority_score: null, payment_amount: 0, plate: "HJK-9012", out: "07:50", in: "12:10", borrower: "吳先生 · Nissan Kicks",
    detections: [{ detection_id: "DET-6003", borrow_photo_id: "borrow-303", return_photo_id: "return-303", category: "collision_damage", severity: "moderate", confidence: 0.55, review_state: "needs_review" }]
  },
  {
    case_id: "CASE-3045", status: "unassigned", priority_score: null, payment_amount: 0, plate: "LMN-3456", out: "09:40", in: "11:30", borrower: "張小姐 · Toyota Yaris",
    detections: [{ detection_id: "DET-6004", borrow_photo_id: "borrow-304", return_photo_id: "return-304", category: "cleanliness", severity: "severe", confidence: 0.38, review_state: "needs_review" }]
  },
  {
    case_id: "CASE-3046", status: "unassigned", priority_score: null, payment_amount: 0, plate: "PQR-7890", out: "10:05", in: "13:45", borrower: "王先生 · Mazda 3",
    detections: [{ detection_id: "DET-6005", borrow_photo_id: "borrow-305", return_photo_id: "return-305", category: "scratch", severity: "minor", confidence: 0.63, review_state: "needs_review" }]
  },

  // 處理中（status: dispatched / processing / pending_payment）
  {
    case_id: "CASE-3038", status: "dispatched", priority_score: 75, payment_amount: 0, plate: "STU-9990", out: "—", in: "—", borrower: "王先生 · Mazda 3",
    detections: [{ detection_id: "DET-5998", borrow_photo_id: "borrow-290", return_photo_id: "return-290", category: "collision_damage", severity: "moderate", confidence: 0.74, review_state: "confirmed" }]
  },
  {
    case_id: "CASE-3035", status: "processing", priority_score: 60, payment_amount: 0, plate: "KLM-4521", out: "—", in: "—", borrower: "林小姐 · Honda Fit",
    detections: [{ detection_id: "DET-5990", borrow_photo_id: "borrow-280", return_photo_id: "return-280", category: "cleanliness", severity: "severe", confidence: 0.69, review_state: "confirmed" }]
  },
  {
    case_id: "CASE-3030", status: "pending_payment", priority_score: 45, payment_amount: 2400, plate: "XYZ-1123", out: "—", in: "—", borrower: "陳先生 · Toyota Yaris",
    detections: [{ detection_id: "DET-5980", borrow_photo_id: "borrow-270", return_photo_id: "return-270", category: "scratch", severity: "moderate", confidence: 0.71, review_state: "confirmed" }]
  },

  // 已處理（status: completed）
  {
    case_id: "CASE-3020", status: "completed", priority_score: 10, payment_amount: 0, plate: "STU-2345", out: "08:00", in: "10:20", borrower: "李小姐",
    detections: [{ detection_id: "DET-5900", borrow_photo_id: "borrow-200", return_photo_id: "return-200", category: "cleanliness", severity: "minor", confidence: 0.88, review_state: "auto_accepted" }]
  },
  {
    case_id: "CASE-3015", status: "completed", priority_score: 20, payment_amount: 0, plate: "VWX-6789", out: "07:15", in: "09:40", borrower: "周先生",
    detections: [{ detection_id: "DET-5895", borrow_photo_id: "borrow-195", return_photo_id: "return-195", category: "scratch", severity: "minor", confidence: 0.95, review_state: "auto_accepted" }]
  },
  {
    case_id: "CASE-3010", status: "completed", priority_score: 95, payment_amount: 1800, plate: "YZA-0123", out: "06:50", in: "09:00", borrower: "蔡小姐",
    detections: [{ detection_id: "DET-5890", borrow_photo_id: "borrow-190", return_photo_id: "return-190", category: "collision_damage", severity: "severe", confidence: 0.79, review_state: "confirmed" }]
  },
];

function confClass(c) { return c >= 0.7 ? "conf-high" : c >= 0.5 ? "conf-mid" : "conf-low"; }
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
          <tr><th>處理狀態</th><th>車牌號碼</th><th>借車時間</th><th>還車時間</th><th>借車前照片</th><th>借車後照片</th><th>借車人</th><th>AI信心程度</th><th>優先級</th></tr>
        </thead>
        <tbody>
          {cases.map((c) => {
            const d = c.detections[0];
            return (
              <tr key={c.case_id} className={d.disputed ? "disputed-row" : ""} onClick={() => onOpen(c)}>
                <td>
                  <span className={`pill ${reviewPillClass(d.review_state)}`}>{REVIEW_LABEL[d.review_state]}</span>
                  {d.disputed && <span className="pill pill-dispute" style={{ marginLeft: 6 }}>顧客申訴</span>}
                </td>
                <td className="plate">{c.plate}</td>
                <td>{c.out}</td>
                <td>{c.in}</td>
                <td><CarThumb /></td>
                <td><CarThumb /></td>
                <td>{c.borrower.split(" · ")[0]}</td>
                <td className={`conf ${confClass(d.confidence)}`}>{(d.confidence * 100).toFixed(0)}%</td>
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
        return (
          <div className="proc-card" key={c.case_id} onClick={() => onOpen(c)}>
            <div className="proc-top">
              <div>
                <div className="proc-title">{c.case_id} · {c.borrower}</div>
                <div className="proc-sub">車牌 {c.plate} · {CATEGORY_LABEL[c.detections[0].category]}・{SEVERITY_LABEL[c.detections[0].severity]} · priority_score {c.priority_score}</div>
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
          <tr><th>處理紀錄</th><th>車牌號碼</th><th>借車時間</th><th>還車時間</th><th>借車前照片</th><th>借車後照片</th><th>借車人</th><th>付款狀態</th><th>AI信心程度</th></tr>
        </thead>
        <tbody>
          {cases.map((c) => {
            const d = c.detections[0];
            return (
              <tr key={c.case_id} onClick={() => onOpen(c)}>
                <td><span className="pill pill-neutral">{REVIEW_LABEL[d.review_state]} → 已結案</span></td>
                <td className="plate">{c.plate}</td>
                <td>{c.out}</td>
                <td>{c.in}</td>
                <td><CarThumb /></td>
                <td><CarThumb /></td>
                <td>{c.borrower}</td>
                <td><span className={`pill ${c.payment_amount > 0 ? "pill-lime" : "pill-neutral"}`}>{c.payment_amount > 0 ? `已收款 NT$${c.payment_amount}` : "無需收款"}</span></td>
                <td className={`conf ${confClass(d.confidence)}`}>{(d.confidence * 100).toFixed(0)}%</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Drawer({ item, onClose, onReview, onTransition, onCompleteWithoutAction, onDispute }) {
  if (!item) return null;
  const d = item.detections[0];
  const action = nextAction(item.status);
  const noContentToHandle =
    (item.status === "unassigned" || item.status === "dispatched") &&
    item.payment_amount === 0 &&
    item.detections.every((det) => det.review_state === "rejected");
  return (
    <>
      <div className="backdrop show" onClick={onClose}></div>
      <div className="drawer show">
        <div className="drawer-close" onClick={onClose}>
          <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
        </div>
        <h2>{item.case_id} · {item.borrower}</h2>
        <div className="sub">車牌 {item.plate} · 借車 {item.out} → 還車 {item.in}</div>

        {d.disputed && (
          <div className="dispute-banner">顧客申訴：認為 AI 判斷有誤，案件已退回未處理事件，待人工複審</div>
        )}

        <div className="section-label">車況比對</div>
        <div className="compare">
          <div className="photo-block"><div className="photo-block-head"><span>借車拍攝</span><span>{item.out}</span></div><div className="photo-frame"><CarThumbBig /></div></div>
          <div className="photo-block"><div className="photo-block-head"><span>還車拍攝</span><span>{item.in}</span></div><div className="photo-frame"><CarThumbBig /><div className="flag-dot" style={{ top: "34%", left: "62%" }}></div></div></div>
        </div>

        <div className="section-label">AI 判讀（Detection）</div>
        <div className="diff-chip"><span className="dot"></span><b>{CATEGORY_LABEL[d.category]}</b><span className="conf-text">severity: {SEVERITY_LABEL[d.severity]}</span></div>
        <br />
        <div className="diff-chip"><span className="dot" style={{ background: "var(--text-muted)" }}></span><b>confidence</b><span className="conf-text">{d.confidence.toFixed(2)}</span></div>

        <div className="checklist">
          <div className="section-label">案件資訊（Case）</div>
          <div className="check-row"><span>priority_score</span><PriorityBadge score={item.priority_score} /></div>
          <div className="check-row"><span>review_state</span><span className={`pill ${reviewPillClass(d.review_state)}`}>{REVIEW_LABEL[d.review_state]}</span></div>
          <div className="check-row"><span>payment_amount</span><span>{item.payment_amount > 0 ? `NT$ ${item.payment_amount}` : "—"}</span></div>
        </div>

        <div className="section-label">操作</div>
        {connected && <div className="gap-note">目前後端只實作了「派工」，其餘操作先在前端模擬，不會真的送到後端。</div>}
        <div className="actions">
          {d.review_state === "needs_review" && (
            <>
              <button className="btn btn-primary" onClick={() => onReview(item.case_id, d.detection_id, "confirmed")}>確認</button>
              <button className="btn btn-secondary" onClick={() => onReview(item.case_id, d.detection_id, "corrected")}>修正</button>
              <button className="btn btn-ghost" onClick={() => onReview(item.case_id, d.detection_id, "rejected")}>否決</button>
            </>
          )}
          {action && !(action.key === "finish" && item.detections.some((det) => det.review_state === "needs_review")) && (
            <button className="btn btn-primary" onClick={() => onTransition(item.case_id)}>{action.label}</button>
          )}
          {noContentToHandle && (
            <button className="btn btn-ghost" onClick={() => onCompleteWithoutAction(item.case_id)}>無需處理／結案</button>
          )}
          {!d.disputed && (
            <button className="btn btn-ghost" onClick={() => onDispute(item.case_id, d.detection_id)}>模擬顧客申訴（AI判斷有誤）</button>
          )}
        </div>
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
  const [cases, setCases] = useState(INITIAL_CASES);
  const [selected, setSelected] = useState(null);
  const [connected, setConnected] = useState(null); // null = 還在檢查, true = 接上真後端, false = 用示範資料
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
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
    updateCase(case_id, (c) => ({ ...c, detections: c.detections.map((d) => (d.detection_id === detection_id ? { ...d, review_state: newState } : d)) }));
  }

  function handleTransition(case_id) {
    const current = cases.find((c) => c.case_id === case_id);
    // 真後端目前只做了 dispatch，接上時優先打真的 API
    if (connected && current && current.status === "unassigned") {
      fetch(`${API_BASE}/cases/${case_id}/dispatch`, { method: "POST" })
        .then((res) => {
          if (!res.ok) return res.json().then((body) => { throw new Error(body.detail || `HTTP ${res.status}`); });
          return res.json();
        })
        .then((updated) => updateCase(case_id, (c) => ({ ...c, ...normalizeAndKeepDecor(c, updated) })))
        .catch((err) => alert(`派工失敗：${err.message}`));
      return;
    }
    // start_processing / finish_processing / confirm_payment：後端還沒開放，先前端模擬
    updateCase(case_id, (c) => {
      let status = c.status;
      let priority_score = c.priority_score;
      if (status === "unassigned") { status = "dispatched"; priority_score = calcPriority(c.detections); }
      else if (status === "dispatched") status = "processing";
      else if (status === "processing") status = c.payment_amount > 0 ? "pending_payment" : "completed";
      else if (status === "pending_payment") status = "completed";
      return { ...c, status, priority_score };
    });
  }

  function normalizeAndKeepDecor(oldCase, updatedFromApi) {
    // API 回傳的 Case 沒有 plate/out/in/borrower，沿用原本畫面上顯示的那些
    const { plate, out, in: inTime, borrower } = oldCase;
    return { plate, out, in: inTime, borrower, ...updatedFromApi };
  }

  // complete_without_action()：案件根本沒有需要處理的內容，直接結案
  function handleCompleteWithoutAction(case_id) {
    updateCase(case_id, (c) => ({ ...c, status: "completed", priority_score: c.priority_score ?? 0 }));
  }

  // 顧客認為 AI 判斷有誤：案件退回未處理事件（unassigned），Detection 重新變成 needs_review，並標記 disputed
  function handleDispute(case_id, detection_id) {
    updateCase(case_id, (c) => ({
      ...c,
      status: "unassigned",
      detections: c.detections.map((d) => (d.detection_id === detection_id ? { ...d, review_state: "needs_review", disputed: true } : d)),
    }));
    setActiveTab("pending");
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
        .dispute-banner{background:var(--red-deep);color:#FBEAE3;font-size:12.5px;font-weight:600;line-height:1.6;padding:12px 16px;border-radius:12px;margin-bottom:18px;}
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
        .pill-dispute{background:var(--red-deep);color:#FBEAE3;font-weight:700;}
        tbody tr.disputed-row{background:rgba(138,63,39,0.07);box-shadow:inset 3px 0 0 var(--red-deep);}
        tbody tr.disputed-row:hover{background:rgba(138,63,39,0.13);}
        .conf{font-weight:700;}
        .conf-low{color:var(--red-deep);}
        .conf-mid{color:#6B4A12;}
        .conf-high{color:var(--accent-lime-deep);}
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
        .btn-primary{background:var(--surface-dark);color:var(--text-onDark);}
        .btn-secondary{background:var(--surface-light);color:var(--text-dark);}
        .btn-ghost{background:transparent;color:var(--text-muted);border:1px solid var(--border-hair);}
      `}</style>

      <Header pendingCount={pending.length} />

      <div className="main">
        <div className="page-head">
          <h1>案件佇列</h1>
          <p>review_state = needs_review 的案件進入待處理；priority_score 由 category × severity 計算，派工後才會產生。</p>
        </div>

        {!loading && (
          <div className={connected ? "conn-banner conn-ok" : "conn-banner conn-off"}>
            {connected
              ? `已連線到後端 ${API_BASE}，資料為即時 /cases 內容。`
              : `無法連線到 ${API_BASE}（後端可能沒有啟動），目前顯示示範資料。`}
          </div>
        )}

        <div className="tabs">
          {tabs.map((t) => (
            <button key={t.key} className={`tab ${activeTab === t.key ? "active" : ""}`} onClick={() => setActiveTab(t.key)}>
              {t.label} <span className="count">{t.count}</span>
            </button>
          ))}
        </div>

        {activeTab === "pending" && <PendingTable cases={pending} onOpen={setSelected} />}
        {activeTab === "processing" && <ProcessingList cases={processing} onOpen={setSelected} />}
        {activeTab === "done" && <DoneTable cases={done} onOpen={setSelected} />}
      </div>

      <Drawer item={selected} onClose={() => setSelected(null)} onReview={handleReview} onTransition={handleTransition} onCompleteWithoutAction={handleCompleteWithoutAction} onDispute={handleDispute} />
    </div>
  );
}
