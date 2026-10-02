import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.jsx";

const API_BASE = "http://127.0.0.1:8000";

const detection = {
  detection_id: "det-1",
  borrow_photo_id: null,
  return_photo_id: "return-1",
  source_photo_id: "return-1",
  category: "scratch",
  severity: "minor",
  confidence: 0.42,
  review_state: "needs_review",
  reviewed_category: null,
  reviewed_severity: null,
  review_note: null,
};

function caseData(overrides = {}) {
  return {
    case_id: "case-1",
    detections: [detection],
    priority_score: 20,
    status: "unassigned",
    payment_amount: 0,
    ...overrides,
  };
}

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(body),
  };
}

async function renderCases(cases) {
  global.fetch.mockResolvedValueOnce(jsonResponse(cases));
  render(<App />);
  await screen.findByText(/已連線到後端/);
}

function openPendingRow() {
  const row = screen.getAllByRole("row")[1];
  expect(row).not.toBeNull();
  fireEvent.click(row);
}

function openProcessingCase(caseId) {
  fireEvent.click(screen.getByRole("button", { name: /處理中案件/ }));
  const card = screen.getByText(new RegExp(`${caseId} ·`)).closest(".proc-card");
  expect(card).not.toBeNull();
  fireEvent.click(card);
}

describe("production backstage console", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
    window.alert = vi.fn();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders the real Case list returned by Module E", async () => {
    await renderCases([caseData()]);

    expect(global.fetch).toHaveBeenCalledWith(`${API_BASE}/cases`);
    expect(screen.getByText("待人工覆核")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
    expect(screen.queryByText("AI信心程度")).not.toBeInTheDocument();

    openPendingRow();
    expect(screen.getByRole("heading", { name: /case-1/ })).toBeInTheDocument();
  });

  it("renders and opens a Case with zero detections", async () => {
    await renderCases([caseData({ case_id: "case-empty", detections: [], priority_score: null })]);

    expect(screen.getByText("無判讀結果")).toBeInTheDocument();
    openPendingRow();
    expect(screen.getByRole("heading", { name: /case-empty/ })).toBeInTheDocument();
    expect(screen.getByText(/此案件沒有判讀結果/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "派工" })).toBeInTheDocument();
  });

  it("dispatches through Module E and applies only the returned Case", async () => {
    const original = caseData({ detections: [{ ...detection, review_state: "auto_accepted" }] });
    const dispatched = { ...original, status: "dispatched" };
    await renderCases([original]);
    global.fetch.mockResolvedValueOnce(jsonResponse(dispatched));

    openPendingRow();
    fireEvent.click(screen.getByRole("button", { name: "派工" }));

    await waitFor(() => expect(global.fetch).toHaveBeenLastCalledWith(
      `${API_BASE}/cases/case-1/dispatch`,
      { method: "POST" },
    ));
    expect(await screen.findByRole("button", { name: "開始處理" })).toBeInTheDocument();
  });

  it("submits confirmed review to Module E", async () => {
    const reviewed = caseData({
      detections: [{ ...detection, review_state: "confirmed" }],
    });
    await renderCases([caseData()]);
    global.fetch.mockResolvedValueOnce(jsonResponse(reviewed));

    openPendingRow();
    fireEvent.click(screen.getByRole("button", { name: "確認" }));

    await waitFor(() => expect(global.fetch).toHaveBeenLastCalledWith(
      `${API_BASE}/cases/case-1/detections/det-1/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result: "confirmed" }),
      },
    ));
    expect((await screen.findAllByText("已確認")).length).toBeGreaterThan(0);
  });

  it("submits rejected review to Module E", async () => {
    const reviewed = caseData({
      detections: [{ ...detection, review_state: "rejected" }],
      priority_score: null,
    });
    await renderCases([caseData()]);
    global.fetch.mockResolvedValueOnce(jsonResponse(reviewed));

    openPendingRow();
    fireEvent.click(screen.getByRole("button", { name: "車體無問題" }));

    await waitFor(() => expect(global.fetch).toHaveBeenLastCalledWith(
      `${API_BASE}/cases/case-1/detections/det-1/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result: "rejected" }),
      },
    ));
    expect((await screen.findAllByText("車體無問題")).length).toBeGreaterThan(0);
  });

  it("reopens a Detection through the appeal endpoint", async () => {
    const acceptedDetection = { ...detection, review_state: "auto_accepted" };
    const original = caseData({ detections: [acceptedDetection] });
    const appealed = caseData({ detections: [{ ...acceptedDetection, review_state: "needs_review" }] });
    await renderCases([original]);
    global.fetch.mockResolvedValueOnce(jsonResponse(appealed));

    openPendingRow();
    fireEvent.click(screen.getByRole("button", { name: "顧客申訴（重新審核）" }));

    await waitFor(() => expect(global.fetch).toHaveBeenLastCalledWith(
      `${API_BASE}/cases/case-1/detections/det-1/appeal`,
      { method: "POST" },
    ));
    expect((await screen.findAllByText("待人工覆核")).length).toBeGreaterThan(0);
  });

  it("completes an empty Case through the no-action endpoint", async () => {
    const empty = caseData({ detections: [], priority_score: null });
    const completed = { ...empty, status: "completed" };
    await renderCases([empty]);
    global.fetch.mockResolvedValueOnce(jsonResponse(completed));

    openPendingRow();
    fireEvent.click(screen.getByRole("button", { name: "無需處理／結案" }));

    await waitFor(() => expect(global.fetch).toHaveBeenLastCalledWith(
      `${API_BASE}/cases/case-1/complete-without-action`,
      { method: "POST" },
    ));
    expect(screen.getByRole("button", { name: /已處理案件/ })).toHaveTextContent("1");
  });

  it("starts processing through the workflow endpoint", async () => {
    const dispatched = caseData({ status: "dispatched" });
    const processing = { ...dispatched, status: "processing" };
    await renderCases([dispatched]);
    global.fetch.mockResolvedValueOnce(jsonResponse(processing));

    openProcessingCase("case-1");
    fireEvent.click(screen.getByRole("button", { name: "開始處理" }));

    await waitFor(() => expect(global.fetch).toHaveBeenLastCalledWith(
      `${API_BASE}/cases/case-1/start-processing`,
      { method: "POST" },
    ));
    expect((await screen.findAllByText("處理中")).length).toBeGreaterThan(0);
  });

  it("confirms payment through Module E", async () => {
    const pendingPayment = caseData({ status: "pending_payment", payment_amount: 2400 });
    const completed = { ...pendingPayment, status: "completed" };
    await renderCases([pendingPayment]);
    global.fetch.mockResolvedValueOnce(jsonResponse(completed));

    openProcessingCase("case-1");
    fireEvent.click(screen.getByRole("button", { name: "確認付款" }));

    await waitFor(() => expect(global.fetch).toHaveBeenLastCalledWith(
      `${API_BASE}/cases/case-1/confirm-payment`,
      { method: "POST" },
    ));
    expect(screen.getByRole("button", { name: /已處理案件/ })).toHaveTextContent("1");
    expect(screen.queryByRole("button", { name: "確認付款" })).not.toBeInTheDocument();
  });

  it("reports backend errors without fabricating a successful transition", async () => {
    const original = caseData({ detections: [{ ...detection, review_state: "auto_accepted" }] });
    await renderCases([original]);
    global.fetch.mockResolvedValueOnce(jsonResponse({ detail: "dispatch blocked" }, 409));

    openPendingRow();
    fireEvent.click(screen.getByRole("button", { name: "派工" }));

    await waitFor(() => expect(window.alert).toHaveBeenCalledWith("操作失敗，請確認案件目前的狀態後再試一次。"));
    expect(screen.getByRole("button", { name: "派工" })).toBeInTheDocument();
  });

  it("hides the AI confidence in the lists but shows it after opening a Case", async () => {
    await renderCases([caseData()]);

    expect(screen.queryByText("AI信心程度")).not.toBeInTheDocument();
    expect(screen.queryByText("0.42")).not.toBeInTheDocument();

    openPendingRow();
    expect(screen.getByText("信心度")).toBeInTheDocument();
    expect(screen.getByText("0.42")).toBeInTheDocument();
  });

  it("adjusts the AI judgement and submits a corrected review to Module E", async () => {
    const corrected = caseData({
      detections: [{ ...detection, review_state: "corrected", reviewed_category: "collision_damage", reviewed_severity: "minor" }],
      priority_score: 50,
    });
    await renderCases([caseData()]);
    global.fetch.mockResolvedValueOnce(jsonResponse(corrected));

    openPendingRow();
    fireEvent.click(screen.getByRole("button", { name: "修正" }));
    expect(screen.getByLabelText("損傷類型")).toHaveValue("scratch");
    expect(screen.getByLabelText("嚴重程度")).toHaveValue("minor");
    expect(screen.getByText(/AI 原判：刮痕・輕微/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("損傷類型"), { target: { value: "collision_damage" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存修正" }));

    await waitFor(() => expect(global.fetch).toHaveBeenLastCalledWith(
      `${API_BASE}/cases/case-1/detections/det-1/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result: "corrected", reviewed_category: "collision_damage", reviewed_severity: "minor" }),
      },
    ));
    expect(await screen.findByText(/AI 原判：刮痕・輕微（已由人工調整）/)).toBeInTheDocument();
    expect(screen.getByText("碰撞損傷")).toBeInTheDocument();
    expect(screen.queryByLabelText("損傷類型")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "修正" })).not.toBeInTheDocument();
  });

  it("does not submit a correction that keeps the AI category and severity", async () => {
    await renderCases([caseData()]);

    openPendingRow();
    fireEvent.click(screen.getByRole("button", { name: "修正" }));
    fireEvent.click(screen.getByRole("button", { name: "儲存修正" }));

    expect(screen.getByText(/至少要有一項和 AI 原判不同/)).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("損傷類型")).toBeInTheDocument();
  });

  it("keeps the correction draft when Module E rejects it", async () => {
    await renderCases([caseData()]);
    global.fetch.mockResolvedValueOnce(jsonResponse({ detail: "correction blocked" }, 409));

    openPendingRow();
    fireEvent.click(screen.getByRole("button", { name: "修正" }));
    fireEvent.change(screen.getByLabelText("嚴重程度"), { target: { value: "severe" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存修正" }));

    await waitFor(() => expect(window.alert).toHaveBeenCalledWith("修正失敗，請確認案件目前的狀態後再試一次。"));
    expect(screen.getByLabelText("嚴重程度")).toHaveValue("severe");
    expect(screen.getByRole("button", { name: "儲存修正" })).not.toBeDisabled();
  });

  it("only offers correction while a Detection needs review", async () => {
    await renderCases([caseData({ detections: [{ ...detection, review_state: "auto_accepted" }] })]);

    openPendingRow();
    expect(screen.queryByRole("button", { name: "修正" })).not.toBeInTheDocument();
  });

  it("shows the corrected category and severity in the processing list", async () => {
    const corrected = caseData({
      status: "processing",
      detections: [{ ...detection, review_state: "corrected", reviewed_category: "cleanliness", reviewed_severity: "severe" }],
    });
    await renderCases([corrected]);

    fireEvent.click(screen.getByRole("button", { name: /處理中案件/ }));
    expect(screen.getByText(/清潔／汙損・嚴重/)).toBeInTheDocument();
  });

  it("sets the payment amount through Module E while the Case is processing", async () => {
    const processing = caseData({ status: "processing" });
    const priced = { ...processing, payment_amount: 2400 };
    await renderCases([processing]);
    global.fetch.mockResolvedValueOnce(jsonResponse(priced));

    openProcessingCase("case-1");
    expect(screen.getByText(/金額大於 0 會進入待付款/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "設定金額" }));
    fireEvent.change(screen.getByLabelText("付款金額"), { target: { value: "2,400" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => expect(global.fetch).toHaveBeenLastCalledWith(
      `${API_BASE}/cases/case-1/payment`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount: 2400 }),
      },
    ));
    expect(await screen.findByText("NT$ 2400")).toBeInTheDocument();
    expect(screen.queryByLabelText("付款金額")).not.toBeInTheDocument();
  });

  it("accepts full-width digits when setting the payment amount", async () => {
    const pendingCase = caseData();
    await renderCases([pendingCase]);
    global.fetch.mockResolvedValueOnce(jsonResponse({ ...pendingCase, payment_amount: 300 }));

    openPendingRow();
    fireEvent.click(screen.getByRole("button", { name: "設定金額" }));
    fireEvent.change(screen.getByLabelText("付款金額"), { target: { value: "３００" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => expect(global.fetch).toHaveBeenLastCalledWith(
      `${API_BASE}/cases/case-1/payment`,
      expect.objectContaining({ body: JSON.stringify({ amount: 300 }) }),
    ));
  });

  it.each(["", "-5", "12.5", "abc"])("rejects the invalid payment amount %j without calling Module E", async (value) => {
    await renderCases([caseData({ status: "processing" })]);

    openProcessingCase("case-1");
    fireEvent.click(screen.getByRole("button", { name: "設定金額" }));
    fireEvent.change(screen.getByLabelText("付款金額"), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    expect(screen.getByText(/請輸入 0 以上的整數/)).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it.each(["pending_payment", "completed"])("does not allow changing the payment amount when the Case is %s", async (status) => {
    await renderCases([caseData({ status, payment_amount: 2400 })]);

    if (status === "completed") {
      fireEvent.click(screen.getByRole("button", { name: /已處理案件/ }));
      fireEvent.click(screen.getAllByRole("row")[1]);
    } else {
      openProcessingCase("case-1");
    }

    expect(screen.queryByRole("button", { name: "設定金額" })).not.toBeInTheDocument();
    expect(screen.getByText("此階段不能修改金額")).toBeInTheDocument();
  });

  it("keeps the typed payment amount when Module E rejects it", async () => {
    await renderCases([caseData({ status: "processing" })]);
    global.fetch.mockResolvedValueOnce(jsonResponse({ detail: "payment blocked" }, 409));

    openProcessingCase("case-1");
    fireEvent.click(screen.getByRole("button", { name: "設定金額" }));
    fireEvent.change(screen.getByLabelText("付款金額"), { target: { value: "800" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => expect(window.alert).toHaveBeenCalledWith("設定金額失敗，請確認案件目前的狀態後再試一次。"));
    expect(screen.getByLabelText("付款金額")).toHaveValue("800");
    expect(screen.getByRole("button", { name: "儲存" })).not.toBeDisabled();
  });

  it("lets staff set a payment amount on a Case with zero detections", async () => {
    const empty = caseData({ detections: [], priority_score: null });
    await renderCases([empty]);
    global.fetch.mockResolvedValueOnce(jsonResponse({ ...empty, payment_amount: 500 }));

    openPendingRow();
    fireEvent.click(screen.getByRole("button", { name: "設定金額" }));
    fireEvent.change(screen.getByLabelText("付款金額"), { target: { value: "500" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    expect(await screen.findByText("NT$ 500")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "無需處理／結案" })).not.toBeInTheDocument();
  });

  it("creates a Case with multiple detections through Module E", async () => {
    await renderCases([caseData({ case_id: "case-9", status: "completed" })]);

    fireEvent.click(screen.getByRole("button", { name: "+ 新增案件" }));
    fireEvent.change(screen.getByLabelText("案件編號"), { target: { value: "CASE-4001" } });
    fireEvent.change(screen.getByLabelText("車牌號碼（選填）"), { target: { value: "AAA-1111" } });
    fireEvent.change(screen.getByLabelText("借車人（選填）"), { target: { value: "測試先生" } });

    const [category1, severity1, confidence1, borrow1, return1] = [
      screen.getAllByLabelText("損傷類型")[0], screen.getAllByLabelText("嚴重程度")[0],
      screen.getAllByLabelText("信心度（0～1）")[0], screen.getAllByLabelText("借車照片 ID")[0], screen.getAllByLabelText("還車照片 ID")[0],
    ];
    fireEvent.change(category1, { target: { value: "scratch" } });
    fireEvent.change(severity1, { target: { value: "moderate" } });
    fireEvent.change(confidence1, { target: { value: "0.6" } });
    fireEvent.change(borrow1, { target: { value: "b-1" } });
    fireEvent.change(return1, { target: { value: "r-1" } });

    fireEvent.click(screen.getByRole("button", { name: "新增一筆判讀" }));
    const [category2, severity2, confidence2, borrow2, return2] = [
      screen.getAllByLabelText("損傷類型")[1], screen.getAllByLabelText("嚴重程度")[1],
      screen.getAllByLabelText("信心度（0～1）")[1], screen.getAllByLabelText("借車照片 ID")[1], screen.getAllByLabelText("還車照片 ID")[1],
    ];
    fireEvent.change(category2, { target: { value: "cleanliness" } });
    fireEvent.change(severity2, { target: { value: "severe" } });
    fireEvent.change(confidence2, { target: { value: "0.9" } });
    fireEvent.change(borrow2, { target: { value: "b-2" } });
    fireEvent.change(return2, { target: { value: "r-2" } });

    const created = {
      case_id: "CASE-4001", status: "unassigned", priority_score: 60, payment_amount: 0,
      detections: [
        { detection_id: "CASE-4001-D1", borrow_photo_id: "b-1", return_photo_id: "r-1", source_photo_id: "r-1", category: "scratch", severity: "moderate", confidence: 0.6, review_state: "needs_review", reviewed_category: null, reviewed_severity: null, review_note: null },
        { detection_id: "CASE-4001-D2", borrow_photo_id: "b-2", return_photo_id: "r-2", source_photo_id: "r-2", category: "cleanliness", severity: "severe", confidence: 0.9, review_state: "needs_review", reviewed_category: null, reviewed_severity: null, review_note: null },
      ],
    };
    global.fetch.mockResolvedValueOnce({ ok: true, status: 201, json: vi.fn().mockResolvedValue(created) });

    fireEvent.click(screen.getByRole("button", { name: "建立案件" }));

    await waitFor(() => expect(global.fetch).toHaveBeenLastCalledWith(
      `${API_BASE}/cases`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: "CASE-4001",
          detections: [
            { detection_id: "CASE-4001-D1", borrow_photo_id: "b-1", return_photo_id: "r-1", category: "scratch", severity: "moderate", confidence: 0.6 },
            { detection_id: "CASE-4001-D2", borrow_photo_id: "b-2", return_photo_id: "r-2", category: "cleanliness", severity: "severe", confidence: 0.9 },
          ],
        }),
      },
    ));

    expect(screen.queryByRole("button", { name: "建立案件" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /待處理案件/ })).toHaveTextContent("1");
    fireEvent.click(screen.getByRole("button", { name: /待處理案件/ }));
    expect(screen.getByText("AAA-1111")).toBeInTheDocument();
  });

  it("removing a detection row leaves at least one row, and blocks submit without photo IDs", async () => {
    await renderCases([]);
    fireEvent.click(screen.getByRole("button", { name: "+ 新增案件" }));
    expect(screen.getByRole("button", { name: "移除" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("案件編號"), { target: { value: "CASE-4002" } });
    fireEvent.change(screen.getByLabelText("信心度（0～1）"), { target: { value: "0.5" } });
    fireEvent.click(screen.getByRole("button", { name: "建立案件" }));

    expect(screen.getByText(/借車照片 ID 和還車照片 ID/)).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it("rejects an out-of-range confidence before calling Module E", async () => {
    await renderCases([]);
    fireEvent.click(screen.getByRole("button", { name: "+ 新增案件" }));
    fireEvent.change(screen.getByLabelText("案件編號"), { target: { value: "CASE-4003" } });
    fireEvent.change(screen.getByLabelText("信心度（0～1）"), { target: { value: "1.5" } });
    fireEvent.change(screen.getByLabelText("借車照片 ID"), { target: { value: "b" } });
    fireEvent.change(screen.getByLabelText("還車照片 ID"), { target: { value: "r" } });
    fireEvent.click(screen.getByRole("button", { name: "建立案件" }));

    expect(screen.getByText(/信心度.*0 到 1 之間/)).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it("shows a Chinese message and keeps the form open when the case_id already exists", async () => {
    await renderCases([]);
    fireEvent.click(screen.getByRole("button", { name: "+ 新增案件" }));
    fireEvent.change(screen.getByLabelText("案件編號"), { target: { value: "case-1" } });
    fireEvent.change(screen.getByLabelText("信心度（0～1）"), { target: { value: "0.5" } });
    fireEvent.change(screen.getByLabelText("借車照片 ID"), { target: { value: "b" } });
    fireEvent.change(screen.getByLabelText("還車照片 ID"), { target: { value: "r" } });
    global.fetch.mockResolvedValueOnce({ ok: false, status: 409, json: vi.fn().mockResolvedValue({ detail: "Case already exists: 'case-1'" }) });

    fireEvent.click(screen.getByRole("button", { name: "建立案件" }));

    await waitFor(() => expect(screen.getByText("案件編號已存在，請換一個。")).toBeInTheDocument());
    expect(screen.getByLabelText("案件編號")).toHaveValue("case-1");
    expect(screen.getByRole("button", { name: "建立案件" })).toBeInTheDocument();
  });

  it("does not offer case creation while the backend is unreachable", async () => {
    global.fetch = vi.fn().mockRejectedValueOnce(new Error("offline"));
    render(<App />);
    await screen.findByText(/無法連線到/);

    fireEvent.click(screen.getByRole("button", { name: "+ 新增案件" }));
    fireEvent.change(screen.getByLabelText("案件編號"), { target: { value: "CASE-4004" } });
    fireEvent.change(screen.getByLabelText("信心度（0～1）"), { target: { value: "0.5" } });
    fireEvent.change(screen.getByLabelText("借車照片 ID"), { target: { value: "b" } });
    fireEvent.change(screen.getByLabelText("還車照片 ID"), { target: { value: "r" } });
    fireEvent.click(screen.getByRole("button", { name: "建立案件" }));

    await waitFor(() => expect(screen.getByText("新增案件失敗：後端尚未連線")).toBeInTheDocument());
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});
