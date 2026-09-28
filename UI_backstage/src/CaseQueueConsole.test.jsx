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

function openPendingRow(text) {
  const row = screen.getByText(text).closest("tr");
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
    expect(screen.getByText("42%")).toBeInTheDocument();

    openPendingRow("42%");
    expect(screen.getByRole("heading", { name: /case-1/ })).toBeInTheDocument();
  });

  it("renders and opens a Case with zero detections", async () => {
    await renderCases([caseData({ case_id: "case-empty", detections: [], priority_score: null })]);

    expect(screen.getByText("無 Detection")).toBeInTheDocument();
    openPendingRow("無 Detection");
    expect(screen.getByRole("heading", { name: /case-empty/ })).toBeInTheDocument();
    expect(screen.getByText(/此案件沒有 Detection/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "派工" })).toBeInTheDocument();
  });

  it("dispatches through Module E and applies only the returned Case", async () => {
    const original = caseData({ detections: [{ ...detection, review_state: "auto_accepted" }] });
    const dispatched = { ...original, status: "dispatched" };
    await renderCases([original]);
    global.fetch.mockResolvedValueOnce(jsonResponse(dispatched));

    openPendingRow("42%");
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

    openPendingRow("42%");
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

    openPendingRow("42%");
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

    openPendingRow("42%");
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

    openPendingRow("無 Detection");
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

    openPendingRow("42%");
    fireEvent.click(screen.getByRole("button", { name: "派工" }));

    await waitFor(() => expect(window.alert).toHaveBeenCalledWith("操作失敗：dispatch blocked"));
    expect(screen.getByRole("button", { name: "派工" })).toBeInTheDocument();
  });
});
