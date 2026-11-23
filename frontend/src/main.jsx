import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { imagePoint, pixelBox } from "./coordinates.js";
import "./style.css";
import Comparison from "./Comparison.jsx";
import Landmarks from "./Landmarks.jsx";
import PlatformApp from "./PlatformApp.jsx";
import { jsonBody, platformApi } from "./platformApi.js";
import ErrorBoundary from "./components/ErrorBoundary.jsx";

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.headers.get("content-type")?.includes("application/json"))
    throw new Error(
      `Local server returned HTTP ${response.status}. Check the backend terminal and retry.`,
    );
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
const jsonPost = (data) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

function App() {
  const [health, setHealth] = useState(null);
  const [reference, setReference] = useState(null);
  const [inspections, setInspections] = useState([]);
  const [selected, setSelected] = useState(null);
  const [components, setComponents] = useState([]);
  const [regionId, setRegionId] = useState(null);
  const [mode, setMode] = useState("automatic");
  const [tool, setTool] = useState("landmarks");
  const [pointIndex, setPointIndex] = useState(0);
  const [previewWidth, setPreviewWidth] = useState(720);
  const [draft, setDraft] = useState(null);
  const [sharpen, setSharpen] = useState(false);
  const [synthetic, setSynthetic] = useState(false);
  const [batch, setBatch] = useState(null);
  const [busy, setBusy] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [proposing, setProposing] = useState(false);
  const [verifiedRegionsAvailable, setVerifiedRegionsAvailable] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const drag = useRef(null);
  const photos = [reference, ...inspections].filter(Boolean);
  const photo = photos.find((p) => p.id === selected) || reference;
  const previewInspection = inspections.find((p) => p.id === selected) || inspections[0];
  const previewPoints = previewInspection?.registered_points || (mode === 'manual' ? previewInspection?.points :
    previewInspection?.detection?.status === 'ok' ? previewInspection.detection.landmarks.map(p=>[p.x,p.y]) : []);
  const names = health?.landmark_names || [
    "upper_left_mount",
    "upper_right_mount",
    "lower_right_mount",
    "lower_left_mount",
  ];
  const activeRegion = components.find((p) => p.id === regionId);
  const referenceSelected = photo?.id === reference?.id;

  useEffect(() => {
    api("/api/health")
      .then(setHealth)
      .catch((e) => setError(`Local backend unavailable: ${e.message}`));
  }, []);
  useEffect(() => {
    platformApi("/api/golden-config").then((saved) => {
      setReference(saved.reference);
      setComponents(saved.components);
      setSelected(saved.reference.id);
      setRegionId(saved.components[0]?.id || null);
      setMode(saved.mode || "automatic");
      setSharpen(!!saved.sharpen);
      setNotice("Saved golden configuration restored.");
    }).catch(() => {});
  }, []);
  function changePhoto(id, update) {
    const referencePointsChanged = id === reference?.id && update.points &&
      JSON.stringify(update.points) !== JSON.stringify(reference.points);
    setReference((p) => (p?.id === id ? { ...p, ...update } : p));
    setInspections((items) =>
      items.map((p) => id === reference?.id && (update.points || update.board_polygon)
        ? { ...p, ...(referencePointsChanged ? { points: [] } : {}), projected: null, registered_points:null } : p.id === id ? { ...p, ...update, ...(update.points ? {registered_points:null,projected:null} : {}) } : p),
    );
    setBatch(null);
  }
  const photoIds = photos.map((p) => p.id).join(",");
  useEffect(() => {
    if (!photoIds) {
      setDetecting(false);
      return;
    }
    let cancelled = false;
    setDetecting(true);
    Promise.all(
      photoIds.split(",").filter((id) => mode === "automatic" || id === reference?.id).map(async (id) => {
        let detection;
        try {
          detection = await api(`/api/landmarks/${id}`, { method: "POST" });
        } catch (e) {
          detection = { status: "failure", reason: e.message, landmarks: [] };
        }
        if (!cancelled) {
          changePhoto(id, { detection });
          setReference((p) => p?.id === id && !p.points?.length && detection.status === "ok"
            ? { ...p, points: detection.landmarks.map((v) => [v.x, v.y]) } : p);
        }
      }),
    ).finally(() => {
      if (!cancelled) setDetecting(false);
    });
    return () => {
      cancelled = true;
    };
  }, [mode, photoIds]);

  async function upload(event, isReference, replaceId = null) {
    const files = [...event.target.files];
    event.target.value = "";
    if (!files.length) return;
    if (!isReference && !replaceId && inspections.length + files.length > (health?.max_photos ?? 15)) {
      setError(`Choose up to ${health?.max_photos ?? 15} inspection photos in total.`);
      return;
    }
    setBusy(true);
    setError("");
    setBatch(null);
    try {
      const uploaded = [];
      const failures = [];
      for (const file of files) {
        if (file.size > (health?.max_upload_bytes ?? 12 * 1024 * 1024)) {
          failures.push(`${file.name}: Photo exceeds 12 MiB upload limit. Choose a smaller JPEG or PNG.`);
          continue;
        }
        if (!/\.(jpe?g|png)$/i.test(file.name)) {
          failures.push(`${file.name}: Choose a JPEG or PNG photo.`);
          continue;
        }
        const body = new FormData();
        body.append("image", file);
        try {
          const result = await api("/api/photos", { method: "POST", body });
          if (result.error) {
            failures.push(`${file.name}: ${result.error}`);
            continue;
          }
          uploaded.push({ ...result, points: [] });
        } catch (e) {
          failures.push(`${file.name}: ${e.message}`);
        }
      }
      if (failures.length) setError(failures.join(" "));
      if (!uploaded.length) return;
      if (isReference) {
        setVerifiedRegionsAvailable(false);
        setReference({ ...uploaded[0], board_polygon: [], confirmed: false });
        setInspections((items) => items.map((p) => ({ ...p, points: [], projected: null, registered_points: null })));
        const setup = await api(`/api/references/${uploaded[0].id}`);
        let automatic = setup;
        try {
          automatic = await api(`/api/references/${uploaded[0].id}/automatic`, { method: "POST" });
        } catch (e) {
          setNotice(`Automatic reference setup needs correction: ${e.message}`);
        }
        setReference((p) => p?.id === uploaded[0].id ? { ...p, ...automatic } : p);
        setMode("automatic");
        setProposing(true);
        try {
          const proposal = await api(`/api/photos/${uploaded[0].id}/component-proposals`, { method: "POST" });
          setComponents(proposal.components);
          setRegionId(proposal.components[0]?.id || null);
          setReference((p) => p?.id === uploaded[0].id ? { ...p, board_polygon: proposal.board_polygon } : p);
          setNotice(`${proposal.candidate_count} component candidates proposed. Review UNKNOWN regions before saving.`);
          try { await api(`/api/photos/${uploaded[0].id}/regions`); setVerifiedRegionsAvailable(true); } catch {}
        } catch (proposalError) {
          setComponents([]);
          setError(`Reference uploaded, but automatic component proposals failed: ${proposalError.message}`);
        } finally { setProposing(false); }
      } else setInspections((items) => replaceId
        ? items.map((p) => p.id === replaceId ? uploaded[0] : p)
        : [...items, ...uploaded]);
      setSelected(uploaded[0].id);
      setPointIndex(0);
      setTool("landmarks");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function switchMode(next) {
    if (next === "manual") {
      for (const p of photos) {
        const points = p.projected ? p.projected.map(([x, y]) => ({ x, y })) : p.detection?.status === "ok" ? p.detection.landmarks : p.detection?.diagnostics?.candidates?.[0]?.landmarks;
        if (!p.points?.length && points?.length === 4 && points.every((v) => Number.isFinite(v.x) && Number.isFinite(v.y)))
          changePhoto(p.id, { points: points.map((v) => [v.x, v.y]) });
      }
    }
    setMode(next);
    setBatch(null);
    setError("");
  }
  function setPoint(index, position) {
    const points = [...(tool === "outline" ? reference.board_polygon || [] : photo.points || [])];
    points[index] = [
      Math.min(photo.width - 1, position[0]),
      Math.min(photo.height - 1, position[1]),
    ];
    if (tool === "outline" && referenceSelected) {
      const outline = [...(reference.board_polygon || [])];
      outline[index] = points[index];
      changePhoto(photo.id, { board_polygon: outline, confirmed: false });
    } else changePhoto(photo.id, { points, ...(referenceSelected ? { confirmed: false } : {}) });
  }
  function updateRegion(update) {
    setComponents((items) =>
      items.map((p) => (p.id === regionId ? { ...p, ...update } : p)),
    );
    setBatch(null);
  }
  function addRegion(box) {
    if (box[2] - box[0] < 5 || box[3] - box[1] < 5) {
      setError("Draw a region at least 5 × 5 original pixels.");
      return;
    }
    const id = crypto.randomUUID();
    const part = {
      id,
      name: `Component ${components.length + 1}`,
      bbox_xyxy_px: box,
    };
    setComponents((items) => [...items, part]);
    setRegionId(id);
    setBatch(null);
    setError("");
  }
  function pointerPosition(event) {
    return imagePoint(
      event.clientX,
      event.clientY,
      event.currentTarget.getBoundingClientRect(),
      [photo.width, photo.height],
    );
  }
  function startPointer(event) {
    if (busy || !photo || photo.error || event.button !== 0) return;
    const position = pointerPosition(event);
    if ((tool === "landmarks" && (mode === "manual" || referenceSelected)) || (tool === "outline" && referenceSelected)) {
      drag.current = { kind: "point", index: pointIndex };
      setPoint(pointIndex, position);
    } else if (tool === "boxes" && referenceSelected) {
      drag.current = { kind: "box", start: position };
      setDraft(pixelBox(position, position));
    } else return;
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function movePointer(event) {
    if (!drag.current) return;
    const currentDrag = drag.current;
    const position = pointerPosition(event);
    if (currentDrag.kind === "point") setPoint(currentDrag.index, position);
    else if (currentDrag.kind === "move-box") {
      const { id, start, box } = currentDrag;
      const [x1, y1, x2, y2] = box;
      const width = x2 - x1, height = y2 - y1;
      const dx = position[0] - start[0], dy = position[1] - start[1];
      const left = Math.max(0, Math.min(photo.width - width, Math.round(x1 + dx)));
      const top = Math.max(0, Math.min(photo.height - height, Math.round(y1 + dy)));
      setComponents((items) => items.map((part) => part.id === id
        ? { ...part, bbox_xyxy_px: [left, top, left + width, top + height], candidate_status: "VERIFIED" } : part));
      setBatch(null);
    } else setDraft(pixelBox(currentDrag.start, position));
  }
  function endPointer(event) {
    if (!drag.current) return;
    const position = pointerPosition(event);
    if (drag.current.kind === "box")
      addRegion(pixelBox(drag.current.start, position));
    else if (drag.current.kind === "point") {
      setPoint(drag.current.index, position);
      setPointIndex(Math.min(3, drag.current.index + 1));
    } else if (drag.current.kind === "move-box") {
      movePointer(event);
    }
    drag.current = null;
    setDraft(null);
  }
  async function confirmReference() {
    setBusy(true);
    setError("");
    try {
      const saved = await api(`/api/references/${reference.id}`, jsonPost({
        points: reference.points, board_polygon: reference.board_polygon,
      }));
      changePhoto(reference.id, saved);
      setMode("automatic");
      setTool("landmarks");
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function saveGolden() {
    if (components.some((component) => component.candidate_status === "UNKNOWN")) {
      setError("Accept, edit, or remove every UNKNOWN component proposal before saving.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await platformApi("/api/golden-config", jsonBody({
        reference_id: reference.id, components, mode: "automatic", sharpen,
      }));
      setNotice("Golden configuration saved for Live Inspection.");
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function detectComponents() {
    if (!reference) return;
    setProposing(true); setError(""); setNotice("");
    try {
      const proposal = await api(`/api/photos/${reference.id}/component-proposals`, jsonPost({
        board_polygon: reference.board_polygon || [],
      }));
      setComponents(proposal.components);
      setRegionId(proposal.components[0]?.id || null);
      changePhoto(reference.id, { board_polygon: proposal.board_polygon });
      setNotice(`${proposal.candidate_count} UNKNOWN candidates proposed. Confirm, rename, resize, add, or remove regions.`);
    } catch (e) { setError(e.message); }
    finally { setProposing(false); }
  }
  async function loadVerifiedRegions() {
    try {
      const saved = await api(`/api/photos/${reference.id}/regions`);
      setComponents(saved.components);
      setRegionId(saved.components[0]?.id || null);
      setNotice("Verified sample annotations loaded. Review before saving this golden configuration.");
    } catch (e) { setError(e.message); }
  }
  async function importComponentMap(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !reference) return;
    setProposing(true); setError(""); setNotice("");
    try {
      const body = new FormData();
      body.append("component_map", file);
      const proposal = await api(`/api/photos/${reference.id}/component-map`, { method: "POST", body });
      setComponents(proposal.components);
      setRegionId(proposal.components[0]?.id || null);
      changePhoto(reference.id, { board_polygon: proposal.board_polygon });
      setNotice(`${proposal.imported_component_count} reference components imported; review and accept each proposal before saving.`);
    } catch (e) { setError(e.message); }
    finally { setProposing(false); }
  }
  async function run() {
    setBusy(true);
    setError("");
    setBatch(null);
    try {
      const result = await api(
        "/api/inspections",
        jsonPost({
          reference_id: reference.id,
          reference_points: Array.from(reference.points || [], (p) => p || []),
          inspections: inspections.map((p) => ({
            photo_id: p.id,
            points: Array.from(p.points || [], (v) => v || []),
          })),
          components,
          mode,
          sharpen,
          synthetic,
        }),
      );
      setBatch(result);
      const referencePoints = result.photos.find(r=>r.alignment?.verification_status === 'verified')?.alignment.reference_points;
      if (referencePoints) setReference(p=>({...p,points:referencePoints}));
      setInspections((items) => items.map((p) => {
        const alignment=result.photos.find(r=>r.photo_id===p.id)?.alignment;
        const verified=alignment?.verification_status === 'verified';
        return {...p,registered_points:verified ? alignment.inspection_points : null,
          landmark_source:alignment?.landmark_kind === 'projected' ? 'Registration-derived' : alignment?.source === 'manual_landmarks' ? 'Manual' : 'Model-detected',
          projected:verified && alignment.landmark_kind === 'projected' ? alignment.inspection_points : null};
      }));

      setTimeout(
        () =>
          document
            .getElementById("results")
            ?.scrollIntoView({ behavior: "instant", block: "start" }),
        0,
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const editingOutline = tool === "outline" && referenceSelected;
  const pointNames = editingOutline ? ["outline upper left", "outline upper right", "outline lower right", "outline lower left"] : names;
  const displayedPoints = editingOutline ? reference.board_polygon || []
    : referenceSelected || mode === "manual" ? photo?.points || []
    : photo?.registered_points || photo?.projected || (photo?.detection?.status === "ok"
      ? photo.detection.landmarks.map((p) => [p.x, p.y]) : []);
  const radius = photo ? Math.max(photo.width, photo.height) / 85 : 10;
  const runHint = !health ? "Connect the local backend to begin."
    : !reference ? "Upload a known-good reference first."
    : !inspections.length ? "Add at least one inspection photo."
    : !components.length ? "Draw or add an expected component box on the reference."
    : mode === "automatic" && !reference.confirmed ? "Confirm the reference landmarks and PCB outline once. Inspection points will be found automatically."
    : detecting ? "Wait for landmark detection to finish."
    : mode === "manual" && photos.some((p) => !p.error && Array.from({ length: 4 }, (_, i) => p.points?.[i]).some((point) => !point || !point.every(Number.isFinite)))
      ? "Mark all four landmarks on each photo before running."
      : "Ready to inspect. Review the reference landmarks and expected parts before running.";

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="board-symbol" aria-hidden="true">
          ▦
        </div>
        <div>
          <h1>Inspection Lab</h1>
          <p>
            Golden configuration, registered comparison, and component evidence.
          </p>
        </div>
        <span className="local-tag">Local files only</span>
      </header>
      <main>
        {error && (
          <div role="alert" className="message error">
            {error}
          </div>
        )}
        {notice && <div role="status" className="message notice">{notice}</div>}
        <fieldset className="workflow" disabled={busy}>
          <section className="upload-section" aria-labelledby="photos-heading">
            <div className="section-heading">
              <h2 id="photos-heading">Board inputs</h2>
              <p>
                One layout and board side per run. JPEG or PNG, up to 12 MiB
                each.
              </p>
            </div>
            <div className="upload-row">
              <label className="upload-control">
                <strong>Known-good reference</strong>
                {reference?.image_url && <img className="upload-preview" src={reference.image_url} alt="Known-good reference preview" />}
                <span>
                  {reference?.filename ||
                    "Choose one complete, sharp board photo"}
                  {reference && " · Choose a file to replace the reference and reset its annotations."}
                </span>
                <input
                  aria-label="Reference photo"
                  type="file"
                  accept="image/jpeg,image/png"
                  onChange={(e) => upload(e, true)}
                />
              </label>
              <label className="upload-control">
                <strong>Inspection photos</strong>
                <span>
                  {inspections.length}/{health?.max_photos ?? 15} selected. Add photos to this batch.
                </span>
                <input
                  aria-label="Inspection photos"
                  type="file"
                  accept="image/jpeg,image/png"
                  multiple
                  disabled={!reference}
                  onChange={(e) => upload(e, false)}
                />
              </label>
            </div>
            <label className="check">
              <input
                type="checkbox"
                checked={synthetic}
                onChange={(e) => {
                  setSynthetic(e.target.checked);
                  setBatch(null);
                }}
              />{" "}
              Label this run as a synthetic demonstration
            </label>
          </section>
          <section
            className="annotation-section"
            aria-labelledby="annotations-heading"
          >
            <div className="section-heading">
              <h2 id="annotations-heading">
                Golden configuration and inspection workspace
              </h2>
              <p>
                Automatic board references and component regions. Correct the golden configuration here; reuse it for every inspection.
              </p>
            </div>
            <div className="mode-row">
              <fieldset className="mode-switch">
                <legend>Landmark mode</legend>
                {["automatic", "manual"].map((value) => (
                  <label key={value}>
                    <input
                      type="radio"
                      name="mode"
                      value={value}
                      checked={mode === value}
                      onChange={() => switchMode(value)}
                    />
                    {value === "manual" ? "Manual" : "Automatic"}
                  </label>
                ))}
              </fieldset>
              <p>
                {mode === "manual"
                  ? "Mark points manually, or confirm the reference setup to align inspection photos automatically."
                  : "Board references are saved automatically. Inspection uses verified landmarks or independent on-board registration."}
              </p>
            </div>
            {mode === "automatic" && (
              <div className="message notice">
                {detecting
                  ? "Detecting landmarks with the local model…"
                  : `Mounting-hole model: ${health?.checkpoint_available ? "local checkpoint available; inspect each detection result." : "checkpoint unavailable."}`}
                <button
                  className="secondary"
                  onClick={() => switchMode("manual")}
                >
                  Switch to Manual
                </button>
              </div>
            )}
            <div className="photo-tabs" aria-label="Photo selection">
              {photos.map((p, i) => (
                <div className="photo-tab" key={p.id}>
                  <button
                    className={photo?.id === p.id ? "selected" : ""}
                    aria-pressed={photo?.id === p.id}
                    onClick={() => {
                      setSelected(p.id);
                      setPointIndex(0);
                      setTool("landmarks");
                    }}
                  >
                    <span>{p.id === reference?.id ? "Reference" : `Inspection ${inspections.findIndex((item) => item.id === p.id) + 1}`}</span>
                    {p.image_url && <img className="photo-thumbnail" src={p.image_url} alt="" />}
                    <strong>{p.filename}</strong>
                    <small>
                      {p.error
                        ? "Photo error"
                        : p.id === reference?.id && p.confirmed ? "Reference confirmed"
                        : p.projected && mode === "automatic" ? "Projected from reference"
                        : mode === "manual"
                          ? `${p.points.filter(Boolean).length}/4 points`
                          : p.detection?.status === "ok"
                            ? "Landmarks accepted"
                            : p.id === reference?.id ? "Mark or correct reference" : "Will try reference registration"}
                    </small>
                  </button>
                  <div className="photo-actions">
                    {p.id !== reference?.id && <label className="replace-photo">Replace
                      <input aria-label={`Replace ${p.filename}`} type="file" accept="image/jpeg,image/png" onChange={(e) => upload(e, false, p.id)} />
                    </label>}
                    <button
                      className="remove-photo"
                      aria-label={`Remove ${p.filename}`}
                      onClick={() => {
                        if (p.id === reference?.id) {
                          setReference(null);
                          setInspections((items) => items.map((item) => ({ ...item, points: [], projected: null, registered_points: null })));
                          setComponents([]);
                          setRegionId(null);
                        }
                        setInspections((items) =>
                          items.filter((item) => item.id !== p.id),
                        );
                        setSelected(p.id === reference?.id ? null : reference?.id);
                        setBatch(null);
                      }}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
            {reference && inspections.length > 0 && <div className="workspace-preview" aria-label="Inspection workspace overview">
              <figure><figcaption>Golden PCB · reference points and component regions</figcaption>
                <svg viewBox={`0 0 ${reference.width} ${reference.height}`} role="img" aria-label="Golden board configuration">
                  <image href={reference.image_url} width={reference.width} height={reference.height} />
                  {components.map((part) => { const [x1,y1,x2,y2] = part.bbox_xyxy_px; return <rect key={part.id} x={x1} y={y1} width={x2-x1} height={y2-y1} fill="none" stroke="#ffbf00" strokeWidth="2" />; })}
                  <Landmarks points={reference.points} width={reference.width} height={reference.height} verified={reference.confirmed}/>
                </svg>
              </figure>
              <figure><figcaption>Inspection PCB · {previewInspection.filename} · {previewInspection.registered_points ? `${previewInspection.landmark_source} · verified` : 'Landmark correspondence pending'}</figcaption>
                <svg viewBox={`0 0 ${previewInspection.width} ${previewInspection.height}`} role="img" aria-label="Inspection workspace input">
                  <image href={previewInspection.image_url} width={previewInspection.width} height={previewInspection.height}/>
                  <Landmarks points={previewPoints} width={previewInspection.width} height={previewInspection.height} verified={!!previewInspection.registered_points}/>
                </svg>
              </figure>
            </div>}
            {!photo && (
              <div className="empty-editor">
                <div aria-hidden="true">▦</div>
                <h3>Start with the known-good board</h3>
                <p>
                  Upload a reference to mark mounting holes and draw the parts
                  you expect to see.
                </p>
              </div>
            )}
            {photo && (
              <div className="editor-layout">
                <div className="image-workspace">
                  <div className="editor-toolbar">
                    <div className="tool-switch">
                      <button
                        className={tool === "landmarks" ? "selected" : ""}
                        onClick={() => setTool("landmarks")}
                      >
                        Mark landmarks
                      </button>
                      <button
                        disabled={!referenceSelected}
                        className={tool === "boxes" ? "selected" : ""}
                        onClick={() => setTool("boxes")}
                      >
                        Draw part boxes
                      </button>
                    </div>
                    <span>
                      {photo.width
                        ? `${photo.width} × ${photo.height} original pixels`
                        : "Unavailable image"}
                    </span>
                  </div>
                  {photo.error ? (
                    <div className="message error">
                      Photo needs review: {photo.error}
                    </div>
                  ) : (
                    <>
                      {mode === "automatic" &&
                        photo.detection?.status === "failure" && !photo.projected && !(referenceSelected && reference.confirmed) && (
                          <div className="message notice">
                            <strong>Landmarks need review.</strong>{" "}
                            {photo.detection.reason}{" "}
                            <span>
                              {referenceSelected ? "Mark or correct the four reference points here, then confirm the setup." : "Reference registration will be tried automatically before manual alignment is requested."}
                            </span>
                          </div>
                        )}
                      {mode === "automatic" && photo.detection?.status === "ok" && photo.detection?.source === "calibrated_layout_mounts" && (
                        <div className="message notice">
                          All four mounting holes verified against the {photo.detection.calibrated_mounting.layout.name} calibration.
                        </div>
                      )}
                      {mode === "automatic" && photo.detection?.diagnostics && (
                        <details>
                          <summary>Raw landmark diagnostics (rejected points are tentative)</summary>
                          <pre style={{whiteSpace: "pre-wrap"}}>{JSON.stringify(photo.detection.diagnostics, null, 2)}</pre>
                        </details>
                      )}
                      <p className="canvas-instruction">
                        {tool === "boxes"
                          ? "Drag a rectangle around an expected part on the reference."
                          : mode === "manual" || referenceSelected
                            ? `Mark ${editingOutline ? "outline corner" : "L"}${pointIndex}: ${pointNames[pointIndex]}. Choose any point in the panel to correct it.`
                            : photo.projected ? "Projected from the confirmed reference after alignment verification." : "Automatic landmarks are read-only. Manual correction requires switching modes."}
                      </p>
                      <div
                        className="preview-container"
                        style={{ maxWidth: previewWidth }}
                      >
                        <svg
                          className="photo-canvas"
                          role="img"
                          aria-label={`Annotation canvas for ${photo.filename}`}
                          width={photo.width}
                          height={photo.height}
                          viewBox={`0 0 ${photo.width} ${photo.height}`}
                          onPointerDown={startPointer}
                          onPointerMove={movePointer}
                          onPointerUp={endPointer}
                          onPointerCancel={() => {
                            drag.current = null;
                            setDraft(null);
                          }}
                        >
                          <image
                            href={photo.image_url}
                            width={photo.width}
                            height={photo.height}
                          />
                          {referenceSelected &&
                            components.map((p) => {
                              const [x1, y1, x2, y2] = p.bbox_xyxy_px;
                              return (
                                <g
                                  key={p.id}
                                  onPointerDown={(e) => {
                                    e.stopPropagation();
                                    setRegionId(p.id);
                                    if (tool === "boxes") {
                                      const canvas = e.currentTarget.closest("svg");
                                      drag.current = { kind: "move-box", id: p.id,
                                        start: imagePoint(e.clientX, e.clientY, canvas.getBoundingClientRect(), [photo.width, photo.height]),
                                        box: [...p.bbox_xyxy_px] };
                                      canvas?.setPointerCapture(e.pointerId);
                                    }
                                  }}
                                >
                                  <rect
                                    x={x1}
                                    y={y1}
                                    width={Math.max(0, x2 - x1)}
                                    height={Math.max(0, y2 - y1)}
                                    className={`region-box ${p.id === regionId ? "active" : ""} ${p.review_reason ? "review" : ""}`}
                                    strokeWidth={radius / 5}
                                  />
                                  <text
                                    x={x1 + radius / 2}
                                    y={Math.max(radius * 2, y1 - radius / 2)}
                                    fontSize={radius * 1.5}
                                    className="canvas-label"
                                  >
                                    {p.name}
                                  </text>
                                </g>
                              );
                            })}
                          {draft && (
                            <rect
                              x={draft[0]}
                              y={draft[1]}
                              width={draft[2] - draft[0]}
                              height={draft[3] - draft[1]}
                              className="draft-box"
                              strokeWidth={radius / 4}
                            />
                          )}

                          {displayedPoints.map(
                            (point, index) =>
                              point && point.every(Number.isFinite) && (
                                <g key={index} pointerEvents="none">
                                  <circle
                                    cx={point[0]}
                                    cy={point[1]}
                                    r={radius}
                                    className={
                                      index === pointIndex
                                        ? "landmark active"
                                        : "landmark"
                                    }
                                    strokeWidth={radius / 4}
                                    style={mode === "automatic" && !referenceSelected && !photo.projected && photo.detection?.status !== "ok" ? {stroke: "#ff5050", strokeDasharray: "6 4"} : undefined}
                                  />
                                  <text
                                    x={point[0] + radius * 1.4}
                                    y={point[1] - radius}
                                    fontSize={radius * 1.7}
                                    className="canvas-label"
                                  >
                                    {editingOutline ? "Outline " : "L"}{index}{photo.projected && !referenceSelected && mode === "automatic" ? " projected" : ""}
                                  </text>
                                </g>
                              ),
                          )}
                        </svg>
                      </div>
                      <label className="preview-size">
                        Preview width{" "}
                        <input
                          aria-label="Preview width"
                          type="range"
                          min="320"
                          max="1000"
                          step="10"
                          value={previewWidth}
                          onChange={(e) =>
                            setPreviewWidth(Number(e.target.value))
                          }
                        />
                        <span>
                          {previewWidth}px maximum; coordinates stay in original
                          pixels
                        </span>
                      </label>
                    </>
                  )}
                </div>
                <aside className="annotation-panel">
                  <h3>{editingOutline ? "PCB surface outline" : "Alignment"}</h3>
                  {referenceSelected && <div className="message notice">
                    <p>{reference.confirmed ? "Reference saved. Its points and surface features will be reused." : "Review or correct the four landmarks and the PCB outline, then confirm once."}</p>
                    <button className="secondary" onClick={() => {
                      setTool("outline"); setPointIndex(0);
                      changePhoto(reference.id, { board_polygon: [], confirmed: false });
                    }}>Mark PCB outline</button>
                    <button className="secondary" disabled={reference.points?.filter(Boolean).length !== 4 || (reference.board_polygon?.filter(Boolean).length || 0) < 3}
                      onClick={confirmReference}>Confirm reference setup</button>
                    <button className="secondary" disabled={!reference.confirmed || !components.length || components.some((component) => component.candidate_status === "UNKNOWN")}
                      onClick={saveGolden}>Save for live line</button>
                    <button className="secondary" disabled={proposing} onClick={detectComponents}>
                      {proposing ? "Detecting components…" : "Detect components"}
                    </button>
                    <label className="secondary import-map">Import Antigravity map
                      <input aria-label="Import Antigravity component map" type="file" accept="application/json,.json"
                        disabled={proposing} onChange={importComponentMap} />
                    </label>
                    <p className="muted">Outline only the PCB surface, excluding background and off-board watermarks. Landmarks can be interior board details.</p>
                  </div>}
                  <p className="muted">
                    Four manual landmarks remain available when automatic registration needs help. Board-relative order, clockwise. Select a point, then click
                    its center.
                  </p>
                  <ol className="point-list">
                    {pointNames.map((name, index) => (
                      <li
                        key={name}
                        className={pointIndex === index ? "active-point" : ""}
                      >
                        <button
                          disabled={(mode !== "manual" && !referenceSelected) || !!photo.error}
                          onClick={() => {
                            setPointIndex(index);
                            if (!editingOutline) setTool("landmarks");
                          }}
                          aria-pressed={pointIndex === index}
                        >
                          <b>L{index}</b> {name}
                        </button>
                        <div className="coordinate-pair">
                          {["x", "y"].map((axis, axisIndex) => (
                            <label key={axis}>
                              {axis}
                              <input
                                aria-label={`${name} ${axis}`}
                                type="number"
                                step="any"
                                min="0"
                                max={
                                  (axisIndex ? photo.height : photo.width) - 1
                                }
                                disabled={(mode !== "manual" && !referenceSelected) || !!photo.error}
                                value={
                                  displayedPoints[index]?.[axisIndex] ?? ""
                                }
                                onChange={(e) => {
                                  const value = Number(e.target.value);
                                  const point = [
                                    ...(displayedPoints[index] || [0, 0]),
                                  ];
                                  point[axisIndex] = value;
                                  setPoint(index, point);
                                }}
                              />
                            </label>
                          ))}
                        </div>
                      </li>
                    ))}
                  </ol>
                  <div className="parts-heading">
                    <h3>Expected components</h3>
                    {verifiedRegionsAvailable && <button className="secondary" onClick={loadVerifiedRegions}>Load verified sample regions</button>}
                    <button className="secondary" disabled={!components.some((component) => component.candidate_status === "UNKNOWN")} onClick={() => {
                      setComponents((items) => items.map((component) => component.candidate_status === "UNKNOWN"
                        ? { ...component, candidate_status: "VERIFIED" } : component));
                      setNotice("All current proposals explicitly accepted. You can still edit or remove them before saving.");
                    }}>Accept all proposals</button>
                    <button className="secondary" disabled={!components.length} onClick={() => {
                      setComponents([]); setRegionId(null); setBatch(null); setNotice("Component regions cleared.");
                    }}>Clear all components</button>
                    <button
                      className="secondary"
                      disabled={!referenceSelected || !!photo.error}
                      onClick={() => {
                        setTool("boxes");
                        addRegion([
                          Math.floor(photo.width * 0.25),
                          Math.floor(photo.height * 0.25),
                          Math.ceil(photo.width * 0.5),
                          Math.ceil(photo.height * 0.5),
                        ]);
                      }}
                    >
                      Add box
                    </button>
                  </div>
                  {!referenceSelected && (
                    <p className="muted">
                      Select the reference to edit component regions.
                    </p>
                  )}
                  {components.length === 0 && (
                    <p className="muted">
                      Draw a box on the reference, then name the part.
                    </p>
                  )}
                  <div className="part-list">
                    {components.map((p) => (
                      <button
                        key={p.id}
                        className={regionId === p.id ? "selected" : ""}
                        onClick={() => {
                          setRegionId(p.id);
                          setSelected(reference.id);
                        }}
                      >
                        {p.name}
                        {p.candidate_status && <small>{p.candidate_status}</small>}
                        {p.review_reason && <small>Review flagged</small>}
                      </button>
                    ))}
                  </div>
                  {activeRegion && referenceSelected && (
                    <div className="region-editor">
                      {activeRegion.candidate_status === "UNKNOWN" && <button className="secondary" onClick={() =>
                        updateRegion({ candidate_status: "VERIFIED" })}>Accept component</button>}
                      <label>
                        Component name
                        <input
                          aria-label="Component name"
                          value={activeRegion.name}
                          maxLength="120"
                          onChange={(e) =>
                            updateRegion({ name: e.target.value, candidate_status: "VERIFIED" })
                          }
                        />
                      </label>
                      <div className="box-coordinates">
                        {["x1", "y1", "x2", "y2"].map((axis, i) => (
                          <label key={axis}>
                            {axis}
                            <input
                              aria-label={`Region ${axis}`}
                              type="number"
                              step="1"
                              min="0"
                              max={i % 2 ? reference.height : reference.width}
                              value={activeRegion.bbox_xyxy_px[i]}
                              onChange={(e) => {
                                const box = [...activeRegion.bbox_xyxy_px];
                                box[i] = Number(e.target.value);
                                updateRegion({ bbox_xyxy_px: box, candidate_status: "VERIFIED" });
                              }}
                            />
                          </label>
                        ))}
                      </div>
                      <label className="check">
                        <input
                          aria-label="Flag region for review"
                          type="checkbox"
                          checked={!!activeRegion.review_reason}
                          onChange={(e) =>
                            updateRegion({
                              review_reason: e.target.checked
                                ? "Unreliable region: operator review required"
                                : undefined,
                            })
                          }
                        />{" "}
                        Always needs review in this run
                      </label>
                      {activeRegion.review_reason !== undefined && (
                        <label>
                          Review reason
                          <input
                            aria-label="Review reason"
                            maxLength="500"
                            value={activeRegion.review_reason}
                            onChange={(e) =>
                              updateRegion({ review_reason: e.target.value })
                            }
                          />
                        </label>
                      )}
                      <button
                        className="danger secondary"
                        onClick={() => {
                          setComponents((items) =>
                            items.filter((p) => p.id !== regionId),
                          );
                          setRegionId(null);
                          setBatch(null);
                        }}
                      >
                        Remove component
                      </button>
                    </div>
                  )}
                </aside>
              </div>
            )}
          </section>
          <section className="run-section" aria-labelledby="run-heading">
            <div>
              <h2 id="run-heading">Run registered inspection</h2>
              <p className="run-hint" id="run-hint" role="status">{runHint}</p>
              <p className="threshold-note">
                Provisional Present threshold: {health?.comparison.present_min ?? "0.50"}.
                Missing requires low correlation plus lost edge energy and appearance change.
                Thresholds are provisional; suspected defects always require operator review.
              </p>
              <label className="check">
                <input
                  type="checkbox"
                  aria-label="Optional sharpening"
                  checked={sharpen}
                  onChange={(e) => {
                    setSharpen(e.target.checked);
                    setBatch(null);
                  }}
                />{" "}
                Mild sharpening on both comparison crops
              </label>
            </div>
            <button
              className="primary run-button"
              aria-describedby="run-hint"
              disabled={
                !reference ||
                inspections.length === 0 ||
                components.length === 0 ||
                detecting ||
                (mode === "automatic" && !reference?.confirmed) ||
                !health
              }
              onClick={run}
            >
              {busy ? "Processing…" : "Run Inspection"}
            </button>
          </section>
        </fieldset>
        {busy && (
          <p role="status" className="message notice">
            Processing local photos. Your annotations are held for this run.
          </p>
        )}
        {batch && (
          <section id="results" aria-labelledby="results-heading">
            <div className="results-heading">
              <div>
                <h2 id="results-heading">Inspection results</h2>
                <p>
                  {batch.mode === "manual"
                    ? "Manual landmarks"
                    : "Automatic landmarks"}{" "}
                  · Sharpening {batch.sharpening_enabled ? "on" : "off"} ·
                  Provisional comparison
                </p>
              </div>
              <a href={batch.report_url} target="_blank" rel="noreferrer">
                Open JSON report
              </a>
            </div>
            {batch.synthetic && (
              <div className="synthetic-label">
                Synthetic demonstration — controlled image example, not a real
                defective board.
              </div>
            )}
            {batch.photos.map((result, index) => (
              <Comparison key={`${result.photo_id}-${index}`} result={result} reference={reference}
                inspection={inspections.find((p) => p.id === result.photo_id)} index={index}
                mode={batch.mode} onManual={() => {
                  switchMode("manual"); setSelected(result.photo_id); setTool("landmarks");
                }} />
            ))}
            <p className="muted">
              Review evidence before acting. Low similarity can also come from
              parallax, glare or misalignment. Real missing-part accuracy
              remains unverified.
            </p>
          </section>
        )}
      </main>
      <footer>
        Photos and run outputs stay on this computer. Uploads must already have
        normalized orientation.
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<ErrorBoundary><PlatformApp inspectionLab={<App />} /></ErrorBoundary>);
