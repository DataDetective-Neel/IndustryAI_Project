import React, { useState } from "react";
import PageHeader from "../components/PageHeader.jsx";
import { jsonBody, platformApi } from "../platformApi.js";

export default function AccountSettings({ user, onSignOut }) {
  const [preferences, setPreferences] = useState({ alarm_sound: user.preferences.alarm_sound ?? true,
    inspection_interval: user.preferences.inspection_interval ?? 3, simulation_directory: user.preferences.simulation_directory ?? "PCB_Dataset_Pilot/images/test" });
  const [password, setPassword] = useState({ current_password: "", new_password: "" }), [message, setMessage] = useState("");
  async function save(event) { event.preventDefault(); try { await platformApi("/api/account/preferences", jsonBody(preferences, "PATCH")); setMessage("Preferences saved."); } catch(e) { setMessage(e.message); } }
  async function change(event) { event.preventDefault(); try { await platformApi("/api/account/password", jsonBody(password)); onSignOut(); } catch(e) { setMessage(e.message); } }
  return <section className="platform-page"><PageHeader title="Account settings" description="Profile, alarm, and simulation defaults."/>
    {message && <div className="platform-notice">{message}</div>}<div className="access-grid">
      <form className="platform-panel account-form" onSubmit={save}><div className="profile-block"><div className="avatar large">{user.display_name.slice(0,2).toUpperCase()}</div><div><h2>{user.display_name}</h2><p>@{user.username} · {user.role}</p></div></div>
        <label className="toggle-row"><span><strong>Audible defect alarm</strong><small>Play an alert for each new review.</small></span><input type="checkbox" checked={preferences.alarm_sound} onChange={e => setPreferences({...preferences, alarm_sound:e.target.checked})}/></label>
        <label>Default inspection interval<input type="number" min="0.5" max="120" step="0.5" value={preferences.inspection_interval} onChange={e => setPreferences({...preferences, inspection_interval:Number(e.target.value)})}/></label>
        <label>Default simulation directory<input value={preferences.simulation_directory} onChange={e => setPreferences({...preferences, simulation_directory:e.target.value})}/></label>
        <button className="primary">Save preferences</button>
      </form>
      <form className="platform-panel account-form" onSubmit={change}><div className="panel-heading"><div><h2>Change password</h2><p>Changing it ends all active sessions.</p></div></div>
        <label>Current password<input required type="password" value={password.current_password} onChange={e => setPassword({...password,current_password:e.target.value})}/></label>
        <label>New password<input required type="password" minLength="10" value={password.new_password} onChange={e => setPassword({...password,new_password:e.target.value})}/></label>
        <button>Change password</button>
      </form>
    </div></section>;
}
