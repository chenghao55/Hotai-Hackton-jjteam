'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  ArrowLeft,
  Camera,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  ImagePlus,
  LoaderCircle,
  RotateCcw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { Button, buttonVariants } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import {
  scenarioLabels,
  type AnalysisResult,
  type ScenarioKey,
} from '@/lib/prototype';

type View = 'checklist' | 'camera' | 'analyzing' | 'result';

const tasks = [
  { title: '車頭左前方 45°', note: '包含車牌與完整保桿', done: true },
  { title: '車尾右後方 45°', note: '距離車身約 2–3 公尺', done: false },
  { title: '駕駛座與儀表板', note: '保持車內光線充足', done: false },
  { title: '後座與腳踏區', note: '拍到座椅及地板全貌', done: false },
];

const issueText: Record<string, string> = {
  blur: '畫面模糊',
  wrong_angle: '拍攝角度偏移',
};

const captureRules = [
  {
    title: '依照畫面順序拍攝',
    description: '請依系統指示完成車頭、車尾、車身兩側、駕駛座、後座及行李廂，請勿跳過任何指定角度。',
  },
  {
    title: '保持正確角度與距離',
    description: '拍攝車外時，建議與車身保持約 2 至 3 公尺距離，並依提示以 45 度角拍攝，確保完整車身都在畫面內。',
  },
  {
    title: '確認光線充足',
    description: '避免逆光、過暗或強烈反光。夜間請移至有照明的位置，必要時開啟手機閃光燈。',
  },
  {
    title: '照片必須清楚',
    description: '拍攝時請拿穩手機並等待對焦完成。若照片模糊、晃動或遭手指遮擋，系統會請你重新拍攝。',
  },
  {
    title: '保留車牌與車況細節',
    description: '車牌、保險桿、輪圈及車身表面應清楚可見；若發現刮痕、凹陷或污損，請另外近距離補拍。',
  },
  {
    title: '整理並拍攝車內',
    description: '請先帶走個人物品，再完整拍攝座椅、儀表板、腳踏區及行李廂，避免物品遮住需要檢查的位置。',
  },
  {
    title: '使用原始照片',
    description: '請直接使用手機相機拍攝，不要套用濾鏡、裁切、塗改或使用通訊軟體壓縮後的圖片。',
  },
  {
    title: '注意拍攝安全',
    description: '請先將車輛停妥並確認周遭安全，不要站在車道中央或一邊駕駛一邊操作手機。',
  },
];

