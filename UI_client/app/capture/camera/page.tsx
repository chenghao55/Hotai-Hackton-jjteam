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
  readCaptureResult,
  readCaptureThumbnails,
  saveCaptureDraft,
  saveCaptureResult,
  saveCaptureThumbnails,
  type CaptureStep,
  type StoredAnalysisResult,
} from '@/lib/capture-flow';
import type { ScenarioKey } from '@/lib/prototype';

type CapturedPhoto = { step: CaptureStep; blob: Blob; thumbnail: string | null };
type AppealContext = { caseId: string; shotType: string } | null;
type CaptureMode = 'normal' | 'damage';
type VehicleType = 'sedan' | 'suv';

export default function CameraPage() {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [currentPhoto, setCurrentPhoto] = useState<Blob | null>(null);
  const [capturedPhotos, setCapturedPhotos] = useState<CapturedPhoto[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [error, setError] = useState('');
  const [analysisError, setAnalysisError] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [cameraStatus, setCameraStatus] = useState<'idle' | 'starting' | 'live'>('idle');
  const [appeal, setAppeal] = useState<AppealContext>(null);
  const [captureMode, setCaptureMode] = useState<CaptureMode>('normal');
  const [vehicleType, setVehicleType] = useState<VehicleType | null>(null);
  const [showDamageChoice, setShowDamageChoice] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [videoDevices, setVideoDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const caseId = params.get('case_id');
    const shotType = params.get('shot_type');
    if (params.get('mode') === 'appeal' && caseId && shotType) {
      setAppeal({ caseId, shotType });
      const storedVehicleType = sessionStorage.getItem('capture-vehicle-type');
      if (storedVehicleType === 'sedan' || storedVehicleType === 'suv') setVehicleType(storedVehicleType);
    }
    setInitialized(true);
  }, []);

  const activeSteps = useMemo(() => {
    if (!appeal) return captureMode === 'damage' ? damageCaptureSteps : captureSteps;
    return [captureSteps.find((step) => step.shotType === appeal.shotType) ?? captureSteps[0]];
  }, [appeal, captureMode]);
  const currentStep = activeSteps[currentIndex] ?? activeSteps[0];
  const progress = ((currentIndex + 1) / activeSteps.length) * 100;
  const returnHref = appeal ? `/capture/result?case_id=${encodeURIComponent(appeal.caseId)}` : '/capture';
  const overlay = !appeal && captureMode === 'normal' && currentIndex >= 4 && vehicleType
    ? getVehicleOverlay(vehicleType, currentStep.shotType)
    : null;
  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  function stopCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraStatus('idle');
  }

  function clearCurrentPhoto() {
    setPreviewUrl(null);
    setCurrentPhoto(null);
    setAnalysisError('');
    if (inputRef.current) inputRef.current.value = '';
  }

  function chooseVehicle(type: VehicleType) {
    sessionStorage.setItem('capture-vehicle-type', type);
    setVehicleType(type);
  }

  function advanceWithoutPhoto() {
    stopCamera();
    clearCurrentPhoto();

    if (captureMode === 'normal') {
      if (currentIndex < captureSteps.length - 1) {
        setCurrentIndex((value) => value + 1);
      } else {
        setShowDamageChoice(true);
      }
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function startDamageCapture() {
    setCaptureMode('damage');
    setCurrentIndex(0);
    setShowDamageChoice(false);
    clearCurrentPhoto();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function continueToAnalysis(photos = capturedPhotos) {
    const thumbnails = Object.fromEntries(photos.filter((photo) => photo.thumbnail).map((photo) => [photo.step.shotType, photo.thumbnail as string]));
    saveCaptureDraft({
      photoCount: photos.length,
      normalPhotoCount: photos.filter((photo) => !photo.step.shotType.startsWith('damage_')).length,
      damagePhotoCount: photos.filter((photo) => photo.step.shotType.startsWith('damage_')).length,
      thumbnails,
    });
    window.location.assign('/capture/analysis-demo');
  }

  async function startCamera(requestedDeviceId?: string) {
    setError('');
    clearCurrentPhoto();
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('這個瀏覽器無法直接使用攝影機，請改用下方的「從相簿選擇」。');
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
      if (activeDeviceId) {
        sessionStorage.setItem('capture-camera-device-id', activeDeviceId);
      }
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraStatus('live');
    } catch (cameraError) {
      stopCamera();
      const denied = cameraError instanceof DOMException && (cameraError.name === 'NotAllowedError' || cameraError.name === 'SecurityError');
      setError(denied
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

  function takePhoto() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth || !video.videoHeight) {
      setError('攝影機仍在準備中，請稍候再按一次快門。');
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext('2d');
    if (!context) {
      setError('照片擷取失敗，請重新拍攝。');
      return;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob) {
        setError('照片擷取失敗，請重新拍攝。');
        return;
      }
      setError('');
      setCurrentPhoto(blob);
      setPreviewUrl(URL.createObjectURL(blob));
      stopCamera();
    }, 'image/jpeg', 0.92);
  }

  function selectPhoto(file?: File) {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setError('請拍攝或選擇圖片檔案。');
      return;
    }
    if (file.size > 12 * 1024 * 1024) {
      setError('照片超過 12 MB，請重新拍攝。');
      return;
    }
    setError('');
    stopCamera();
    setCurrentPhoto(file);
    setPreviewUrl(URL.createObjectURL(file));
  }

  async function confirmPhoto(action: 'continue' | 'finish' = 'continue') {
    if (!currentPhoto) return;
    const thumbnail = await createThumbnail(currentPhoto);
    const completed = [...capturedPhotos, { step: currentStep, blob: currentPhoto, thumbnail }];

    if (appeal) {
      await analyzePhotos(completed);
      return;
    }

    if (action === 'finish') {
      continueToAnalysis(completed);
      return;
    }

    if (captureMode === 'normal' && currentIndex === captureSteps.length - 1) {
      setCapturedPhotos(completed);
      setShowDamageChoice(true);
      clearCurrentPhoto();
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    if (currentIndex < activeSteps.length - 1) {
      setCapturedPhotos(completed);
      setCurrentIndex((value) => value + 1);
      clearCurrentPhoto();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  async function analyzePhotos(photos: CapturedPhoto[]) {
    setIsAnalyzing(true);
    setAnalysisError('');
    const formData = new FormData();
    formData.append('stage', 'return');
    formData.append('scenario', resolvePrototypeScenario(appeal));
    formData.append('shot_types', JSON.stringify(photos.map((photo) => photo.step.shotType)));
    if (appeal) formData.append('appeal_of', appeal.caseId);
    photos.forEach((photo) => formData.append('current_images', photo.blob, `${photo.step.shotType}.jpg`));

    try {
      const response = await fetch('/api/analyze', { method: 'POST', body: formData });
      if (!response.ok) throw new Error('analysis_failed');
      const result = await response.json() as StoredAnalysisResult;
      saveCaptureResult(result);
      const oldThumbnails = appeal ? readCaptureThumbnails(result.case_id) : {};
      const newThumbnails = Object.fromEntries(photos.filter((photo) => photo.thumbnail).map((photo) => [photo.step.shotType, photo.thumbnail as string]));
      saveCaptureThumbnails(result.case_id, { ...oldThumbnails, ...newThumbnails });
      if (appeal) sessionStorage.setItem(`capture-appeal-submitted:${result.case_id}`, 'true');
      window.location.assign(`/capture/result?case_id=${encodeURIComponent(result.case_id)}`);
    } catch {
      setIsAnalyzing(false);
      setAnalysisError('車況分析暫時無法完成，照片仍保留在本頁，請重新送出分析。');
    }
  }

  if (!initialized) return null;

  if (!appeal && !vehicleType) {
    return <VehicleTypeSelection onSelect={chooseVehicle} />;
  }

  if (!appeal && showDamageChoice) {
    return <DamageChoice normalPhotoCount={capturedPhotos.length} onAddDamage={startDamageCapture} onContinue={() => continueToAnalysis()} />;
  }

  return (
    <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8">
      <div className="mx-auto min-h-dvh w-full max-w-md overflow-hidden bg-white shadow-[0_0_50px_rgb(16_37_31/10%)] sm:min-h-[calc(100dvh-4rem)] sm:rounded-[32px]">
        <header className="bg-[#101d1a] px-5 py-4 text-white">
          <div className="grid grid-cols-[44px_1fr_44px] items-center">
            <Link href={returnHref} aria-label={appeal ? '返回分析結果' : '返回拍照規則'} className="grid size-11 place-items-center rounded-2xl border border-white/15 bg-white/10 transition hover:bg-white/15 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-[#c9ff38]/60">
              <ArrowLeft className="size-5" aria-hidden="true" />
            </Link>
            <div className="text-center">
              <p className="font-semibold">{appeal ? '申訴補拍' : '車況拍攝'}</p>
              <p className="mt-0.5 text-sm text-white/55">{appeal ? `案件 ${appeal.caseId}` : '車輛 7A21'}</p>
            </div>
            <span className="grid size-11 place-items-center rounded-2xl bg-[#c9ff38] text-[#10251f]"><ShieldCheck className="size-5" aria-hidden="true" /></span>
          </div>
        </header>

        <section className="px-5 pb-8 pt-5 sm:px-7">
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm font-semibold text-[#2d6d5d]">{appeal ? '問題角度補拍' : captureMode === 'damage' ? `損壞照片 ${currentIndex + 1}／最多 4 張` : `基本照片 ${currentIndex + 1}／8`}</p>
            <p className="text-sm font-medium text-[#62756d]">{Math.round(progress)}%</p>
          </div>
          <Progress value={progress} className="mt-2 h-2 bg-[#dce9e1] [&>div]:bg-[#c9ff38]" />
          <h1 className="mt-5 text-[28px] font-semibold leading-tight tracking-tight">{currentStep.title}</h1>
          <p className="mt-2 text-base leading-6 text-[#62756d]">{appeal ? '請針對 AI 指出的問題部位重新拍攝；其他已通過的照片會保留。' : currentStep.description}</p>

          {!appeal && captureMode === 'damage' && (
            <div className="mt-4 flex items-start gap-3 rounded-2xl border border-[#cfe1d7] bg-[#eff6f1] p-4 text-sm leading-6 text-[#355f54]">
              <ShieldCheck className="mt-0.5 size-5 shrink-0 text-[#2d6d5d]" aria-hidden="true" />
              <p><strong className="block text-[#173e35]">損壞照片為選填</strong>拍 1 張即可進入下一流程，最多可補充 4 張；請只拍本次發現的刮痕、凹痕或破損。</p>
            </div>
          )}

          {isAnalyzing ? (
            <div className="mt-8 grid min-h-[360px] place-items-center rounded-[28px] bg-[#10251f] px-8 text-center text-white shadow-[0_12px_32px_rgb(16_37_31/18%)]" role="status">
              <div>
                <span className="mx-auto grid size-20 place-items-center rounded-full bg-white/10 text-[#c9ff38]"><LoaderCircle className="size-10 animate-spin" aria-hidden="true" /></span>
                <h2 className="mt-5 text-2xl font-semibold">正在分析車況</h2>
                <p className="mt-2 text-base leading-6 text-white/65">正在檢查拍攝品質、車身變化與車內清潔狀況，請不要關閉頁面。</p>
              </div>
            </div>
          ) : (
            <>
              <div className="relative mt-5 aspect-[4/3] overflow-hidden rounded-[28px] bg-[#10251f] shadow-[0_12px_32px_rgb(16_37_31/18%)]">
                {previewUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={previewUrl} alt={`${currentStep.title}照片預覽`} className="size-full object-cover" />
                ) : cameraStatus === 'live' || cameraStatus === 'starting' ? (
                  <>
                    <video ref={videoRef} data-testid="live-camera" aria-label="即時攝影機預覽" className="relative z-0 size-full object-cover" autoPlay muted playsInline />
                    {cameraStatus === 'starting' && <div className="absolute inset-0 z-10 grid place-items-center bg-[#10251f]/85 text-center text-white"><div><LoaderCircle className="mx-auto size-8 animate-spin text-[#c9ff38]" aria-hidden="true" /><p className="mt-3 font-semibold">正在開啟攝影機…</p></div></div>}
                    {cameraStatus === 'live' && overlay && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={overlay.src}
                        alt=""
                        data-testid="vehicle-alignment-overlay"
                        className="pointer-events-none absolute inset-0 z-20 size-full object-contain p-2 opacity-75 drop-shadow-[0_0_10px_rgb(201_255_56/70%)]"
                        style={{ transform: overlay.flip ? 'scaleX(-1)' : undefined }}
                        aria-hidden="true"
                      />
                    )}
                  </>
                ) : (
                  <div className="grid size-full place-items-center px-8 text-center text-white"><div><span className="mx-auto grid size-16 place-items-center rounded-full border border-white/15 bg-white/10 text-[#c9ff38]"><Camera className="size-8" aria-hidden="true" /></span><p className="mt-4 text-lg font-semibold">將拍攝部位對準框線</p><p className="mt-1 text-sm leading-6 text-white/60">橫向拍攝並保持手機穩定</p></div></div>
                )}
                <div className="pointer-events-none absolute inset-5 z-30 rounded-[22px] border-2 border-dashed border-[#c9ff38]/80" aria-hidden="true" />
                <span className="pointer-events-none absolute bottom-4 left-1/2 z-40 -translate-x-1/2 whitespace-nowrap rounded-full bg-black/60 px-3 py-1.5 text-sm text-white backdrop-blur" aria-hidden="true">{currentStep.frameLabel}</span>
              </div>

              <canvas ref={canvasRef} className="hidden" aria-hidden="true" />
              <div className="mt-4 grid grid-cols-3 gap-2">
                <Tip icon={<MoveUpRight />} label={currentStep.tips[0]} />
                <Tip icon={<ScanLine />} label={currentStep.tips[1]} />
                <Tip icon={<SunMedium />} label={currentStep.tips[2]} />
              </div>
              <input ref={inputRef} data-testid="camera-input" type="file" accept="image/*" capture="environment" className="sr-only" onChange={(event) => selectPhoto(event.target.files?.[0])} />
              {error && <div role="alert" className="mt-4 flex gap-2 rounded-2xl bg-red-50 p-4 text-sm font-medium text-red-700"><AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />{error}</div>}
              {analysisError && <div role="alert" className="mt-4 flex gap-2 rounded-2xl bg-red-50 p-4 text-sm font-medium text-red-700"><AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />{analysisError}</div>}

              {previewUrl ? (
                <div className="mt-5 space-y-3">
                  {appeal ? (
                    <div className="grid grid-cols-2 gap-3">
                        <Button variant="outline" className="h-14 rounded-2xl border-[#b9cbc2] text-base" onClick={() => startCamera()}><ImagePlus className="size-5" />重新拍攝</Button>
                      <Button className="h-14 rounded-2xl bg-[#c9ff38] text-base font-semibold text-[#10251f] hover:bg-[#ddff7d]" onClick={() => confirmPhoto('finish')}><Check className="size-5" />送出申訴照片</Button>
                    </div>
                  ) : captureMode === 'damage' ? (
                    <>
                      <Button variant="outline" className="h-14 w-full rounded-2xl border-[#b9cbc2] text-base" onClick={() => startCamera()}><ImagePlus className="size-5" />重新拍攝</Button>
                      {currentIndex < damageCaptureSteps.length - 1 && (
                        <Button variant="outline" className="h-14 w-full rounded-2xl border-[#7f9a8d] text-base font-semibold text-[#173e35]" onClick={() => confirmPhoto('continue')}><Plus className="size-5" />再新增一張損壞照片</Button>
                      )}
                      <Button className="h-16 w-full rounded-2xl bg-[#173e35] text-base font-semibold text-white shadow-[0_8px_20px_rgb(23_62_53/18%)] hover:bg-[#22594b]" onClick={() => confirmPhoto('finish')}><Check className="size-5" />完成並分析（損壞照片 {currentIndex + 1} 張）</Button>
                    </>
                  ) : (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <Button variant="outline" className="h-14 w-full rounded-2xl border-[#b9cbc2] text-base" onClick={() => startCamera()}><ImagePlus className="size-5" />重新拍攝</Button>
                        <Button className="h-14 rounded-2xl bg-[#c9ff38] text-base font-semibold text-[#10251f] hover:bg-[#ddff7d]" onClick={() => confirmPhoto('continue')}><Check className="size-5" />{currentIndex === captureSteps.length - 1 ? '儲存並繼續' : '儲存並拍下一張'}</Button>
                      </div>
                    </>
                  )}
                </div>
              ) : cameraStatus === 'live' ? (
                <div className="mt-5 space-y-4">
                  {videoDevices.length > 0 && (
                    <div className="rounded-2xl border border-[#dce9e1] bg-[#f7faf8] p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div><p className="text-sm font-semibold text-[#173e35]">鏡頭來源</p><p className="mt-0.5 text-xs text-[#62756d]">預設使用電腦鏡頭</p></div>
                        {videoDevices.length > 1 && <Select value={selectedDeviceId || null} onValueChange={changeCamera}>
                          <SelectTrigger aria-label="選擇鏡頭來源" className="h-10 max-w-[190px] rounded-xl bg-white"><SelectValue placeholder="選擇鏡頭" /></SelectTrigger>
                          <SelectContent>
                            {videoDevices.map((device, index) => <SelectItem key={device.deviceId || index} value={device.deviceId}>{device.label || `攝影機 ${index + 1}`}</SelectItem>)}
                          </SelectContent>
                        </Select>}
                      </div>
                    </div>
                  )}
                  <div className="grid grid-cols-[1fr_72px_1fr] items-center gap-3">
                    <Button variant="outline" className="h-12 rounded-2xl border-[#b9cbc2]" onClick={stopCamera}><CameraOff className="size-5" />取消</Button>
                    <Button aria-label="拍攝照片" className="size-[72px] rounded-full border-[6px] border-white bg-[#c9ff38] text-[#10251f] shadow-[0_0_0_3px_#c9ff38,0_10px_24px_rgb(16_37_31/24%)] hover:bg-[#ddff7d]" onClick={takePhoto}><Camera className="size-7" /></Button>
                    <span className="text-center text-sm font-medium text-[#62756d]">按中央快門</span>
                  </div>
                </div>
              ) : (
                <div className="mt-5 space-y-3">
                  <Button className="h-14 w-full rounded-2xl bg-[#173e35] text-base font-semibold text-white shadow-[0_8px_20px_rgb(23_62_53/18%)] hover:bg-[#22594b]" onClick={() => startCamera()} disabled={cameraStatus === 'starting'}><Camera className="size-5" />開啟即時相機</Button>
                  <Button variant="outline" className="h-12 w-full rounded-2xl border-[#b9cbc2] text-base" onClick={() => inputRef.current?.click()}><FolderOpen className="size-5" />從相簿或檔案選擇</Button>
                </div>
              )}
              <p className="mt-3 text-center text-sm leading-5 text-[#73837c]">預設使用電腦鏡頭；如有多個攝影機，可從鏡頭來源手動切換。</p>
            </>
          )}
        </section>
        {!appeal && captureMode === 'normal' && (
          <Button variant="outline" size="sm" className="fixed bottom-4 right-4 z-30 h-8 rounded-full border-[#9eafa7] bg-white/90 px-3 text-xs font-semibold text-[#536b62] shadow-md backdrop-blur hover:bg-white sm:right-[calc(50%-13rem)]" onClick={advanceWithoutPhoto}>
            跳過此張
          </Button>
        )}
      </div>
    </main>
  );
}

function VehicleTypeSelection({ onSelect }: { onSelect: (type: VehicleType) => void }) {
  return (
    <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8">
      <div className="mx-auto min-h-dvh w-full max-w-md overflow-hidden bg-white shadow-[0_0_50px_rgb(16_37_31/10%)] sm:min-h-[calc(100dvh-4rem)] sm:rounded-[32px]">
        <header className="bg-[#101d1a] px-5 py-4 text-white">
          <div className="grid grid-cols-[44px_1fr_44px] items-center">
            <Link href="/capture" aria-label="返回拍照規則" className="grid size-11 place-items-center rounded-2xl border border-white/15 bg-white/10"><ArrowLeft className="size-5" /></Link>
            <div className="text-center"><p className="font-semibold">選擇車型</p><p className="mt-0.5 text-sm text-white/55">拍攝前設定</p></div>
            <span className="grid size-11 place-items-center rounded-2xl bg-[#c9ff38] text-[#10251f]"><ShieldCheck className="size-5" /></span>
          </div>
        </header>
        <section className="px-5 pb-10 pt-8 sm:px-7">
          <p className="text-sm font-semibold text-[#2d6d5d]">步驟 1</p>
          <h1 className="mt-2 text-[30px] font-semibold leading-tight tracking-tight">這次拍攝的是哪種車型？</h1>
          <p className="mt-3 text-base leading-7 text-[#62756d]">我們會在第 5–8 張車身照顯示對應的透明導引框，讓每次拍攝角度更一致。</p>
          <div className="mt-7 grid gap-4">
            <button type="button" className="group overflow-hidden rounded-[28px] border-2 border-[#dce9e1] bg-[#f7faf8] text-left transition hover:border-[#8eb62a] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#c9ff38]/50" onClick={() => onSelect('sedan')}>
              <div className="relative grid h-40 place-items-center overflow-hidden bg-[#10251f]">
                <img src="/overlays/sedan-front.png" alt="轎車透明框架示意" className="h-full w-full object-contain p-3 opacity-85 transition group-hover:scale-[1.03]" />
              </div>
              <div className="flex items-center gap-4 p-5"><span className="grid size-12 place-items-center rounded-2xl bg-[#dfff8b] text-[#173e35]"><Car className="size-6" /></span><div><strong className="text-xl">轎車</strong><p className="mt-1 text-sm text-[#62756d]">房車、掀背車等低車身車型</p></div></div>
            </button>
            <button type="button" className="group overflow-hidden rounded-[28px] border-2 border-[#dce9e1] bg-[#f7faf8] text-left transition hover:border-[#8eb62a] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#c9ff38]/50" onClick={() => onSelect('suv')}>
              <div className="relative grid h-40 place-items-center overflow-hidden bg-[#10251f]">
                <img src="/overlays/suv-front.png" alt="休旅車透明框架示意" className="h-full w-full object-contain p-3 opacity-85 transition group-hover:scale-[1.03]" />
              </div>
              <div className="flex items-center gap-4 p-5"><span className="grid size-12 place-items-center rounded-2xl bg-[#dfff8b] text-[#173e35]"><Truck className="size-6" /></span><div><strong className="text-xl">休旅車</strong><p className="mt-1 text-sm text-[#62756d]">SUV、跨界休旅等高車身車型</p></div></div>
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}

function DamageChoice({ normalPhotoCount, onAddDamage, onContinue }: { normalPhotoCount: number; onAddDamage: () => void; onContinue: () => void }) {
  return (
    <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8">
      <div className="mx-auto min-h-dvh w-full max-w-md overflow-hidden bg-white shadow-[0_0_50px_rgb(16_37_31/10%)] sm:min-h-[calc(100dvh-4rem)] sm:rounded-[32px]">
        <header className="bg-[#101d1a] px-5 py-4 text-white"><div className="flex items-center justify-between"><div><p className="font-semibold">基本拍攝完成</p><p className="mt-0.5 text-sm text-white/55">8 個步驟皆已確認</p></div><span className="grid size-11 place-items-center rounded-2xl bg-[#c9ff38] text-[#10251f]"><Check className="size-5" /></span></div></header>
        <section className="px-5 py-10 sm:px-7">
          <span className="grid size-16 place-items-center rounded-[22px] bg-[#dfff8b] text-[#173e35]"><Camera className="size-8" /></span>
          <h1 className="mt-6 text-[30px] font-semibold leading-tight">是否有需要補拍的車損？</h1>
          <p className="mt-3 text-base leading-7 text-[#62756d]">損壞照片為選填。如果沒有刮痕、凹痕或破損，可以直接進入下一個流程。</p>
          <div className="mt-5 rounded-2xl bg-[#eff6f1] p-4 text-sm leading-6 text-[#45645b]">已完成 8 個基本拍攝步驟，其中儲存 {normalPhotoCount} 張照片；跳過的步驟不會建立照片。</div>
          <div className="mt-8 space-y-3">
            <Button variant="outline" className="h-16 w-full rounded-2xl border-[#7f9a8d] bg-white text-base font-semibold text-[#173e35]" onClick={onAddDamage}><Plus className="size-5" />新增損壞照片（選填，最多 4 張）</Button>
            <Button className="h-16 w-full rounded-2xl bg-[#173e35] text-base font-semibold text-white shadow-[0_8px_20px_rgb(23_62_53/18%)] hover:bg-[#22594b]" onClick={onContinue}><Check className="size-5" />沒有車損，進入下一步</Button>
          </div>
        </section>
      </div>
    </main>
  );
}

function getVehicleOverlay(vehicleType: VehicleType, shotType: string) {
  const isRear = shotType.startsWith('rear_');
  const isRight = shotType.includes('_right_');
  return {
    src: `/overlays/${vehicleType}-${isRear ? 'rear' : 'front'}.png`,
    flip: isRight,
  };
}

function resolvePrototypeScenario(appeal: AppealContext): ScenarioKey {
  if (appeal) return readCaptureResult(appeal.caseId)?.cleanliness.level === 'dirty' ? 'dirty' : 'damage';
  const stored = sessionStorage.getItem('capture-prototype-scenario');
  return stored === 'blur' || stored === 'damage' || stored === 'dirty' ? stored : 'normal';
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
  return <div className="flex min-w-0 flex-col items-center gap-1.5 rounded-2xl bg-[#eff6f1] px-2 py-3 text-center text-sm font-medium text-[#355f54]"><span className="[&_svg]:size-4" aria-hidden="true">{icon}</span><span>{label}</span></div>;
}
