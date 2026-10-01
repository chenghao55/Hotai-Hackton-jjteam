import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import CapturePage from '@/app/capture/page';
import CameraPage from '@/app/capture/camera/page';
import CapturePaymentPage from '@/app/capture/payment/page';
import ReviewProgressPage from '@/app/capture/review-progress/page';
import ReviewRequestPage from '@/app/capture/review-request/page';
import CaptureResultPage from '@/app/capture/result/page';
import { captureSteps, damageCaptureSteps, saveCaptureResult, saveCaptureThumbnails } from '@/lib/capture-flow';

const api = vi.hoisted(() => ({
  requestPhotoGuidance: vi.fn(),
  uploadPhoto: vi.fn(),
  createCaseFromPhotos: vi.fn(),
}));

vi.mock('@/lib/module-e-api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/module-e-api')>();
  return { ...original, ...api };
});

const passCheck = { level: 'PASS', code: 'PASS', message: '視角正確', action: 'accept' } as const;

function acceptedPhoto(photoId: string) {
  return { accepted: true, photo_id: photoId, check: passCheck };
}

function installImageMocks() {
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: () => 'blob:preview' });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: () => undefined });
  vi.stubGlobal('Image', class {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    width = 640;
    height = 480;
    set src(_value: string) { this.onload?.(); }
  });
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    configurable: true,
    value: () => ({ drawImage: vi.fn() }),
  });
  Object.defineProperty(HTMLCanvasElement.prototype, 'toDataURL', {
    configurable: true,
    value: () => 'data:image/jpeg;base64,thumbnail',
  });
}

async function uploadCurrentFile(name: string) {
  const expectedCallCount = api.uploadPhoto.mock.calls.length + 1;
  fireEvent.change(screen.getByTestId('camera-input'), {
    target: { files: [new File([name], `${name}.jpg`, { type: 'image/jpeg' })] },
  });
  fireEvent.click(screen.getByRole('button', { name: /儲存並/ }));
  await waitFor(() => expect(api.uploadPhoto).toHaveBeenCalledTimes(expectedCallCount));
}

