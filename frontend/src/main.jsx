import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { imagePoint, pixelBox } from "./coordinates.js";
import "./style.css";

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
const outcomeName = {
  ok: "Scored regions present",
  missing: "Missing component",
  review: "Needs review",
  retake: "Alignment needs review",
  error: "Photo could not be processed",
};

function App() {
  const [health, setHealth] = useState(null);
  const [reference, setReference] = useState(null);
  const [inspections, setInspections] = useState([]);
  const [selected, setSelected] = useState(null);
  const [components, setComponents] = useState([]);
  const [regionId, setRegionId] = useState(null);
  const [mode, setMode] = useState("manual");
  const [tool, setTool] = useState("landmarks");
  const [pointIndex, setPointIndex] = useState(0);
  const [previewWidth, setPreviewWidth] = useState(720);
  const [draft, setDraft] = useState(null);
  const [sharpen, setSharpen] = useState(false);
  const [synthetic, setSynthetic] = useState(false);
  const [batch, setBatch] = useState(null);
  const [busy, setBusy] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [error, setError] = useState("");
  const drag = useRef(null);
  const photos = [reference, ...inspections].filter(Boolean);
  const photo = photos.find((p) => p.id === selected) || reference;
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
  function changePhoto(id, update) {
    setReference((p) => (p?.id === id ? { ...p, ...update } : p));
    setInspections((items) =>
      items.map((p) => (p.id === id ? { ...p, ...update } : p)),
    );
    setBatch(null);
  }
  const photoIds = photos.map((p) => p.id).join(",");
  useEffect(() => {
    if (mode !== "automatic" || !photoIds) {
      setDetecting(false);
      return;
    }
    let cancelled = false;
    setDetecting(true);
    Promise.all(
      photoIds.split(",").map(async (id) => {
        let detection;
        try {
          detection = await api(`/api/landmarks/${id}`, { method: "POST" });
        } catch (e) {
          detection = { status: "failure", reason: e.message, landmarks: [] };
        }
        if (!cancelled) changePhoto(id, { detection });
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
          uploaded.push({
            ...(await api("/api/photos", { method: "POST", body })),
            points: [],
          });
        } catch (e) {
          failures.push(`${file.name}: ${e.message}`);
        }
      }
      if (failures.length) setError(failures.join(" "));
      if (!uploaded.length) return;
      if (isReference) {
        setReference(uploaded[0]);
        try {
          const preset = await api(`/api/photos/${uploaded[0].id}/regions`);
          setComponents(preset.components);
        } catch {
          setComponents([]);
        }
        setRegionId(null);
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
        const points = p.detection?.status === "ok" ? p.detection.landmarks : p.detection?.diagnostics?.candidates?.[0]?.landmarks;
        if (!p.points?.length && points?.length === 4 && points.every((v) => Number.isFinite(v.x) && Number.isFinite(v.y)))
          changePhoto(p.id, { points: points.map((v) => [v.x, v.y]) });
      }
    }
    setMode(next);
    setBatch(null);
    setError("");
  }
  function setPoint(index, position) {
    const points = [...(photo.points || [])];
    points[index] = [
      Math.min(photo.width - 1, position[0]),
      Math.min(photo.height - 1, position[1]),
    ];
    changePhoto(photo.id, { points });
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
    if (tool === "landmarks" && mode === "manual") {
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
    const position = pointerPosition(event);
    if (drag.current.kind === "point") setPoint(drag.current.index, position);
    else setDraft(pixelBox(drag.current.start, position));
  }
  function endPointer(event) {
    if (!drag.current) return;
    const position = pointerPosition(event);
    if (drag.current.kind === "box")
      addRegion(pixelBox(drag.current.start, position));
    else {
      setPoint(drag.current.index, position);
      setPointIndex(Math.min(3, drag.current.index + 1));
    }
    drag.current = null;
    setDraft(null);
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
  const displayedPoints =
    mode === "manual"
      ? photo?.points || []
      : photo?.detection?.status === "ok"
        ? photo.detection.landmarks.map((p) => [p.x, p.y])
        : (photo?.detection?.diagnostics?.candidates?.[0]?.landmarks || []).map((p) => [p.x, p.y]);
  const radius = photo ? Math.max(photo.width, photo.height) / 85 : 10;
  const runHint = !health ? "Connect the local backend to begin."
    : !reference ? "Upload a known-good reference first."
    : !inspections.length ? "Add at least one inspection photo."
    : !components.length ? "Draw or add an expected component box on the reference."
    : detecting ? "Wait for landmark detection to finish."
    : mode === "manual" && photos.some((p) => !p.error && Array.from({ length: 4 }, (_, i) => p.points?.[i]).some((point) => !point || !point.every(Number.isFinite)))
      ? "Mark all four mounting holes on each photo before running."
      : "Ready to inspect. Review the mounting holes and expected parts before running.";

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="board-symbol" aria-hidden="true">
          ▦
        </div>
        <div>
          <h1>IndustryAI PCB inspection</h1>
          <p>
            Inspection workspace · Reference, alignment and component evidence.
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
        <fieldset className="workflow" disabled={busy}>
          <section className="upload-section" aria-labelledby="photos-heading">
            <div className="section-heading">
              <h2 id="photos-heading">1. Choose the board photos</h2>
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
                2. Define landmarks and expected parts
              </h2>
              <p>
                Point identities stay attached to the same mounting holes when a
                board rotates.
              </p>
            </div>
            <div className="mode-row">
              <fieldset className="mode-switch">
                <legend>Landmark mode</legend>
                {["manual", "automatic"].map((value) => (
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
                  ? "Mark four points on every photo in the displayed order."
                  : "Mounting holes must pass model and visual checks. Rejected sets are never used for scoring."}
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
                        : mode === "manual"
                          ? `${p.points.filter(Boolean).length}/4 points`
                          : p.detection?.status === "ok"
                            ? "Landmarks accepted"
                            : "Needs review"}
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
                        photo.detection?.status === "failure" && (
                          <div className="message notice">
                            <strong>Landmarks need review.</strong>{" "}
                            {photo.detection.reason}{" "}
                            <span>
                              Scoring will be skipped. Switch to Manual to
                              correct the tentative points; verify all four mounting holes.
                            </span>
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
                          : mode === "manual"
                            ? `Mark L${pointIndex}: ${names[pointIndex]}. Choose any point in the panel to correct it.`
                            : "Automatic landmarks are read-only. Manual correction requires switching modes."}
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
                                    if (tool === "boxes") return;
                                    e.stopPropagation();
                                    setRegionId(p.id);
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
                                    style={mode === "automatic" && photo.detection?.status !== "ok" ? {stroke: "#ff5050", strokeDasharray: "6 4"} : undefined}
                                  />
                                  <text
                                    x={point[0] + radius * 1.4}
                                    y={point[1] - radius}
                                    fontSize={radius * 1.7}
                                    className="canvas-label"
                                  >
                                    L{index}{mode === "automatic" && photo.detection?.status !== "ok" ? " tentative" : ""}
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
                  <h3>Four mounting-hole identities</h3>
                  <p className="muted">
                    Board-relative order, clockwise. Select a point, then click
                    its center.
                  </p>
                  <ol className="point-list">
                    {names.map((name, index) => (
                      <li
                        key={name}
                        className={pointIndex === index ? "active-point" : ""}
                      >
                        <button
                          disabled={mode !== "manual" || !!photo.error}
                          onClick={() => {
                            setPointIndex(index);
                            setTool("landmarks");
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
                                disabled={mode !== "manual" || !!photo.error}
                                value={
                                  displayedPoints[index]?.[axisIndex] ?? ""
                                }
                                onChange={(e) => {
                                  const value = Number(e.target.value);
                                  const point = [
                                    ...(photo.points[index] || [0, 0]),
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
                        {p.review_reason && <small>Review flagged</small>}
                      </button>
                    ))}
                  </div>
                  {activeRegion && referenceSelected && (
                    <div className="region-editor">
                      <label>
                        Component name
                        <input
                          aria-label="Component name"
                          value={activeRegion.name}
                          maxLength="120"
                          onChange={(e) =>
                            updateRegion({ name: e.target.value })
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
                                updateRegion({ bbox_xyxy_px: box });
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
              <h2 id="run-heading">3. Inspect and review</h2>
              <p className="run-hint" id="run-hint" role="status">{runHint}</p>
              <p className="threshold-note">
                Provisional Present threshold: {health?.comparison.present_min ?? "0.50"}.
                Other scores need review. Missing-part detection requires verified absence evidence;
                this one-board demo has no verified absence exemplar.
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
              <article
                className="result-sheet"
                data-testid={`result-${index}`}
                key={`${result.photo_id}-${index}`}
              >
                <div className="result-heading">
                  <h3>{result.filename}</h3>
                  <strong className={`status ${result.outcome}`}>
                    {outcomeName[result.outcome]}
                  </strong>
                </div>
                {result.alignment.status !== "ok" ? (
                  <div className="message notice">
                    <strong>Component scoring skipped.</strong>{" "}
                    {result.alignment.reason}
                    {batch.mode === "automatic" && (
                      <button
                        className="secondary"
                        onClick={() => switchMode("manual")}
                      >
                        Switch to Manual
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="result-images">
                    {[
                      ["Alignment overlay", result.alignment_overlay_url],
                      ["Component decisions", result.component_overlay_url],
                    ].map(([title, url]) => (
                      <figure key={title}>
                        <figcaption>{title}</figcaption>
                        <a href={url} target="_blank" rel="noreferrer">
                          <img
                            src={url}
                            alt={`${title} for ${result.filename}`}
                            loading="lazy"
                          />
                        </a>
                      </figure>
                    ))}
                  </div>
                )}
                {result.alignment_validation && <p>Alignment overlay score: {result.alignment_validation.overlay_score?.toFixed(4) ?? "unavailable"}; {result.alignment_validation.reliable ? "validated" : "REVIEW — correct landmarks or retake photo"}</p>}
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Component</th>
                        <th>Decision</th>
                        <th>Similarity</th>
                        <th>Best offset (px)</th>
                        <th>Expected box</th>
                        <th>Coverage</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.components.map((p, i) => (
                        <tr key={`${p.id}-${i}`}>
                          <th scope="row">{p.name}</th>
                          <td>
                            <span className={`status ${p.status}`}>
                              {p.display_status}
                            </span>
                          </td>
                          <td>{p.score == null ? "—" : p.score.toFixed(6)}</td>
                          <td>
                            {p.overlap == null
                              ? "—"
                              : `${(p.overlap * 100).toFixed(2)}%`}
                          </td>
                          <td className="reason">
                            {p.reason
                              ?.replace(/^explicit_review: /, "")
                              .replaceAll("_", " ")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>
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

createRoot(document.getElementById("root")).render(<App />);
