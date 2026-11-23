import React from "react";
import { platformApi, jsonBody } from "../platformApi.js";

export default function PageHeader({ title, description, live = false, status = null }) {
  const [enabled, setEnabled] = React.useState(() => localStorage.getItem("aoi_alarm_sound") !== "false");
  React.useEffect(() => { platformApi("/api/auth/me").then(user => setEnabled(user.preferences.alarm_sound !== false && localStorage.getItem("aoi_alarm_sound") !== "false")).catch(() => {}); }, []);
  async function toggleAlarm() {
    const next = !enabled; setEnabled(next); localStorage.setItem("aoi_alarm_sound", String(next));
    try { const result = await platformApi("/api/account/preferences", jsonBody({ alarm_sound: next }, "PATCH")); setEnabled(result.alarm_sound !== false); }
    catch { setEnabled(!next); localStorage.setItem("aoi_alarm_sound", String(!next)); }
  }
  return <header className="platform-header"><div><h1>{title}</h1><p>{description}</p></div>
    <div className="header-actions"><label className="alarm-toggle"><input aria-label="Audible alarm" type="checkbox" checked={enabled} onChange={toggleAlarm}/><span>Alarm on</span></label>
      <div className={`line-pill ${live ? "online" : ""}`}><span/>{status ? `Line ${status}` : live ? "Line connected" : "Local system"}</div></div>
  </header>;
}