describe('canonical return capture', () => {
  afterEach(() => {
    cleanup();
    sessionStorage.clear();
    localStorage.clear();
    window.history.replaceState({}, '', '/');
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    window.history.replaceState({}, '', '/capture');
    installImageMocks();
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('11111111-1111-4111-8111-111111111111');
    api.requestPhotoGuidance.mockResolvedValue({ accepted: true, check: passCheck });
  });

  it('keeps the rules gate and links to the canonical camera page', () => {
    render(<CapturePage />);
    const scrollArea = screen.getByTestId('rules-scroll-area');
    Object.defineProperties(scrollArea, {
      scrollTop: { configurable: true, value: 600 },
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1000 },
    });
    fireEvent.scroll(scrollArea);
    fireEvent.click(screen.getByRole('checkbox', { name: '我已經詳細閱讀拍照規則及流程' }));
    expect(screen.getByRole('link', { name: /開始拍照/ })).toHaveAttribute('href', '/capture/camera');
  });

  it('shows the rules and keeps capture disabled before they are read', () => {
    render(<CapturePage />);
    expect(screen.getByRole('heading', { name: /開始拍照前.*請先閱讀拍攝規則/ })).toBeInTheDocument();
    expect(screen.getByText('拍照規則及流程')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /開始拍照/ })).toBeDisabled();
  });

  it('rejects confirmation before the rules reach the end', () => {
    render(<CapturePage />);
    const checkbox = screen.getByRole('checkbox', { name: '我已經詳細閱讀拍照規則及流程' });
    fireEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
    expect(screen.getByRole('alert')).toHaveTextContent('請先詳細閱讀所有條款');
  });

  it('allows the rules confirmation to be cleared again', () => {
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
    fireEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
    expect(screen.getByRole('button', { name: /開始拍照/ })).toBeDisabled();
  });

  it('defines seven steps without dashboard and maps evidence explicitly', () => {
    expect(captureSteps.map((step) => [step.shotType, step.captureSlot, step.includeInCaseEvidence, step.entrySide])).toEqual([
      ['vehicle_cards', 'fuel_parking_card', false, undefined],
      ['front_cabin', 'interior_front', false, 'left'],
      ['rear_cabin', 'interior_rear', false, 'left'],
      ['front_left_45', 'front_left', true, undefined],
      ['front_right_45', 'front_right', true, undefined],
      ['rear_left_45', 'rear_left', true, undefined],
      ['rear_right_45', 'rear_right', true, undefined],
    ]);
    expect(damageCaptureSteps.every((step) => step.captureSlot === 'other_damage' && step.includeInCaseEvidence)).toBe(true);
  });

  it('keeps the camera controls and environment-facing file input', () => {
    render(<CameraPage />);
    expect(screen.getByRole('link', { name: '返回拍照規則' })).toHaveAttribute('href', '/capture');
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));
    expect(screen.getByRole('heading', { name: '加油卡與停車卡' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /開啟即時相機/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /從相簿或檔案選擇/ })).toBeInTheDocument();
    expect(screen.getByTestId('camera-input')).toHaveAttribute('accept', 'image/*');
    expect(screen.getByTestId('camera-input')).toHaveAttribute('capture', 'environment');
  });

  it('calls live photo guidance and renders an accepted=false response', async () => {
    const stop = vi.fn();
    const frame = new Blob(['frame'], { type: 'image/jpeg' });
    api.requestPhotoGuidance.mockResolvedValueOnce({
      accepted: false,
      check: { level: 'L2', code: 'BLUR', message: '畫面模糊，請保持手機穩定', action: 'reshoot' },
    });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop }],
          getVideoTracks: () => [{ getSettings: () => ({ deviceId: 'camera-1' }) }],
        }),
        enumerateDevices: vi.fn().mockResolvedValue([
          { kind: 'videoinput', deviceId: 'camera-1', label: 'Camera' },
        ]),
      },
    });
    Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
    Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', { configurable: true, get: () => 640 });
    Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', { configurable: true, get: () => 480 });
    Object.defineProperty(HTMLCanvasElement.prototype, 'toBlob', {
      configurable: true,
      value: (callback: BlobCallback) => callback(frame),
    });

    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));
    fireEvent.click(screen.getByRole('button', { name: /開啟即時相機/ }));

    await waitFor(() => expect(api.requestPhotoGuidance).toHaveBeenCalledWith(frame, expect.objectContaining({
      photoType: 'return',
      captureSlot: 'fuel_parking_card',
      vehicleType: 'sedan',
      sessionId: '11111111-1111-4111-8111-111111111111',
      frameId: 1,
    })));
    expect(await screen.findByTestId('photo-guidance')).toHaveTextContent('畫面模糊，請保持手機穩定');
  });

  it('uses one session and increasing frame IDs for preview and final guidance', async () => {
    api.requestPhotoGuidance.mockResolvedValue({ accepted: false, check: { level: 'L2', code: 'BLUR', message: '仍可按快門，提交時重新檢核', action: 'reshoot' } });
    const frame = new Blob(['frame'], { type: 'image/jpeg' });
    api.uploadPhoto.mockResolvedValueOnce(acceptedPhoto('cards-id'));
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
          getVideoTracks: () => [{ getSettings: () => ({ deviceId: 'camera-1' }) }],
        }),
        enumerateDevices: vi.fn().mockResolvedValue([]),
      },
    });
    Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
    Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', { configurable: true, get: () => 640 });
    Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', { configurable: true, get: () => 480 });
    Object.defineProperty(HTMLCanvasElement.prototype, 'toBlob', {
      configurable: true,
      value: (callback: BlobCallback) => callback(frame),
    });

    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));
    fireEvent.click(screen.getByRole('button', { name: /開啟即時相機/ }));
    await waitFor(() => expect(api.requestPhotoGuidance).toHaveBeenCalled());
    expect(await screen.findByTestId('photo-guidance')).toHaveTextContent('仍可按快門，提交時重新檢核');
    expect(screen.getByRole('button', { name: '拍攝照片' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '拍攝照片' }));
    fireEvent.click(await screen.findByRole('button', { name: /儲存並拍下一張/ }));
    await waitFor(() => expect(api.uploadPhoto).toHaveBeenCalled());

    const previewContext = api.requestPhotoGuidance.mock.calls[0][1];
    const finalContext = api.uploadPhoto.mock.calls[0][1];
    expect(previewContext.sessionId).toBe('11111111-1111-4111-8111-111111111111');
    expect(finalContext.sessionId).toBe(previewContext.sessionId);
    expect(finalContext.frameId).toBeGreaterThan(previewContext.frameId);
  });

  it('shows the exterior alignment overlay after the first three accepted photos', async () => {
    const stop = vi.fn();
    api.uploadPhoto
      .mockResolvedValueOnce(acceptedPhoto('cards'))
      .mockResolvedValueOnce(acceptedPhoto('front-cabin'))
      .mockResolvedValueOnce(acceptedPhoto('rear-cabin'));
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop }],
          getVideoTracks: () => [{ getSettings: () => ({ deviceId: 'camera-1' }) }],
        }),
        enumerateDevices: vi.fn().mockResolvedValue([]),
      },
    });
    Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));
    for (let index = 0; index < 3; index += 1) {
      await uploadCurrentFile(`aux-${index}`);
      await waitFor(() => expect(screen.getByRole('heading', { name: captureSteps[index + 1].title })).toBeInTheDocument());
    }
    fireEvent.click(screen.getByRole('button', { name: /開啟即時相機/ }));
    const overlay = await screen.findByTestId('vehicle-alignment-overlay');
    expect(overlay).toHaveAttribute('src', '/overlays/sedan-front.png');
    expect(overlay).toHaveStyle({ transform: 'scale(1.14)' });
  });

  it('shows the requested front and rear cabin alignment overlays', async () => {
    api.uploadPhoto
      .mockResolvedValueOnce(acceptedPhoto('cards'))
      .mockResolvedValueOnce(acceptedPhoto('front-cabin'));
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
          getVideoTracks: () => [{ getSettings: () => ({ deviceId: 'camera-1' }) }],
        }),
        enumerateDevices: vi.fn().mockResolvedValue([]),
      },
    });
    Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));

    await uploadCurrentFile('cards');
    await waitFor(() => expect(screen.getByRole('heading', { name: '車內座椅（前座）' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /開啟即時相機/ }));
    expect(await screen.findByTestId('vehicle-alignment-overlay')).toHaveAttribute('src', '/overlays/interior-front.svg');

    await uploadCurrentFile('front-cabin');
    await waitFor(() => expect(screen.getByRole('heading', { name: '車內座椅（後座）' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /開啟即時相機/ }));
    const rearOverlay = await screen.findByTestId('vehicle-alignment-overlay');
    expect(rearOverlay).toHaveAttribute('src', '/overlays/interior-rear.svg');
    expect(rearOverlay).toHaveStyle({ transform: 'scale(1)' });
  });

  it('uses the default camera first and keeps manual selection for multiple devices', async () => {
    const stop = vi.fn();
    const getUserMedia = vi.fn().mockResolvedValue({
      getTracks: () => [{ stop }],
      getVideoTracks: () => [{ getSettings: () => ({ deviceId: 'builtin-camera' }) }],
    });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia,
        enumerateDevices: vi.fn().mockResolvedValue([
          { kind: 'videoinput', deviceId: 'builtin-camera', label: 'Built-in Camera' },
          { kind: 'videoinput', deviceId: 'phone-camera', label: 'Phone Camera' },
        ]),
      },
    });
    Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));
    fireEvent.click(screen.getByRole('button', { name: /開啟即時相機/ }));
    await waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(1));
    expect(getUserMedia).toHaveBeenCalledWith(expect.objectContaining({
      video: expect.not.objectContaining({ deviceId: expect.anything() }),
    }));
    expect(sessionStorage.getItem('capture-camera-device-id')).toBe('builtin-camera');
    expect(await screen.findByRole('combobox', { name: '選擇鏡頭來源' })).toBeInTheDocument();
  });

  it('opens capture normally when only one camera is available', async () => {
    const getUserMedia = vi.fn().mockResolvedValue({
      getTracks: () => [{ stop: vi.fn() }],
      getVideoTracks: () => [{ getSettings: () => ({ deviceId: 'builtin-camera' }) }],
    });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia,
        enumerateDevices: vi.fn().mockResolvedValue([
          { kind: 'videoinput', deviceId: 'builtin-camera', label: 'Built-in Camera' },
        ]),
      },
    });
    Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn().mockResolvedValue(undefined) });
    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));
    fireEvent.click(screen.getByRole('button', { name: /開啟即時相機/ }));
    expect(await screen.findByTestId('live-camera')).toBeInTheDocument();
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('combobox', { name: '選擇鏡頭來源' })).not.toBeInTheDocument();
  });

  it('revokes preview object URLs after acceptance and on unmount', async () => {
    let objectUrlNumber = 0;
    const createObjectURL = vi.fn(() => `blob:preview-${++objectUrlNumber}`);
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL });
    api.uploadPhoto.mockResolvedValueOnce(acceptedPhoto('cards-id'));
    const view = render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));

    await uploadCurrentFile('cards');
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:preview-1'));

    fireEvent.change(screen.getByTestId('camera-input'), {
      target: { files: [new File(['front'], 'front.jpg', { type: 'image/jpeg' })] },
    });
    expect(revokeObjectURL).not.toHaveBeenCalledWith('blob:preview-3');
    view.unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:preview-3');
  });

  it('uploads an accepted auxiliary photo and advances directly to front cabin', async () => {
    api.uploadPhoto.mockResolvedValueOnce(acceptedPhoto('cards-id'));
    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));

    await uploadCurrentFile('cards');

    await waitFor(() => expect(screen.getByRole('heading', { name: '車內座椅（前座）' })).toBeInTheDocument());
    expect(api.uploadPhoto).toHaveBeenCalledWith(expect.any(Blob), expect.objectContaining({
      photoType: 'return',
      captureSlot: 'fuel_parking_card',
      sessionId: '11111111-1111-4111-8111-111111111111',
    }));
    expect(screen.queryByText('儀表板與里程')).not.toBeInTheDocument();
  });

  it('keeps a rejected upload on the same step without storing a photo ID', async () => {
    api.uploadPhoto.mockResolvedValueOnce({ accepted: false, photo_id: null, check: { level: 'L2', code: 'BLUR', message: '畫面模糊，請重新拍攝', action: 'reshoot' } });
    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /休旅車/ }));

    await uploadCurrentFile('blurred');

    expect(screen.getByRole('heading', { name: '加油卡與停車卡' })).toBeInTheDocument();
    expect(await screen.findByText('畫面模糊，請重新拍攝')).toBeInTheDocument();
    expect(api.createCaseFromPhotos).not.toHaveBeenCalled();
  });

  it('uploads all seven steps but submits only exterior evidence IDs', async () => {
    captureSteps.forEach((_, index) => api.uploadPhoto.mockResolvedValueOnce(acceptedPhoto(`photo-${index + 1}`)));
    api.createCaseFromPhotos.mockResolvedValue({ case_id: 'server-case', detections: [], priority_score: null, status: 'unassigned', payment_amount: 0 });
    render(<CameraPage />);
    fireEvent.click(screen.getByRole('button', { name: /轎車/ }));

    for (let index = 0; index < captureSteps.length; index += 1) {
      await uploadCurrentFile(`step-${index}`);
      if (index < captureSteps.length - 1) {
        await waitFor(() => expect(screen.getByRole('heading', { name: captureSteps[index + 1].title })).toBeInTheDocument());
      }
    }

    expect(await screen.findByRole('heading', { name: /是否有需要補拍的車損/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /建立車況案件/ }));
    await waitFor(() => expect(api.createCaseFromPhotos).toHaveBeenCalledWith(['photo-4', 'photo-5', 'photo-6', 'photo-7']));
    expect(sessionStorage.getItem('capture-case:server-case')).toContain('server-case');
    const contexts = api.uploadPhoto.mock.calls.map((call) => call[1]);
    expect(contexts.map((context) => context.frameId)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(new Set(contexts.map((context) => context.sessionId))).toEqual(new Set(['11111111-1111-4111-8111-111111111111']));
    expect(contexts[1].entrySide).toBe('left');
    expect(contexts[2].entrySide).toBe('left');
    expect(contexts[3].entrySide).toBeUndefined();
    expect(sessionStorage.getItem('capture-guidance-session-id')).toBeNull();
    expect(sessionStorage.getItem('capture-guidance-frame-id')).toBeNull();
  });

  it('renders only real Case fields, including reviewed values and zero priority', async () => {
    saveCaptureResult({
      case_id: 'case-real',
      priority_score: 0,
      status: 'processing',
      payment_amount: 500,
      detections: [{
        detection_id: 'detection-1',
        borrow_photo_id: null,
        return_photo_id: 'return-1',
        source_photo_id: 'return-1',
        category: 'scratch',
        severity: 'minor',
        confidence: 0.78,
        review_state: 'corrected',
        reviewed_category: 'collision_damage',
        reviewed_severity: 'moderate',
        review_note: '人工已修正',
      }],
    });
    saveCaptureThumbnails('case-real', { 'return-1': 'data:image/jpeg;base64,thumb' });
    window.history.replaceState({}, '', '/capture/result?case_id=case-real');

    render(<CaptureResultPage />);

    expect(await screen.findByText('case-real')).toBeInTheDocument();
    expect(screen.getByText('處理中')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('NT$500')).toBeInTheDocument();
    expect(screen.getByText('刮痕')).toBeInTheDocument();
    expect(screen.getByText('碰撞損傷')).toBeInTheDocument();
    expect(screen.getByText('中度')).toBeInTheDocument();
    expect(screen.getByText('78%')).toBeInTheDocument();
    expect(screen.queryByText(/預估費用|建議動作|風險/)).not.toBeInTheDocument();
  });

  it('handles a real Case with no detections explicitly', async () => {
    saveCaptureResult({ case_id: 'empty-case', detections: [], priority_score: null, status: 'unassigned', payment_amount: 0 });
    window.history.replaceState({}, '', '/capture/result?case_id=empty-case');
    render(<CaptureResultPage />);
    expect(await screen.findByText('目前 Case 沒有偵測到車況項目。')).toBeInTheDocument();
    expect(screen.getByText('尚未計算')).toBeInTheDocument();
  });

  it('keeps the retained prototype payment page behavior isolated', () => {
    window.history.replaceState({}, '', '/capture/payment?case_id=CASE-1044');
    render(<CapturePaymentPage />);
    expect(screen.getByRole('heading', { name: '選擇付款方式' })).toBeInTheDocument();
    expect(screen.getByText('NT$5,500')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /銀行轉帳/ })).toBeChecked();
    fireEvent.click(screen.getByRole('radio', { name: /LINE Pay/ }));
    fireEvent.click(screen.getByRole('button', { name: /確認付款方式並繼續/ }));
    expect(screen.getByRole('status')).toHaveTextContent('已選擇 LINE Pay');
  });

  it('keeps the retained prototype review request behavior isolated', () => {
    window.history.replaceState({}, '', '/capture/review-request?case_id=CASE-1044');
    render(<ReviewRequestPage />);
    expect(screen.getByRole('heading', { name: '你對哪些判讀結果有疑義？' })).toBeInTheDocument();
    const submit = screen.getByRole('link', { name: /確認送出人工覆核申請/ });
    fireEvent.click(submit);
    expect(screen.getByRole('alert')).toHaveTextContent('請至少勾選一項有疑義的 AI 判讀結果');
    fireEvent.click(screen.getByRole('checkbox', { name: /右後保桿出現疑似新增刮痕/ }));
    fireEvent.change(screen.getByLabelText('補充說明'), { target: { value: '這道痕跡在取車前就已存在。' } });
    fireEvent.click(submit);
    expect(JSON.parse(sessionStorage.getItem('capture-review-request:CASE-1044') || '{}')).toMatchObject({
      finding_ids: ['FINDING-1044-01'],
      note: '這道痕跡在取車前就已存在。',
    });
  });

  it('keeps the retained prototype review progress behavior isolated', () => {
    window.history.replaceState({}, '', '/capture/review-progress?case_id=CASE-1044');
    render(<ReviewProgressPage />);
    expect(screen.getByRole('heading', { name: '人工審核中', level: 1 })).toBeInTheDocument();
    expect(screen.getByText('已完成 3 / 5 階段')).toBeInTheDocument();
    expect(screen.getByText('覆核申請已送出')).toBeInTheDocument();
    expect(screen.getByText('等待付款確認')).toBeInTheDocument();
    expect(screen.getByText('案件完成')).toBeInTheDocument();
  });
});
