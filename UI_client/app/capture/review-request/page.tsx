'use client';

import Link from 'next/link';
import { useEffect, useState, type MouseEvent } from 'react';
import { AlertCircle, ArrowLeft, CheckCircle2, FileSearch, Image as ImageIcon, Send } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { Textarea } from '@/components/ui/textarea';
import { analyses, type AnalysisResult, type DamageFinding } from '@/lib/prototype';

export default function ReviewRequestPage() {
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [caseId, setCaseId] = useState(analyses.damage.case_id);
  const [thumbnails, setThumbnails] = useState<Record<string, string>>({});
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const requestedCaseId = new URLSearchParams(window.location.search).get('case_id') || analyses.damage.case_id;
    const resolved = analyses.damage;
    setCaseId(requestedCaseId);
    setResult(resolved);
    setThumbnails({});
  }, []);

  const findings = result?.damage_findings ?? [];
  const backHref = `/capture/result?case_id=${encodeURIComponent(caseId)}`;
  const progressHref = `/capture/review-progress?case_id=${encodeURIComponent(caseId)}`;

  function toggleFinding(id: string, checked: boolean) {
    setSelectedIds((current) => checked ? [...current, id] : current.filter((item) => item !== id));
    setError('');
  }

  function submitReview(event: MouseEvent<HTMLAnchorElement>) {
    if (selectedIds.length === 0) {
      event.preventDefault();
      setError('請至少勾選一項有疑義的 AI 判讀結果');
      return;
    }

    sessionStorage.setItem(`capture-review-request:${caseId}`, JSON.stringify({
      case_id: caseId,
      finding_ids: selectedIds,
      note: note.trim(),
      submitted_at: new Date().toISOString(),
    }));
  }

  return (
    <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8">
      <div className="mx-auto min-h-dvh w-full max-w-md overflow-hidden bg-white shadow-[0_0_50px_rgb(16_37_31/10%)] sm:min-h-[calc(100dvh-4rem)] sm:rounded-[32px]">
        <header className="bg-[#101d1a] px-5 py-4 text-white">
          <div className="grid grid-cols-[44px_1fr_44px] items-center">
            <Link href={backHref} aria-label="返回 AI 判讀結果" className="grid size-11 place-items-center rounded-2xl border border-white/15 bg-white/10 transition hover:bg-white/15 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-[#c9ff38]/60"><ArrowLeft className="size-5" /></Link>
            <div className="text-center"><p className="font-semibold">申請人工覆核</p><p className="mt-0.5 text-sm text-white/55">案件 {caseId}</p></div>
            <span className="grid size-11 place-items-center rounded-2xl bg-[#c9ff38] text-[#10251f]"><FileSearch className="size-5" /></span>
          </div>
        </header>

        <section className="px-5 pb-9 pt-6 sm:px-7">
          <div className="rounded-[26px] border border-[#d9e8df] bg-[#f3f8f5] p-5">
            <p className="text-sm font-semibold text-[#2d6d5d]">選擇需要重新確認的項目</p>
            <h1 className="mt-1 text-[28px] font-semibold leading-tight tracking-tight">你對哪些判讀結果有疑義？</h1>
            <p className="mt-3 text-base leading-7 text-[#62756d]">請勾選希望由專人重新確認的問題，可選擇一項或多項。</p>
          </div>

          <div className="mt-6 space-y-4">
            {findings.map((finding, index) => (
              <FindingReviewCard
                key={finding.id}
                finding={finding}
                index={index}
                thumbnail={thumbnails[finding.shot_type]}
                checked={selectedIds.includes(finding.id)}
                onCheckedChange={(checked) => toggleFinding(finding.id, checked)}
              />
            ))}
          </div>

          <div className="mt-6 rounded-[24px] border border-[#d8e5de] bg-white p-5 shadow-sm">
            <label htmlFor="review-note" className="text-lg font-semibold">補充說明</label>
            <p className="mt-1 text-sm leading-6 text-[#62756d]">請說明你認為判讀不正確的原因，或提供希望審核人員注意的資訊。</p>
            <Textarea id="review-note" value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} placeholder="例如：這道痕跡在租車前就已存在，請協助比對取車時的照片。" className="mt-4 min-h-32 resize-y rounded-2xl border-[#bfd0c7] bg-[#f9fbfa] p-4 leading-6 focus-visible:border-[#2d6d5d] focus-visible:ring-[#2d6d5d]/20" />
            <p className="mt-2 text-right text-sm text-[#84928c]">{note.length} / 500</p>
          </div>

          {error && <div role="alert" className="mt-4 flex items-start gap-2 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-medium leading-6 text-red-700"><AlertCircle className="mt-0.5 size-5 shrink-0" />{error}</div>}

          <Link href={progressHref} onClick={submitReview} className="mt-6 inline-flex min-h-16 w-full items-center justify-center gap-2 rounded-2xl bg-[#c9ff38] px-5 py-3 text-lg font-semibold text-[#10251f] shadow-[0_10px_24px_rgb(113_154_20/18%)] transition hover:bg-[#ddff7d] focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-[#173e35]/30">確認送出人工覆核申請<Send className="size-5" /></Link>
          <p className="mt-3 text-center text-sm leading-6 text-[#73837c]">送出後將進入案件追蹤頁，你可以查看人工覆核進度。</p>
        </section>
      </div>
    </main>
  );
}

function FindingReviewCard({ finding, index, thumbnail, checked, onCheckedChange }: { finding: DamageFinding; index: number; thumbnail?: string; checked: boolean; onCheckedChange: (checked: boolean) => void }) {
  const checkboxId = `review-finding-${finding.id}`;
  return (
    <article className={`overflow-hidden rounded-[24px] border bg-white shadow-sm transition ${checked ? 'border-[#8fb624] ring-2 ring-[#c9ff38]/35' : 'border-[#dce6e0]'}`}>
      <div className="relative aspect-[16/9] bg-[#e8efeb]">
        {thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={thumbnail} alt={`${finding.shot_label}問題照片`} className="size-full object-cover" />
        ) : (
          <div className="grid size-full place-items-center text-center text-[#657970]"><div><ImageIcon className="mx-auto size-8" /><p className="mt-2 text-sm">問題照片縮圖</p></div></div>
        )}
        <span className="absolute left-3 top-3 rounded-full bg-black/65 px-3 py-1.5 text-sm font-medium text-white backdrop-blur">{finding.shot_label}</span>
      </div>
      <div className="p-4">
        <p className="text-sm font-semibold text-amber-700">疑似問題 {index + 1}</p>
        <h2 className="mt-1 text-lg font-semibold leading-6">{finding.summary}</h2>
        <label htmlFor={checkboxId} className={`mt-4 flex min-h-16 cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 transition ${checked ? 'border-[#8fb624] bg-[#f5ffe0]' : 'border-[#d9e5de] bg-[#f7faf8] hover:bg-[#f1f6f3]'}`}>
          <Checkbox id={checkboxId} checked={checked} onCheckedChange={(value) => onCheckedChange(value === true)} aria-label={`我對此項 AI 判讀結果有疑義：${finding.summary}`} className="size-6 rounded-full border-[#789087] data-checked:border-[#173e35] data-checked:bg-[#173e35]" />
          <span className="font-medium leading-6">我對此項 AI 判讀結果有疑義</span>
          {checked && <CheckCircle2 className="ml-auto size-5 shrink-0 text-[#47741e]" aria-hidden="true" />}
        </label>
      </div>
    </article>
  );
}
