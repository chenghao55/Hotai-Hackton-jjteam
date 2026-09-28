'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  Camera,
  CameraOff,
  Car,
  Check,
  FolderOpen,
  ImagePlus,
  LoaderCircle,
  MoveUpRight,
  Plus,
  ScanLine,
  ShieldCheck,
  SunMedium,
  Truck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  captureSteps,
  damageCaptureSteps,
  saveCaptureResult,
  saveCaptureThumbnails,
  type CapturedPhoto,
} from '@/lib/capture-flow';
import {
  createCaseFromPhotos,
  ModuleERequestError,
  requestPhotoGuidance,
  uploadPhoto,
  type PhotoGuidanceResponse,
  type CaptureContext,
} from '@/lib/module-e-api';

type CaptureMode = 'normal' | 'damage';
type VehicleType = 'sedan' | 'suv';

export default function CameraPage() {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [currentPhoto, setCurrentPhoto] = useState<Blob | null>(null);
  const [capturedPhotos, setCapturedPhotos] = useState<CapturedPhoto[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [requestError, setRequestError] = useState('');
  const [guidance, setGuidance] = useState<PhotoGuidanceResponse | null>(null);
  const [guidanceLoading, setGuidanceLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [creatingCase, setCreatingCase] = useState(false);
  const [cameraStatus, setCameraStatus] = useState<'idle' | 'starting' | 'live'>('idle');
  const [captureMode, setCaptureMode] = useState<CaptureMode>('normal');
  const [vehicleType, setVehicleType] = useState<VehicleType | null>(null);
  const [entrySide, setEntrySide] = useState<'left' | 'right'>('left');
  const [showDamageChoice, setShowDamageChoice] = useState(false);
  const [videoDevices, setVideoDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const guidanceInFlightRef = useRef(false);
  const sessionIdRef = useRef(globalThis.crypto?.randomUUID?.() ?? `capture-${Date.now()}-${Math.random()}`);
  const frameIdRef = useRef(0);

  const activeSteps = useMemo(
    () => captureMode === 'damage' ? damageCaptureSteps : captureSteps,
    [captureMode],
  );
  const currentStep = activeSteps[currentIndex] ?? activeSteps[0];
  const progress = ((currentIndex + 1) / activeSteps.length) * 100;
  const overlay = captureMode === 'normal' && currentIndex >= 3 && vehicleType
    ? getVehicleOverlay(vehicleType, currentStep.shotType)
    : null;

  function nextContext(): CaptureContext {
    frameIdRef.current += 1;
    return {
      vehicleType: vehicleType as VehicleType,
      captureSlot: currentStep.captureSlot,
      sessionId: sessionIdRef.current,
      frameId: frameIdRef.current,
      ...(currentStep.captureSlot === 'interior_front' || currentStep.captureSlot === 'interior_rear'
        ? { entrySide } : {}),
    };
  }

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    if (!previewUrl) return;
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  useEffect(() => {
    if (cameraStatus !== 'live' || !vehicleType) return;
    let active = true;

    async function checkFrame() {
      if (!active || guidanceInFlightRef.current) return;
      const frame = await captureVideoFrame(videoRef.current, canvasRef.current, 0.72);
      if (!frame || !active) return;
      guidanceInFlightRef.current = true;
      setGuidanceLoading(true);
      try {
        const response = await requestPhotoGuidance(frame, nextContext());
        if (active) {
          setGuidance(response);
          setRequestError('');
        }
      } catch (error) {
        if (active) setRequestError(formatRequestError(error, '即時拍攝指導'));
      } finally {
        guidanceInFlightRef.current = false;
        if (active) setGuidanceLoading(false);
      }
    }

    void checkFrame();
    const timer = window.setInterval(() => void checkFrame(), 1500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [cameraStatus, currentStep.captureSlot, entrySide, vehicleType]);

  function stopCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraStatus('idle');
  }

  function clearCurrentPhoto() {
    setPreviewUrl(null);
    setCurrentPhoto(null);
    if (inputRef.current) inputRef.current.value = '';
  }

  function chooseVehicle(type: VehicleType) {
    sessionStorage.setItem('capture-vehicle-type', type);
    setVehicleType(type);
  }

  function startDamageCapture() {
    setCaptureMode('damage');
    setCurrentIndex(0);
    setShowDamageChoice(false);
    clearCurrentPhoto();
    setGuidance(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function submitCase(photos: CapturedPhoto[]) {
    const evidencePhotoIds = photos
      .filter((photo) => photo.step.includeInCaseEvidence)
      .map((photo) => photo.photoId);
    if (!evidencePhotoIds.length) {
      setRequestError('尚未完成車身證據照片，無法建立案件。');
      return;
    }

    setCreatingCase(true);
    setRequestError('');
    try {
      const result = await createCaseFromPhotos(evidencePhotoIds);
      saveCaptureResult(result);
      saveCaptureThumbnails(
        result.case_id,
        Object.fromEntries(
          photos
            .filter((photo) => photo.thumbnail)
            .map((photo) => [photo.photoId, photo.thumbnail as string]),
        ),
      );
      window.location.assign(`/capture/result?case_id=${encodeURIComponent(result.case_id)}`);
    } catch (error) {
      setRequestError(`${formatRequestError(error, '案件建立')} 已接受的照片仍保留在本頁，請重新送出。`);
      setCreatingCase(false);
    }
  }

  async function startCamera(requestedDeviceId?: string) {
    setRequestError('');
    setGuidance(null);
    clearCurrentPhoto();
    if (!navigator.mediaDevices?.getUserMedia) {
      setRequestError('這個瀏覽器無法直接使用攝影機，請改用下方的「從相簿選擇」。');
      return;
    }

    setCameraStatus('starting');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: requestedDeviceId
          ? { deviceId: { exact: requestedDeviceId }, width: { ideal: 1920 }, height: { ideal: 1080 } }
          : { width: { ideal: 1920 }, height: { ideal: 1080 } },
      });
      const devices = navigator.mediaDevices.enumerateDevices
        ? (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === 'videoinput')
        : [];
      setVideoDevices(devices);
      const activeDeviceId = stream.getVideoTracks?.()[0]?.getSettings?.().deviceId ?? '';
      setSelectedDeviceId(activeDeviceId);
      if (activeDeviceId) sessionStorage.setItem('capture-camera-device-id', activeDeviceId);
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraStatus('live');
    } catch (cameraError) {
      stopCamera();
      const denied = cameraError instanceof DOMException && (cameraError.name === 'NotAllowedError' || cameraError.name === 'SecurityError');
      setRequestError(denied
        ? '尚未取得攝影機權限。請在瀏覽器允許使用攝影機後再試一次，或從相簿選擇照片。'
        : '目前找不到可用的攝影機，請確認鏡頭未被其他程式占用，或從相簿選擇照片。');
    }
  }

  async function changeCamera(deviceId: string | null) {
    if (!deviceId) return;
    setSelectedDeviceId(deviceId);
    stopCamera();
    await startCamera(deviceId);
  }

  async function takePhoto() {
    const blob = await captureVideoFrame(videoRef.current, canvasRef.current, 0.92);
    if (!blob) {
      setRequestError('攝影機仍在準備中，請稍候再按一次快門。');
      return;
    }
    setRequestError('');
    setCurrentPhoto(blob);
    setPreviewUrl(URL.createObjectURL(blob));
    stopCamera();
  }

  function selectPhoto(file?: File) {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setRequestError('請拍攝或選擇圖片檔案。');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setRequestError('照片超過 10 MB，請重新拍攝。');
      return;
    }
    setRequestError('');
    stopCamera();
    setCurrentPhoto(file);
    setPreviewUrl(URL.createObjectURL(file));
  }

  async function confirmPhoto(action: 'continue' | 'finish' = 'continue') {
    if (!currentPhoto || uploading || creatingCase) return;
    setUploading(true);
    setRequestError('');
    try {
      const response = await uploadPhoto(currentPhoto, 'return', currentStep.captureSlot, nextContext());
      setGuidance(response);
      if (!response.accepted || !response.photo_id) {
        setUploading(false);
        return;
      }

      const thumbnail = await createThumbnail(currentPhoto);
      const completed = [...capturedPhotos, { step: currentStep, photoId: response.photo_id, thumbnail }];
      setCapturedPhotos(completed);
      setUploading(false);
      clearCurrentPhoto();
      setGuidance(null);

      if (action === 'finish') {
        setShowDamageChoice(true);
        await submitCase(completed);
        return;
      }
      if (captureMode === 'normal' && currentIndex === captureSteps.length - 1) {
        setShowDamageChoice(true);
      } else if (currentIndex < activeSteps.length - 1) {
        setCurrentIndex((value) => value + 1);
      }
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (error) {
      setUploading(false);
      setRequestError(`${formatRequestError(error, '照片上傳')} 尚未儲存 photo_id，請重新送出。`);
    }
  }

  if (!vehicleType) return <VehicleTypeSelection onSelect={chooseVehicle} />;
  if (showDamageChoice) {
    return (
      <DamageChoice
        normalPhotoCount={capturedPhotos.filter((photo) => !photo.step.shotType.startsWith('damage_')).length}
        damagePhotoCount={capturedPhotos.filter((photo) => photo.step.shotType.startsWith('damage_')).length}
        onAddDamage={startDamageCapture}
        onContinue={() => void submitCase(capturedPhotos)}
        creatingCase={creatingCase}
        error={requestError}
      />
    );
  }

  return (
    <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8">
      <div className="mx-auto min-h-dvh w-full max-w-md overflow-hidden bg-white shadow-[0_0_50px_rgb(16_37_31/10%)] sm:min-h-[calc(100dvh-4rem)] sm:rounded-[32px]">
        <header className="bg-[#101d1a] px-5 py-4 text-white"><div className="grid grid-cols-[44px_1fr_44px] items-center"><Link href="/capture" aria-label="返回拍照規則" className="grid size-11 place-items-center rounded-2xl border border-white/15 bg-white/10"><ArrowLeft className="size-5" /></Link><div className="text-center"><p className="font-semibold">車況拍攝</p><p className="mt-0.5 text-sm text-white/55">車輛 7A21</p></div><span className="grid size-11 place-items-center rounded-2xl bg-[#c9ff38] text-[#10251f]"><ShieldCheck className="size-5" /></span></div></header>
        <section className="px-5 pb-8 pt-5 sm:px-7">
          <div className="flex items-center justify-between gap-4"><p className="text-sm font-semibold text-[#2d6d5d]">{captureMode === 'damage' ? `損壞照片 ${currentIndex + 1}／最多 4 張` : `基本照片 ${currentIndex + 1}／7`}</p><p className="text-sm font-medium text-[#62756d]">{Math.round(progress)}%</p></div>
          <Progress value={progress} className="mt-2 h-2 bg-[#dce9e1] [&>div]:bg-[#c9ff38]" />
          <h1 className="mt-5 text-[28px] font-semibold leading-tight tracking-tight">{currentStep.title}</h1>
          <p className="mt-2 text-base leading-6 text-[#62756d]">{currentStep.description}</p>
          {captureMode === 'damage' && <div className="mt-4 rounded-2xl border border-[#cfe1d7] bg-[#eff6f1] p-4 text-sm leading-6 text-[#355f54]"><strong className="block text-[#173e35]">損壞照片為選填</strong>拍 1 張即可進入下一流程，最多可補充 4 張。</div>}
          {(currentStep.captureSlot === 'interior_front' || currentStep.captureSlot === 'interior_rear') && <div className="mt-4"><label htmlFor="entry-side" className="mb-2 block text-sm font-semibold">從哪一側車門拍攝？</label><select id="entry-side" value={entrySide} onChange={(event) => { setEntrySide(event.target.value as 'left' | 'right'); setGuidance(null); }} className="h-11 w-full rounded-xl border border-[#cfe1d7] bg-white px-3"><option value="left">左側車門</option><option value="right">右側車門</option></select></div>}

          {creatingCase ? (
            <div className="mt-8 grid min-h-[360px] place-items-center rounded-[28px] bg-[#10251f] px-8 text-center text-white" role="status"><div><LoaderCircle className="mx-auto size-10 animate-spin text-[#c9ff38]" /><h2 className="mt-5 text-2xl font-semibold">正在建立案件</h2><p className="mt-2 text-base text-white/65">正在分析已接受的車身照片，請不要關閉頁面。</p></div></div>
          ) : (
            <>
              <div className="relative mt-5 aspect-[4/3] overflow-hidden rounded-[28px] bg-[#10251f] shadow-[0_12px_32px_rgb(16_37_31/18%)]">
                {previewUrl ? <img src={previewUrl} alt={`${currentStep.title}照片預覽`} className="size-full object-cover" /> : cameraStatus === 'live' || cameraStatus === 'starting' ? <><video ref={videoRef} data-testid="live-camera" aria-label="即時攝影機預覽" className="relative z-0 size-full object-cover" autoPlay muted playsInline />{cameraStatus === 'starting' && <div className="absolute inset-0 z-10 grid place-items-center bg-[#10251f]/85 text-white"><LoaderCircle className="size-8 animate-spin text-[#c9ff38]" /></div>}{cameraStatus === 'live' && overlay && <img src={overlay.src} alt="" data-testid="vehicle-alignment-overlay" className="pointer-events-none absolute inset-0 z-20 size-full object-contain p-2 opacity-75" style={{ transform: overlay.flip ? 'scaleX(-1)' : undefined }} />}</> : <div className="grid size-full place-items-center px-8 text-center text-white"><div><Camera className="mx-auto size-10 text-[#c9ff38]" /><p className="mt-4 text-lg font-semibold">將拍攝部位對準框線</p></div></div>}
                <div className="pointer-events-none absolute inset-5 z-30 rounded-[22px] border-2 border-dashed border-[#c9ff38]/80" />
                <span className="pointer-events-none absolute bottom-4 left-1/2 z-40 -translate-x-1/2 whitespace-nowrap rounded-full bg-black/60 px-3 py-1.5 text-sm text-white">{currentStep.frameLabel}</span>
              </div>
              <canvas ref={canvasRef} className="hidden" aria-hidden="true" />
              <div className="mt-4 grid grid-cols-3 gap-2"><Tip icon={<MoveUpRight />} label={currentStep.tips[0]} /><Tip icon={<ScanLine />} label={currentStep.tips[1]} /><Tip icon={<SunMedium />} label={currentStep.tips[2]} /></div>
              <input ref={inputRef} data-testid="camera-input" type="file" accept="image/*" capture="environment" className="sr-only" onChange={(event) => selectPhoto(event.target.files?.[0])} />
              {requestError && <div role="alert" className="mt-4 flex gap-2 rounded-2xl bg-red-50 p-4 text-sm font-medium text-red-700"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{requestError}</div>}
              {guidance && <div data-testid="photo-guidance" className={`mt-4 rounded-2xl p-4 text-sm font-medium ${guidance.accepted ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-800'}`}>{guidance.check.message}{guidance.review_required && <p className="mt-2">人工審理照片的交付流程尚未接通，目前無法儲存此張照片。</p>}</div>}
              {guidanceLoading && <p className="mt-2 text-center text-sm text-[#62756d]">正在檢查拍攝畫面…</p>}

              {previewUrl ? (
                <div className="mt-5 space-y-3">
                  <Button variant="outline" className="h-14 w-full rounded-2xl" onClick={() => void startCamera()} disabled={uploading}><ImagePlus className="size-5" />重新拍攝</Button>
                  {captureMode === 'damage' && currentIndex < damageCaptureSteps.length - 1 && <Button variant="outline" className="h-14 w-full rounded-2xl" onClick={() => void confirmPhoto('continue')} disabled={uploading}><Plus className="size-5" />再新增一張損壞照片</Button>}
                  <Button className="h-16 w-full rounded-2xl bg-[#173e35] text-white" onClick={() => void confirmPhoto(captureMode === 'damage' ? 'finish' : 'continue')} disabled={uploading}>{uploading ? <LoaderCircle className="size-5 animate-spin" /> : <Check className="size-5" />}{captureMode === 'damage' ? '完成並建立案件' : currentIndex === captureSteps.length - 1 ? '儲存並繼續' : '儲存並拍下一張'}</Button>
                </div>
              ) : cameraStatus === 'live' ? (
                <div className="mt-5 space-y-4">{videoDevices.length > 1 && <Select value={selectedDeviceId || null} onValueChange={changeCamera}><SelectTrigger aria-label="選擇鏡頭來源" className="h-10 rounded-xl"><SelectValue placeholder="選擇鏡頭" /></SelectTrigger><SelectContent>{videoDevices.map((device, index) => <SelectItem key={device.deviceId || index} value={device.deviceId}>{device.label || `攝影機 ${index + 1}`}</SelectItem>)}</SelectContent></Select>}<div className="grid grid-cols-[1fr_72px_1fr] items-center gap-3"><Button variant="outline" className="h-12 rounded-2xl" onClick={stopCamera}><CameraOff className="size-5" />取消</Button><Button aria-label="拍攝照片" className="size-[72px] rounded-full border-[6px] border-white bg-[#c9ff38] text-[#10251f]" onClick={() => void takePhoto()}><Camera className="size-7" /></Button><span className="text-center text-sm text-[#62756d]">按中央快門</span></div></div>
              ) : (
                <div className="mt-5 space-y-3"><Button className="h-14 w-full rounded-2xl bg-[#173e35] text-white" onClick={() => void startCamera()} disabled={cameraStatus === 'starting'}><Camera className="size-5" />開啟即時相機</Button><Button variant="outline" className="h-12 w-full rounded-2xl" onClick={() => inputRef.current?.click()}><FolderOpen className="size-5" />從相簿或檔案選擇</Button></div>
              )}
            </>
          )}
        </section>
      </div>
    </main>
  );
}

function VehicleTypeSelection({ onSelect }: { onSelect: (type: VehicleType) => void }) {
  return <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8"><div className="mx-auto min-h-dvh w-full max-w-md bg-white sm:rounded-[32px]"><header className="bg-[#101d1a] px-5 py-4 text-white"><Link href="/capture" aria-label="返回拍照規則"><ArrowLeft /></Link></header><section className="px-5 py-8"><p className="text-sm font-semibold text-[#2d6d5d]">步驟 1</p><h1 className="mt-2 text-[30px] font-semibold">這次拍攝的是哪種車型？</h1><p className="mt-3 text-[#62756d]">我們會在第 4–7 張車身照顯示對應的透明導引框。</p><div className="mt-7 grid gap-4"><button type="button" className="rounded-[28px] border-2 border-[#dce9e1] p-5 text-left" onClick={() => onSelect('sedan')}><Car className="size-6" /><strong className="mt-3 block text-xl">轎車</strong></button><button type="button" className="rounded-[28px] border-2 border-[#dce9e1] p-5 text-left" onClick={() => onSelect('suv')}><Truck className="size-6" /><strong className="mt-3 block text-xl">休旅車</strong></button></div></section></div></main>;
}

function DamageChoice({ normalPhotoCount, damagePhotoCount, onAddDamage, onContinue, creatingCase, error }: { normalPhotoCount: number; damagePhotoCount: number; onAddDamage: () => void; onContinue: () => void; creatingCase: boolean; error: string }) {
  return <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8"><div className="mx-auto min-h-dvh w-full max-w-md bg-white sm:rounded-[32px]"><header className="bg-[#101d1a] px-5 py-4 text-white"><p className="font-semibold">基本拍攝完成</p><p className="text-sm text-white/55">7 個步驟皆已確認</p></header><section className="px-5 py-10"><h1 className="text-[30px] font-semibold">是否有需要補拍的車損？</h1><p className="mt-3 text-[#62756d]">損壞照片為選填，最多可補充 4 張。</p><div className="mt-5 rounded-2xl bg-[#eff6f1] p-4 text-sm">已儲存 {normalPhotoCount} 張基本照片{damagePhotoCount ? `及 ${damagePhotoCount} 張損壞照片` : ''}。</div>{error && <div role="alert" className="mt-4 rounded-2xl bg-red-50 p-4 text-sm text-red-700">{error}</div>}<div className="mt-8 space-y-3"><Button variant="outline" className="h-16 w-full rounded-2xl" onClick={onAddDamage} disabled={creatingCase || damagePhotoCount >= 4}><Plus className="size-5" />新增損壞照片（選填）</Button><Button className="h-16 w-full rounded-2xl bg-[#173e35] text-white" onClick={onContinue} disabled={creatingCase}>{creatingCase ? <LoaderCircle className="size-5 animate-spin" /> : <Check className="size-5" />}建立車況案件</Button></div></section></div></main>;
}

function getVehicleOverlay(vehicleType: VehicleType, shotType: string) {
  const isRear = shotType.startsWith('rear_');
  const isRight = shotType.includes('_right_');
  return { src: `/overlays/${vehicleType}-${isRear ? 'rear' : 'front'}.png`, flip: isRight };
}

async function captureVideoFrame(video: HTMLVideoElement | null, canvas: HTMLCanvasElement | null, quality: number): Promise<Blob | null> {
  if (!video || !canvas || !video.videoWidth || !video.videoHeight) return null;
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));
}

async function createThumbnail(blob: Blob): Promise<string | null> {
  const objectUrl = URL.createObjectURL(blob);
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error('thumbnail_failed'));
      image.src = objectUrl;
    });
    const canvas = document.createElement('canvas');
    canvas.width = 320;
    canvas.height = 240;
    const context = canvas.getContext('2d');
    if (!context) return null;
    const scale = Math.max(canvas.width / image.width, canvas.height / image.height);
    const width = image.width * scale;
    const height = image.height * scale;
    context.drawImage(image, (canvas.width - width) / 2, (canvas.height - height) / 2, width, height);
    return canvas.toDataURL('image/jpeg', 0.64);
  } catch {
    return null;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function Tip({ icon, label }: { icon: React.ReactNode; label: string }) {
  return <div className="flex min-w-0 flex-col items-center gap-1.5 rounded-2xl bg-[#eff6f1] px-2 py-3 text-center text-sm font-medium text-[#355f54]"><span className="[&_svg]:size-4">{icon}</span><span>{label}</span></div>;
}

function formatRequestError(error: unknown, operation: string) {
  if (error instanceof ModuleERequestError) {
    if (error.kind === 'http') return `${operation}失敗（HTTP ${error.status}）：${error.message}`;
    return `${operation}失敗：無法連線至後端服務。`;
  }
  return `${operation}失敗，請稍後重試。`;
}
