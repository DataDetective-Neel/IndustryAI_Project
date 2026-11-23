import React, { useEffect, useState } from "react";
import PageHeader from "../components/PageHeader.jsx";
import EmptyState from "../components/EmptyState.jsx";
import { jsonBody, platformApi } from "../platformApi.js";

export default function GoldenLibrary() {
  const [references, setReferences] = useState([]), [name, setName] = useState(""), [file, setFile] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  async function refresh() { try { setReferences((await platformApi("/api/golden-library")).references); } catch (e) { setError(e.message); } }
  useEffect(() => { refresh(); }, []);
  async function addGolden(event) {
    event.preventDefault(); if (!file || busy) return; setBusy(true); setError(""); setNotice("");
    try {
      const body = new FormData(); body.append("image", file);
      const imported = await platformApi("/api/simulation/reference", {method:"POST", body});
      await platformApi("/api/golden-library", jsonBody({reference_id:imported.reference_id,name:name.trim() || file.name.replace(/\.[^.]+$/, "")}));
      setFile(null); setName(""); event.target.reset();
      setNotice("Golden PCB saved to the library."); await refresh();
      return;
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function remove(referenceId) { try { await platformApi(`/api/golden-library/${referenceId}`, { method: "DELETE" }); await refresh(); } catch (e) { setError(e.message); } }
  return <section className="platform-page"><PageHeader title="Golden PCB library" description="Store confirmed board references for reuse across inspections."/>
    {error && <div className="platform-alert">{error}</div>}{notice && <div className="platform-notice">{notice}</div>}
    <form className="platform-panel golden-add" onSubmit={addGolden}><div className="panel-heading"><div><h2>Add a golden PCB</h2><p>Upload a complete golden PCB image. Landmarks and components are processed automatically.</p></div></div>
      <label>Reference name<input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Controller board · Top side" maxLength="100"/></label>
      <label className="import-button">{file?.name || "Choose golden PCB image"}<input aria-label="Choose golden PCB image" type="file" accept="image/png,image/jpeg" onChange={e => setFile(e.target.files?.[0] || null)}/></label>
      <button className="primary" disabled={!file || busy}>{busy ? "Saving golden PCB…" : "Add to library"}</button>
    </form>
    <article className="platform-panel golden-list"><div className="panel-heading"><div><h2>Saved golden PCBs</h2><p>Stored in the local inspection database.</p></div><span>{references.length} saved</span></div>
      {!references.length ? <EmptyState title="No saved golden PCBs">Add a confirmed golden PCB to reuse it in live inspection.</EmptyState> : <div className="golden-grid">{references.map(item => <article key={item.reference_id}><img src={item.reference.image_url} alt={`${item.name} golden PCB`}/><div><h3>{item.name}</h3><p>{item.reference.filename} · {item.components.length} components</p><small>Saved {new Date(item.updated_at).toLocaleString()}</small><button className="danger" onClick={() => remove(item.reference_id)}>Remove</button></div></article>)}</div>}
    </article>
  </section>;
}