export default function CapturePage() {
  const [hasReadRules, setHasReadRules] = useState(false);
  const [hasReachedRulesEnd, setHasReachedRulesEnd] = useState(false);
  const [rulesError, setRulesError] = useState('');
  const rulesScrollRef = useRef<HTMLDivElement>(null);

  function updateRulesEndState() {
    const element = rulesScrollRef.current;
    if (!element) return;
    if (element.scrollHeight === 0 || element.clientHeight === 0) return;

    const reachedEnd = element.scrollTop + element.clientHeight >= element.scrollHeight - 4;
    if (reachedEnd) {
      setHasReachedRulesEnd(true);
      setRulesError('');
    }
  }

  useEffect(() => {
    updateRulesEndState();
    window.addEventListener('resize', updateRulesEndState);
    return () => window.removeEventListener('resize', updateRulesEndState);
  }, []);

  function changeRulesConfirmation(checked: boolean) {
    if (checked && !hasReachedRulesEnd) {
      setRulesError('請先詳細閱讀所有條款');
      return;
    }

    setHasReadRules(checked);
    setRulesError('');
  }

  return (
    <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8">
      <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col overflow-x-hidden bg-white shadow-[0_0_50px_rgb(16_37_31/10%)] sm:min-h-[calc(100dvh-4rem)] sm:rounded-[32px]">
        <header className="bg-[#101d1a] px-5 py-4 text-white">
          <div className="flex items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-[#c9ff38] text-[#10251f]">
                <ShieldCheck className="size-6" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-lg font-semibold tracking-tight">車況管家</p>
                <p className="text-sm text-white/55">iRent AI Prototype</p>
              </div>
            </div>
            <span className="shrink-0 rounded-full border border-white/15 px-3 py-1.5 text-sm text-white/70">拍攝者介面</span>
          </div>
        </header>

        <section className="flex flex-1 flex-col px-5 pb-6 pt-5 sm:px-7">
          <div>
            <p className="text-sm font-semibold text-[#2d6d5d]">拍攝前確認</p>
            <h1 className="mt-1.5 text-[28px] font-semibold leading-tight tracking-tight">開始拍照前，<br />請先閱讀拍攝規則</h1>
            <p className="mt-2 text-base leading-6 text-[#62756d]">依照規則拍攝，可減少照片模糊、角度不完整及重拍的情況。</p>
          </div>

          <div className="relative mt-4 flex h-[50dvh] min-h-[340px] max-h-[520px] shrink-0 flex-col overflow-hidden rounded-[26px] border border-[#cbe5d7] bg-[#effaf3] shadow-[inset_0_1px_0_rgb(255_255_255/80%)]">
            <div className="flex items-center gap-3 border-b border-[#cbe5d7] bg-[#ddf5e6] px-5 py-3">
              <span className="grid size-9 place-items-center rounded-xl bg-[#173e35] text-[#c9ff38]">
                <Camera className="size-5" aria-hidden="true" />
              </span>
              <div>
                <h2 className="font-semibold">拍照規則及流程</h2>
                <p className="text-sm text-[#587066]">共 8 項，請向下閱讀完整內容</p>
              </div>
            </div>

            <div
              ref={rulesScrollRef}
              data-testid="rules-scroll-area"
              onScroll={updateRulesEndState}
              className="min-h-0 flex-1 touch-pan-y overflow-y-scroll overscroll-contain px-5 py-1 [scrollbar-color:#7aa291_#dcefe4] [scrollbar-width:auto] [-webkit-overflow-scrolling:touch]"
            >
              <ol className="divide-y divide-[#cbe5d7]">
                {captureRules.map((rule, index) => (
                  <li key={rule.title} className="flex gap-3 py-4">
                    <span className="grid size-7 shrink-0 place-items-center rounded-full bg-[#c9ff38] text-sm font-bold text-[#173e35]" aria-hidden="true">{index + 1}</span>
                    <div>
                      <h3 className="text-base font-semibold">{rule.title}</h3>
                      <p className="mt-1 text-[15px] leading-6 text-[#50675e]">{rule.description}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          <div className="mt-4 flex items-center gap-3 rounded-2xl px-1 py-2 text-base font-medium leading-6">
            <Checkbox
              aria-labelledby="rules-confirmation-label"
              aria-describedby={rulesError ? 'rules-confirmation-error' : undefined}
              aria-invalid={Boolean(rulesError)}
              checked={hasReadRules}
              onCheckedChange={(checked) => changeRulesConfirmation(checked === true)}
              className="size-7 rounded-full border-2 border-[#49675e] bg-white text-[#10251f] data-checked:border-[#c9ff38] data-checked:bg-[#c9ff38] [&_svg]:size-4"
            />
            <span id="rules-confirmation-label">我已經詳細閱讀拍照規則及流程</span>
          </div>

          {rulesError && (
            <p id="rules-confirmation-error" role="alert" className="mt-1 px-1 text-sm font-medium text-red-600">
              {rulesError}
            </p>
          )}

          {hasReadRules ? (
            <Link
              href="/capture/camera"
              className={cn(buttonVariants(), 'mt-3 h-14 w-full rounded-2xl bg-[#173e35] text-base font-semibold text-white shadow-[0_8px_20px_rgb(23_62_53/18%)] hover:bg-[#22594b] focus-visible:ring-[#8db6aa]')}
            >
              開始拍照 <ArrowRight className="size-5" aria-hidden="true" />
            </Link>
          ) : (
            <button
              type="button"
              disabled
              className={cn(buttonVariants(), 'mt-3 h-14 w-full cursor-not-allowed rounded-2xl bg-[#d7ddd9] text-base font-semibold text-[#87928d] shadow-none disabled:opacity-100')}
            >
              開始拍照 <ArrowRight className="size-5" aria-hidden="true" />
            </button>
          )}
        </section>
      </div>
    </main>
  );
}

export function LegacyCapturePage() {
  const [view, setView] = useState<View>('checklist');
  const [scenario, setScenario] = useState<ScenarioKey>('normal');
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  function pickFile(file?: File) {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setError('請選擇 JPG、PNG 或 HEIC 圖片。');
      return;
    }
    if (file.size > 12 * 1024 * 1024) {
      setError('圖片超過 12 MB，請縮小後再試。');
      return;
    }
    setError('');
    setPreview(URL.createObjectURL(file));
  }

  async function analyze() {
    setView('analyzing');
    setError('');
    try {
      const body = new FormData();
      body.set('stage', 'return');
      body.set('scenario', scenario);
      const response = await fetch('/api/analyze', { method: 'POST', body });
      if (!response.ok) throw new Error('analysis failed');
      setResult(await response.json());
      setView('result');
    } catch {
      setError('目前無法完成分析，照片已保留，請稍後重試。');
      setView('camera');
    }
  }

  function restart() {
    setResult(null);
    setPreview(null);
    setError('');
    setView('camera');
  }

  return (
    <main className="min-h-screen bg-[#eef3ef] text-[#14251f]">
      <div className="mx-auto min-h-screen max-w-md bg-white shadow-[0_0_50px_rgb(20_37_31/8%)]">
        <header className="sticky top-0 z-10 border-b bg-white/95 px-5 py-4 backdrop-blur">
          <div className="flex items-center justify-between">
            <Link href="/" aria-label="回到首頁" className="grid size-8 place-items-center rounded-lg transition hover:bg-muted"><ArrowLeft className="size-4" /></Link>
            <div className="text-center">
              <p className="font-semibold">還車車況檢查</p>
              <p className="text-xs text-muted-foreground">車輛 7A21</p>
            </div>
            <span className="grid size-9 place-items-center rounded-xl bg-[#eaffaa] text-[#173e35]"><ShieldCheck className="size-5" /></span>
          </div>
        </header>

        {view === 'checklist' && (
          <section className="px-5 pb-28 pt-6">
            <div className="rounded-3xl bg-[#173e35] p-5 text-white">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">拍攝進度</span>
                <span className="text-[#dfff78]">1 / 4</span>
              </div>
              <Progress value={25} className="mt-4 h-2 bg-white/15 [&>div]:bg-[#c9ff38]" />
              <p className="mt-4 text-sm leading-6 text-white/65">AI 會在上傳當下檢查角度、距離與清晰度，問題照片可立即補拍。</p>
            </div>

            <h1 className="mb-3 mt-7 text-xl font-semibold">依順序完成拍攝</h1>
            <div className="space-y-3">
              {tasks.map((task, index) => (
                <button
                  key={task.title}
                  onClick={() => !task.done && setView('camera')}
                  className="flex w-full items-center gap-4 rounded-2xl border bg-white p-4 text-left transition hover:border-[#86a91e] disabled:opacity-60"
                  disabled={task.done}
                >
                  <span className={`grid size-10 shrink-0 place-items-center rounded-xl ${task.done ? 'bg-[#173e35] text-[#c9ff38]' : index === 1 ? 'bg-[#eaffaa] text-[#173e35]' : 'bg-muted text-muted-foreground'}`}>
                    {task.done ? <Check className="size-5" /> : <Camera className="size-5" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{task.title}</span>
                    <span className="mt-0.5 block text-sm text-muted-foreground">{task.note}</span>
                  </span>
                  {index === 1 && <ChevronRight className="size-5 text-muted-foreground" />}
                </button>
              ))}
            </div>
          </section>
        )}

        {view === 'camera' && (
          <section className="px-5 pb-28 pt-6">
            <div className="mb-5 flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-[#2d6d5d]">第 2 張，共 4 張</p>
                <h1 className="mt-1 text-2xl font-semibold">車尾右後方 45°</h1>
              </div>
              <Badge className="bg-[#eaffaa] text-[#173e35]">AI 拍攝教練</Badge>
            </div>

            <div className="relative grid aspect-[4/3] place-items-center overflow-hidden rounded-[28px] bg-[#15251f]">
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preview} alt="待分析照片預覽" className="size-full object-cover" />
              ) : (
                <div className="text-center text-white/70">
                  <div className="mx-auto mb-4 grid size-16 place-items-center rounded-full border border-white/15 bg-white/10"><Camera className="size-7" /></div>
                  <p className="font-medium text-white">將車尾完整放入引導框</p>
                  <p className="mt-1 text-sm">距離車身約 2–3 公尺</p>
                </div>
              )}
              <div className="pointer-events-none absolute inset-8 rounded-[22px] border-2 border-dashed border-[#c9ff38]/75" />
              <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black/55 px-3 py-1.5 text-xs text-white backdrop-blur">車牌與右後保桿需清楚可見</div>
            </div>

            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="sr-only"
              onChange={(event) => pickFile(event.target.files?.[0])}
            />
            <div className="mt-4 grid grid-cols-2 gap-3">
              <Button variant="outline" className="h-12" onClick={() => inputRef.current?.click()}><ImagePlus />{preview ? '更換照片' : '選擇照片'}</Button>
              <Button className="h-12 bg-[#173e35] text-white hover:bg-[#22594b]" onClick={() => inputRef.current?.click()}><Camera />開啟相機</Button>
            </div>

            {error && <div role="alert" className="mt-4 flex gap-3 rounded-2xl bg-red-50 p-4 text-sm text-red-700"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{error}</div>}

            <div className="mt-7 rounded-2xl border bg-[#f7faf7] p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><Sparkles className="size-4 text-[#587e13]" />Prototype 情境</div>
              <div className="grid grid-cols-2 gap-2">
                {(Object.keys(scenarioLabels) as ScenarioKey[]).map((key) => (
                  <button key={key} onClick={() => setScenario(key)} className={`rounded-xl border px-3 py-2 text-sm font-medium transition ${scenario === key ? 'border-[#355f54] bg-[#173e35] text-white' : 'bg-white hover:border-[#86a91e]'}`}>{scenarioLabels[key]}</button>
                ))}
              </div>
              <p className="mt-3 text-xs leading-5 text-muted-foreground">此控制僅供初賽 Demo 固定重現四種結果，正式版由 AI API 決定。</p>
            </div>

            <Button className="mt-5 h-13 w-full bg-[#c9ff38] text-base font-semibold text-[#10251f] hover:bg-[#ddff7d]" onClick={analyze}>送出並即時檢查 <ChevronRight /></Button>
          </section>
        )}

        {view === 'analyzing' && (
          <section className="grid min-h-[70vh] place-items-center px-8 text-center">
            <div>
              <span className="mx-auto grid size-20 place-items-center rounded-[26px] bg-[#eaffaa]"><LoaderCircle className="size-9 animate-spin text-[#173e35]" /></span>
              <h1 className="mt-6 text-2xl font-semibold">AI 正在檢查照片</h1>
              <p className="mt-2 leading-7 text-muted-foreground">依序檢查清晰度、拍攝角度與新增異常，通常只需要幾秒鐘。</p>
            </div>
          </section>
        )}

        {view === 'result' && result && (
          <section className="px-5 pb-28 pt-8">
            <div className={`rounded-[28px] p-6 ${result.recommended_action === 'pass' ? 'bg-[#173e35] text-white' : 'bg-[#fff4d8] text-[#3b2b12]'}`}>
              <span className={`grid size-14 place-items-center rounded-2xl ${result.recommended_action === 'pass' ? 'bg-[#c9ff38] text-[#173e35]' : 'bg-[#ffd76a] text-[#563a00]'}`}>
                {result.recommended_action === 'pass' ? <CheckCircle2 className="size-7" /> : <AlertTriangle className="size-7" />}
              </span>
              <h1 className="mt-5 text-2xl font-semibold">{result.recommended_action === 'reshoot' ? '需要補拍這張照片' : result.recommended_action === 'pass' ? '照片與車況檢查完成' : '異常已安全回報'}</h1>
              <p className={`mt-2 text-sm leading-6 ${result.recommended_action === 'pass' ? 'text-white/70' : 'text-[#6b5428]'}`}>
                {result.recommended_action === 'reshoot' ? '這張照片尚不足以可靠判讀，請依下方提示重新拍攝。' : result.recommended_action === 'pass' ? 'AI 未發現明顯新增異常，本次結果已留存。' : '系統不會直接判定責任，案件已送交營運人員覆核。'}
              </p>
            </div>

            <div className="mt-5 rounded-2xl border p-5">
              <div className="flex items-center justify-between">
                <span className="font-semibold">AI 判讀摘要</span>
                <Badge variant="outline">信心 {Math.round(result.confidence * 100)}%</Badge>
              </div>
              <div className="mt-4 space-y-3 text-sm">
                <ResultRow label="拍攝品質" ok={result.capture_quality.passed} value={result.capture_quality.passed ? '通過' : result.capture_quality.issues.map((issue) => issueText[issue] ?? issue).join('、')} />
                <ResultRow label="新增車損" ok={!result.vehicle_change.detected} value={result.vehicle_change.findings[0] ?? '未發現明顯變化'} />
                <ResultRow label="車內整潔" ok={result.cleanliness.level !== 'dirty'} value={result.cleanliness.level === 'dirty' ? '髒污，需立即清潔' : result.cleanliness.level === 'clean' ? '乾淨' : '普通'} />
              </div>
            </div>

            {result.vehicle_change.findings.length > 0 && <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900"><strong>AI觀察：</strong>{result.vehicle_change.findings[0]}</div>}
            {result.cleanliness.findings.length > 0 && <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900"><strong>整潔觀察：</strong>{result.cleanliness.findings[0]}</div>}

            {result.recommended_action === 'reshoot' ? (
              <Button className="mt-6 h-13 w-full bg-[#173e35] text-white hover:bg-[#22594b]" onClick={restart}><RotateCcw />依提示重新拍攝</Button>
            ) : (
              <Button className="mt-6 h-13 w-full bg-[#173e35] text-white hover:bg-[#22594b]" onClick={() => setView('checklist')}><Check />完成並返回任務</Button>
            )}
          </section>
        )}
      </div>
    </main>
  );
}

function ResultRow({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-start gap-3 rounded-xl bg-muted/65 p-3">
      {ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-700" /> : <Circle className="mt-0.5 size-4 shrink-0 fill-amber-400 text-amber-500" />}
      <div><span className="text-muted-foreground">{label}</span><p className="mt-0.5 font-medium text-foreground">{value}</p></div>
    </div>
  );
}
