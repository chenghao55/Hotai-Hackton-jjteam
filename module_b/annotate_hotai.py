"""Run a localhost-only UI for minimal single-photo Hotai damage annotation."""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import random
from threading import Lock
from urllib.parse import urlparse
import webbrowser

from .dataset import ImageSample, discover_samples


SCHEMA_VERSION = 1
VISIBLE_DAMAGE_VALUES = frozenset({"yes", "no", "uncertain"})
CATEGORY_VALUES = frozenset({"scratch", "collision_damage", "uncertain_category"})


@dataclass(frozen=True)
class AnnotatedPhotoSample:
    path: Path
    label: int
    group_id: str
    categories: tuple[str, ...]
    annotation_id: str


def load_annotated_samples(
    queue_path: str | Path, annotations_path: str | Path, *, exclude_uncertain: bool = True
) -> list[AnnotatedPhotoSample]:
    queue = json.loads(Path(queue_path).read_text(encoding="utf-8"))
    annotations = json.loads(Path(annotations_path).read_text(encoding="utf-8"))
    if queue.get("schema_version") != SCHEMA_VERSION or annotations.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported annotation schema version")
    root = Path(queue.get("data_root", "")).resolve()
    raw_annotations = annotations.get("annotations")
    if not isinstance(raw_annotations, dict):
        raise ValueError("Annotation file does not contain an annotations object")
    samples: list[AnnotatedPhotoSample] = []
    for item in queue.get("items", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("Annotation queue contains an invalid item")
        raw = raw_annotations.get(item["id"])
        if raw is None:
            raise ValueError(f"Missing annotation for queue item: {item['id']}")
        annotation = validate_annotation(raw)
        if annotation["visible_damage"] == "uncertain" and exclude_uncertain:
            continue
        if annotation["visible_damage"] == "uncertain":
            raise ValueError("Uncertain annotations cannot be converted to binary labels")
        image_path = (root / item["relative_path"]).resolve()
        if not image_path.is_relative_to(root) or not image_path.is_file():
            raise ValueError(f"Annotated image is missing or outside the data root: {image_path}")
        samples.append(
            AnnotatedPhotoSample(
                path=image_path,
                label=int(annotation["visible_damage"] == "yes"),
                group_id=str(item["vehicle_group"]),
                categories=tuple(annotation["categories"]),
                annotation_id=item["id"],
            )
        )
    if not samples or {sample.label for sample in samples} != {0, 1}:
        raise ValueError("Completed annotations must contain visible and non-visible damage")
    return samples


def _round_robin_by_group(samples: list[ImageSample], count: int, seed: int) -> list[ImageSample]:
    grouped: dict[str, deque[ImageSample]] = defaultdict(deque)
    for sample in sorted(samples, key=lambda item: str(item.path)):
        grouped[sample.group_id].append(sample)
    group_ids = sorted(grouped)
    random.Random(seed).shuffle(group_ids)
    selected: list[ImageSample] = []
    while group_ids and len(selected) < count:
        remaining: list[str] = []
        for group_id in group_ids:
            if len(selected) >= count:
                break
            selected.append(grouped[group_id].popleft())
            if grouped[group_id]:
                remaining.append(group_id)
        group_ids = remaining
    return selected


def select_annotation_samples(
    samples: list[ImageSample], *, count: int, seed: int
) -> list[ImageSample]:
    if count <= 0 or count > len(samples):
        raise ValueError("annotation count must be within the dataset size")
    positives = [sample for sample in samples if sample.label == 1]
    negatives = [sample for sample in samples if sample.label == 0]
    positive_count = min(len(positives), count // 2)
    negative_count = min(len(negatives), count - positive_count)
    if positive_count + negative_count < count:
        positive_count = min(len(positives), count - negative_count)
    selected = _round_robin_by_group(positives, positive_count, seed)
    selected += _round_robin_by_group(negatives, negative_count, seed + 1)
    random.Random(seed + 2).shuffle(selected)
    if len(selected) != count:
        raise ValueError("Unable to select the requested balanced annotation queue")
    return selected


def validate_annotation(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError("annotation must be an object")
    visible_damage = raw.get("visible_damage")
    categories = raw.get("categories", [])
    notes = raw.get("notes", "")
    if visible_damage not in VISIBLE_DAMAGE_VALUES:
        raise ValueError("visible_damage must be yes, no, or uncertain")
    if not isinstance(categories, list) or any(value not in CATEGORY_VALUES for value in categories):
        raise ValueError("categories contain an unsupported value")
    categories = list(dict.fromkeys(categories))
    if visible_damage == "yes" and not categories:
        raise ValueError("visible damage requires at least one category")
    if visible_damage != "yes" and categories:
        raise ValueError("only visible damage may contain categories")
    if "uncertain_category" in categories and len(categories) != 1:
        raise ValueError("uncertain_category cannot be combined with another category")
    if not isinstance(notes, str) or len(notes) > 500:
        raise ValueError("notes must be a string of at most 500 characters")
    return {
        "visible_damage": visible_damage,
        "categories": categories,
        "notes": notes.strip(),
    }


def build_queue(data_root: Path, *, count: int, seed: int) -> dict[str, object]:
    root = data_root.resolve()
    samples = select_annotation_samples(discover_samples(root), count=count, seed=seed)
    items = []
    for sample in samples:
        relative = sample.path.relative_to(root).as_posix()
        item_id = sha256(relative.encode("utf-8")).hexdigest()[:16]
        items.append(
            {
                "id": item_id,
                "relative_path": relative,
                "vehicle_group": sample.group_id,
                "weak_claim_label": sample.label,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "seed": seed,
        "count": count,
        "data_root": str(root),
        "items": items,
    }


def _atomic_json_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


HTML = r"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Module B 車損標註</title><style>
:root{font-family:system-ui,sans-serif;color:#18212f;background:#edf1f5}body{margin:0}.app{max-width:1100px;margin:auto;padding:18px}
.top,.panel{background:white;border-radius:14px;padding:16px;box-shadow:0 3px 16px #17203318}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.progress{height:9px;background:#dce3ea;border-radius:9px;overflow:hidden}.bar{height:100%;background:#2474e5}.grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(320px,.8fr);gap:14px}
.photo{height:68vh;min-height:420px;display:flex;align-items:center;justify-content:center;background:#111927;border-radius:10px;overflow:hidden}.photo img{max-width:100%;max-height:100%;object-fit:contain}
h1{font-size:20px;margin:0}h2{font-size:17px;margin:0 0 12px}.choice{display:block;border:1px solid #ccd5df;border-radius:9px;padding:11px;margin:8px 0;cursor:pointer}.choice:hover{border-color:#2474e5}
.categories{margin:12px 0 18px;padding:10px;background:#f4f7fa;border-radius:9px}.actions{display:flex;gap:8px}.actions button{flex:1;border:0;border-radius:8px;padding:12px;cursor:pointer;font-weight:650}.primary{background:#2474e5;color:white}.secondary{background:#dfe6ee}.meta{color:#68778a;font-size:13px;margin-top:10px}.done{padding:50px;text-align:center;font-size:20px}.error{color:#b42318;min-height:24px}textarea{width:100%;box-sizing:border-box;min-height:70px}
@media(max-width:800px){.grid{grid-template-columns:1fr}.photo{height:48vh;min-height:300px}}
</style></head><body><div class="app"><div class="top"><div><h1>Module B 單張照片車損標註</h1><div id="counter"></div></div><div style="width:42%"><div class="progress"><div id="bar" class="bar"></div></div></div></div><div id="main"></div></div>
<script>
let state,index=0; const main=document.querySelector('#main');
async function load(){state=await (await fetch('/api/state')).json();index=Math.max(0,state.items.findIndex(x=>!x.annotation));if(index<0)index=state.items.length-1;render()}
function setPreset(v,c=[]){document.querySelector(`input[name=visible][value=${v}]`).checked=true;document.querySelectorAll('input[name=category]').forEach(x=>x.checked=c.includes(x.value));toggleCategories()}
function toggleCategories(){const yes=document.querySelector('input[name=visible]:checked')?.value==='yes';document.querySelector('#categories').style.display=yes?'block':'none'}
function render(){const done=state.completed===state.items.length;if(done){main.innerHTML=`<div class="panel done">全部 ${state.items.length} 張已完成。可以回到 Codex 繼續訓練。</div>`;updateTop();return}const item=state.items[index];const a=item.annotation||{};main.innerHTML=`<div class="grid"><div class="panel"><div class="photo"><img src="${item.image_url}" alt="待標註照片"></div><div class="meta">照片 ${index+1} / ${state.items.length}　ID: ${item.id}</div></div><div class="panel"><h2>這張照片看得到損傷嗎？</h2>${['no','yes','uncertain'].map(v=>`<label class="choice"><input type="radio" name="visible" value="${v}" ${a.visible_damage===v?'checked':''}> ${{no:'沒有可見損傷',yes:'有可見損傷',uncertain:'無法判斷'}[v]}</label>`).join('')}<div id="categories" class="categories"><b>損傷類型（可複選）</b>${[['scratch','刮傷'],['collision_damage','撞傷／凹陷／破損'],['uncertain_category','有損傷但類型不確定']].map(([v,t])=>`<label class="choice"><input type="checkbox" name="category" value="${v}" ${(a.categories||[]).includes(v)?'checked':''}> ${t}</label>`).join('')}</div><label>備註（選填）<textarea id="notes">${a.notes||''}</textarea></label><div id="error" class="error"></div><div class="actions"><button class="secondary" onclick="previous()">上一張</button><button class="primary" onclick="save()">儲存並下一張</button></div><div class="meta">快速鍵：1 無損傷、2 刮傷、3 撞傷、4 兩者、5 無法判斷、Enter 儲存</div></div></div>`;document.querySelectorAll('input[name=visible]').forEach(x=>x.onchange=toggleCategories);toggleCategories();updateTop()}
function updateTop(){document.querySelector('#counter').textContent=`已完成 ${state.completed} / ${state.items.length}`;document.querySelector('#bar').style.width=`${100*state.completed/state.items.length}%`}
async function save(){const visible=document.querySelector('input[name=visible]:checked')?.value;const categories=[...document.querySelectorAll('input[name=category]:checked')].map(x=>x.value);const notes=document.querySelector('#notes').value;const response=await fetch('/api/annotation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:state.items[index].id,visible_damage:visible,categories,notes})});const data=await response.json();if(!response.ok){document.querySelector('#error').textContent=data.error;return}state=data;const next=state.items.findIndex((x,i)=>i>index&&!x.annotation);index=next>=0?next:state.items.findIndex(x=>!x.annotation);render()}
function previous(){if(index>0){index--;render()}}
document.addEventListener('keydown',e=>{if(e.target.tagName==='TEXTAREA')return;if(e.key==='1')setPreset('no');if(e.key==='2')setPreset('yes',['scratch']);if(e.key==='3')setPreset('yes',['collision_damage']);if(e.key==='4')setPreset('yes',['scratch','collision_damage']);if(e.key==='5')setPreset('uncertain');if(e.key==='Enter')save()});load();
</script></body></html>"""


class AnnotationStore:
    def __init__(self, queue: dict[str, object], annotations_path: Path):
        self.queue = queue
        self.annotations_path = annotations_path
        self.lock = Lock()
        self.items_by_id = {item["id"]: item for item in queue["items"]}
        if annotations_path.exists():
            raw = json.loads(annotations_path.read_text(encoding="utf-8"))
            if raw.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("Unsupported annotation schema version")
            self.annotations = dict(raw.get("annotations", {}))
        else:
            self.annotations: dict[str, dict[str, object]] = {}

    def state(self) -> dict[str, object]:
        items = [
            {
                "id": item["id"],
                "image_url": f"/image/{item['id']}",
                "annotation": self.annotations.get(item["id"]),
            }
            for item in self.queue["items"]
        ]
        return {"items": items, "completed": sum(item["annotation"] is not None for item in items)}

    def save(self, item_id: str, raw: object) -> None:
        if item_id not in self.items_by_id:
            raise ValueError("Unknown annotation item id")
        annotation = validate_annotation(raw)
        with self.lock:
            self.annotations[item_id] = annotation
            _atomic_json_write(
                self.annotations_path,
                {
                    "schema_version": SCHEMA_VERSION,
                    "queue_seed": self.queue["seed"],
                    "queue_count": self.queue["count"],
                    "annotations": self.annotations,
                },
            )


def make_handler(store: AnnotationStore, data_root: Path):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, value: object, status: HTTPStatus = HTTPStatus.OK):
            payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                payload = HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if path == "/api/state":
                self._json(store.state())
                return
            if path.startswith("/image/"):
                item_id = path.removeprefix("/image/")
                item = store.items_by_id.get(item_id)
                if item is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                image_path = (data_root / item["relative_path"]).resolve()
                if not image_path.is_relative_to(data_root):
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                payload = image_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mimetypes.guess_type(image_path.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self):
            if urlparse(self.path).path != "/api/annotation":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 10_000:
                    raise ValueError("Invalid request size")
                raw = json.loads(self.rfile.read(length))
                if not isinstance(raw, dict):
                    raise ValueError("Request must be an object")
                item_id = raw.pop("id", None)
                if not isinstance(item_id, str):
                    raise ValueError("Annotation id is required")
                store.save(item_id, raw)
                self._json(store.state())
            except (ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def log_message(self, format, *args):
            return

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--queue", type=Path, default=Path("data/hotai_annotation_queue.json"))
    parser.add_argument("--annotations", type=Path, default=Path("data/hotai_annotations.json"))
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260914)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_root = args.data_root.resolve()
    if args.queue.exists():
        queue = json.loads(args.queue.read_text(encoding="utf-8"))
        if Path(queue.get("data_root", "")).resolve() != data_root:
            raise ValueError("Existing queue belongs to a different data root")
    else:
        queue = build_queue(data_root, count=args.count, seed=args.seed)
        _atomic_json_write(args.queue, queue)
    store = AnnotationStore(queue, args.annotations)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store, data_root))
    url = f"http://127.0.0.1:{args.port}/"
    print(json.dumps({"url": url, "queue": str(args.queue), "annotations": str(args.annotations), "completed": store.state()["completed"]}, ensure_ascii=False), flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
