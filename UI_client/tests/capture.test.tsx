import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import CapturePage, { LegacyCapturePage } from '@/app/capture/page';
import CameraPage from '@/app/capture/camera/page';
import AnalysisDemoPage from '@/app/capture/analysis-demo/page';
import CapturePaymentPage from '@/app/capture/payment/page';
import ReviewRequestPage from '@/app/capture/review-request/page';
import ReviewProgressPage from '@/app/capture/review-progress/page';
import CaptureResultPage from '@/app/capture/result/page';
import { saveCaptureResult } from '@/lib/capture-flow';
import { analyses, nextStatus, type ScenarioKey } from '@/lib/prototype';

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
  window.history.replaceState({}, '', '/');
  vi.unstubAllGlobals();
});

function seedResult(scenario: ScenarioKey) {
  const result = analyses[scenario];
  saveCaptureResult({
    ...result,
    status: nextStatus(result.recommended_action),
    analyzed_at: '2026-09-16T02:30:00.000Z',
    source: 'mock-api',
  });
}

describe('手機拍攝端', () => {
  it('顯示拍照規則且開始拍照按鈕預設停用', () => {
    render(<CapturePage />);
    expect(screen.getByRole('heading', { name: /開始拍照前.*請先閱讀拍攝規則/ })).toBeInTheDocument();
    expect(screen.getByText('拍照規則及流程')).toBeInTheDocument();
    expect(screen.getByText('我已經詳細閱讀拍照規則及流程')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /開始拍照/ })).toBeDisabled();
  });

  it('未讀完規則時拒絕勾選並顯示提醒', () => {
    render(<CapturePage />);
    const checkbox = screen.getByRole('checkbox', { name: '我已經詳細閱讀拍照規則及流程' });
    expect(checkbox).not.toBeChecked();
    fireEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
    expect(screen.getByRole('alert')).toHaveTextContent('請先詳細閱讀所有條款');
  });

  it('規則捲到底後可勾選及取消，且不影響開始拍照', () => {
    render(<CapturePage />);
    const checkbox = screen.getByRole('checkbox', { name: '我已經詳細閱讀拍照規則及流程' });
    const scrollArea = screen.getByTestId('rules-scroll-area');
    Object.defineProperties(scrollArea, {
      scrollTop: { configurable: true, value: 600 },
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1000 },
    });
    fireEvent.scroll(scrollArea);
    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(screen.getByRole('link', { name: /開始拍照/ })).toHaveAttribute('href', '/capture/camera');
    fireEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
    expect(screen.getByRole('button', { name: /開始拍照/ })).toBeDisabled();
  });

  it('相機頁提供拍攝引導、手機後鏡頭與返回按鈕', () => {
    render(<CameraPage />);
    expect(screen.getByRole('link', { name: '返回拍照規則' })).toHaveAttribute('href', '/capture');
    expect(screen.getByRole('heading', { name: /這次拍攝的是哪種車型/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));
    expect(screen.getByRole('heading', { name: '加油卡與停車卡' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /開啟即時相機/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /從相簿或檔案選擇/ })).toBeInTheDocument();
    expect(screen.getByTestId('camera-input')).toHaveAttribute('accept', 'image/*');
    expect(screen.getByTestId('camera-input')).toHaveAttribute('capture', 'environment');
  });

  it('拍照後顯示預覽並可確認照片進入下一個角度', async () => {
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: () => 'blob:camera-preview' });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: () => undefined });
    vi.stubGlobal('Image', class {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      width = 640;
      height = 480;
      set src(_value: string) { this.onload?.(); }
    });
    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));
    const input = screen.getByTestId('camera-input');
    fireEvent.change(input, { target: { files: [new File(['photo'], 'car.jpg', { type: 'image/jpeg' })] } });
    expect(screen.getByAltText('加油卡與停車卡照片預覽')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /儲存並拍下一張/ }));
    await waitFor(() => expect(screen.getByRole('heading', { name: '儀表板與里程' })).toBeInTheDocument());
    expect(screen.getByText('基本照片 2／8')).toBeInTheDocument();
    fireEvent.change(input, { target: { files: [new File(['photo-2'], 'car-2.jpg', { type: 'image/jpeg' })] } });
    expect(screen.queryByRole('button', { name: /新增損壞照片/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /沒有車損/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /儲存並拍下一張/ })).toBeInTheDocument();
  });

  it('可逐張跳過八個基本步驟，再選擇是否新增損壞照片', async () => {
    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /休旅車/ }));
    const skip = () => fireEvent.click(screen.getByRole('button', { name: '跳過此張' }));
    skip();
    expect(screen.getByRole('heading', { name: '儀表板與里程' })).toBeInTheDocument();
    skip();
    skip();
    skip();
    expect(screen.getByRole('heading', { name: '車身左前方 45°' })).toBeInTheDocument();
    skip();
    skip();
    skip();
    skip();
    expect(screen.getByRole('heading', { name: /是否有需要補拍的車損/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /新增損壞照片/ }));
    await waitFor(() => expect(screen.getByRole('heading', { name: '損壞照片 1' })).toBeInTheDocument());
    expect(screen.getByText(/拍 1 張即可進入下一流程/)).toBeInTheDocument();
  });

  it('第五張開啟鏡頭時會顯示所選車型的透明角度框', async () => {
    const stop = vi.fn();
    vi.stubGlobal('navigator', {
      ...navigator,
      mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }) },
    });
    Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));
    for (let index = 0; index < 4; index += 1) fireEvent.click(screen.getByRole('button', { name: '跳過此張' }));
    expect(screen.getByRole('heading', { name: '車身左前方 45°' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /開啟即時相機/ }));
    expect(await screen.findByTestId('vehicle-alignment-overlay')).toHaveAttribute('src', '/overlays/sedan-front.png');
  });

  it('取得權限後會直接使用電腦預設鏡頭並保留手動切換', async () => {
    const stop = vi.fn();
    const getUserMedia = vi.fn().mockImplementation(async (constraints: MediaStreamConstraints) => {
      const requested = typeof constraints.video === 'object' && 'deviceId' in constraints.video ? constraints.video.deviceId : undefined;
      const deviceId = requested && typeof requested === 'object' && 'exact' in requested ? String(requested.exact) : 'builtin-camera';
      return {
        getTracks: () => [{ stop }],
        getVideoTracks: () => [{ getSettings: () => ({ deviceId }) }],
      };
    });
    vi.stubGlobal('navigator', {
      ...navigator,
      mediaDevices: {
        getUserMedia,
        enumerateDevices: vi.fn().mockResolvedValue([
          { kind: 'videoinput', deviceId: 'builtin-camera', label: 'FaceTime HD Camera' },
          { kind: 'videoinput', deviceId: 'phone-camera', label: 'JJL相機' },
        ]),
      },
    });
    Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));
    fireEvent.click(screen.getByRole('button', { name: /開啟即時相機/ }));
    expect(await screen.findByText('鏡頭來源')).toBeInTheDocument();
    expect(screen.getByText('預設使用電腦鏡頭')).toBeInTheDocument();
    await waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(1));
    expect(getUserMedia).toHaveBeenCalledWith(expect.objectContaining({
      video: expect.not.objectContaining({ deviceId: expect.anything() }),
    }));
    expect(sessionStorage.getItem('capture-camera-device-id')).toBe('builtin-camera');
    expect(screen.getByRole('combobox', { name: '選擇鏡頭來源' })).toBeInTheDocument();
  });

  it('只偵測到電腦鏡頭時仍會正常開啟拍攝', async () => {
    const computerStream = {
      getTracks: () => [{ stop: vi.fn() }],
      getVideoTracks: () => [{ getSettings: () => ({ deviceId: 'builtin-camera' }) }],
    };
    const getUserMedia = vi.fn().mockResolvedValue(computerStream);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia,
        enumerateDevices: vi.fn().mockResolvedValue([{ kind: 'videoinput', deviceId: 'builtin-camera', label: 'FaceTime HD Camera' }]),
      },
    });
    Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));
    fireEvent.click(screen.getByRole('button', { name: /開啟即時相機/ }));
    expect(await screen.findByTestId('live-camera')).toBeInTheDocument();
    expect(await screen.findByText('鏡頭來源')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });

  it('暫時分析頁只提供成功與失敗兩個結果按鈕', () => {
    render(<AnalysisDemoPage />);
    expect(screen.getByRole('button', { name: /成功/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /失敗/ })).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(2);
  });

  it('正常結果顯示不需額外費用並完成結案', async () => {
    seedResult('normal');
    render(<CaptureResultPage />);
    expect(await screen.findByRole('heading', { name: '還車檢查已完成' })).toBeInTheDocument();
    expect(screen.getByText(/本次不需支付額外費用/)).toBeInTheDocument();
    expect(screen.getByText('已結案')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /完成並返回首頁/ })).toHaveAttribute('href', '/');
  });

  it('疑似車損分別列出兩處問題、個別估價與費用總表', async () => {
    seedResult('damage');
    render(<CaptureResultPage />);
    expect(await screen.findByRole('heading', { name: 'AI 偵測到 2 處疑似問題' })).toBeInTheDocument();
    expect(screen.getByText('右後保桿出現疑似新增刮痕')).toBeInTheDocument();
    expect(screen.getByText('右前車門下緣出現疑似新增凹痕')).toBeInTheDocument();
    expect(screen.getAllByText('NT$2,000–4,000')).toHaveLength(2);
    expect(screen.getAllByText('NT$1,500–3,000')).toHaveLength(2);
    expect(screen.getByText('NT$3,500–7,000')).toBeInTheDocument();
    expect(screen.getByText('最終價格為：')).toBeInTheDocument();
    expect(screen.getByText('NT$5,500')).toBeInTheDocument();
    expect(screen.queryByText(/78%|74%|信心/)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /申請人工覆核/ })).toHaveAttribute('href', '/capture/review-request?case_id=CASE-1044');
    expect(screen.getByRole('link', { name: /我對 AI 判讀結果無異議/ })).toHaveAttribute('href', '/capture/payment?case_id=CASE-1044');
  });

  it('付款頁提供銀行轉帳、LINE Pay 與 Apple Pay', () => {
    seedResult('damage');
    window.history.replaceState({}, '', '/capture/payment?case_id=CASE-1044');
    render(<CapturePaymentPage />);
    expect(screen.getByRole('heading', { name: '選擇付款方式' })).toBeInTheDocument();
    expect(screen.getByText('本次最終應付金額')).toBeInTheDocument();
    expect(screen.getByText('NT$5,500')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /銀行轉帳/ })).toBeChecked();
    expect(screen.getByRole('radio', { name: /LINE Pay/ })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Apple Pay/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: /LINE Pay/ }));
    fireEvent.click(screen.getByRole('button', { name: /確認付款方式並繼續/ }));
    expect(screen.getByRole('status')).toHaveTextContent('已選擇 LINE Pay');
  });

  it('人工覆核頁顯示五階段案件進度與離開按鈕', () => {
    window.history.replaceState({}, '', '/capture/review-progress?case_id=CASE-1044');
    render(<ReviewProgressPage />);
    expect(screen.getByRole('heading', { name: '人工審核中', level: 1 })).toBeInTheDocument();
    expect(screen.getByText('已完成 3 / 5 階段')).toBeInTheDocument();
    expect(screen.getByText('覆核申請已送出')).toBeInTheDocument();
    expect(screen.getByText('等待付款確認')).toBeInTheDocument();
    expect(screen.getByText('案件完成')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /先返回首頁/ })).toHaveAttribute('href', '/');
  });

  it('人工覆核申請頁可選擇有疑義項目並填寫說明', () => {
    seedResult('damage');
    window.history.replaceState({}, '', '/capture/review-request?case_id=CASE-1044');
    render(<ReviewRequestPage />);
    expect(screen.getByRole('heading', { name: '你對哪些判讀結果有疑義？' })).toBeInTheDocument();
    expect(screen.getByText('右後保桿出現疑似新增刮痕')).toBeInTheDocument();
    expect(screen.getByText('右前車門下緣出現疑似新增凹痕')).toBeInTheDocument();
    const submit = screen.getByRole('link', { name: /確認送出人工覆核申請/ });
    fireEvent.click(submit);
    expect(screen.getByRole('alert')).toHaveTextContent('請至少勾選一項有疑義的 AI 判讀結果');
    fireEvent.click(screen.getByRole('checkbox', { name: /右後保桿出現疑似新增刮痕/ }));
    fireEvent.change(screen.getByLabelText('補充說明'), { target: { value: '這道痕跡在取車前就已存在。' } });
    fireEvent.click(submit);
    expect(JSON.parse(sessionStorage.getItem('capture-review-request:CASE-1044') || '{}')).toMatchObject({ finding_ids: ['FINDING-1044-01'], note: '這道痕跡在取車前就已存在。' });
    expect(submit).toHaveAttribute('href', '/capture/review-progress?case_id=CASE-1044');
  });

  it('髒污結果顯示可能清潔費', async () => {
    seedResult('dirty');
    render(<CaptureResultPage />);
    expect(await screen.findByText('清潔費用預估總表')).toBeInTheDocument();
    expect(screen.getAllByText('NT$500–1,200')).toHaveLength(3);
    expect(screen.getAllByText(/後座發現飲料杯/)).toHaveLength(2);
  });

  it('舊版拍攝流程仍可操作並拒絕非圖片檔案', () => {
    const { container } = render(<LegacyCapturePage />);
    fireEvent.click(screen.getByRole('button', { name: /車尾右後方 45°/ }));
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['bad'], 'case.txt', { type: 'text/plain' })] } });
    expect(screen.getByRole('alert')).toHaveTextContent('請選擇 JPG、PNG 或 HEIC 圖片');
  });
});
