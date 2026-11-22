import React, { useEffect, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import LiveInspection from "./pages/LiveInspection.jsx";
import AccessManagement from "./pages/AccessManagement.jsx";
import AccountSettings from "./pages/AccountSettings.jsx";
import { jsonBody, platformApi, session } from "./platformApi.js";
import "./platform.css";

function Login({ onLogin }) {
  const [form, setForm] = useState({ username: "admin", password: "" }), [error, setError] = useState("");
  async function submit(event) { event.preventDefault(); try { const result = await platformApi("/api/auth/login", jsonBody(form)); session.token = result.token; onLogin(result.user); } catch(e) { setError(e.message); } }
  return <main className="login-screen"><section className="login-brand"><span className="brand-mark">IA</span><p>IndustryAI / Automated optical inspection</p><h1>Evidence before decisions.</h1><p>Configure a golden PCB, inspect each board through one pipeline, and keep operator decisions auditable.</p><div className="trace-lines"><i/><i/><i/></div></section>
    <form className="login-card" onSubmit={submit}><span className="login-kicker">Local AOI console</span><h2>Sign in</h2><p>Use the administrator account configured at launch.</p>{error && <div className="platform-alert">{error}</div>}
      <label>Username<input autoFocus required value={form.username} onChange={e => setForm({...form,username:e.target.value})}/></label>
      <label>Password<input required type="password" value={form.password} onChange={e => setForm({...form,password:e.target.value})}/></label>
      <button className="primary">Open AOI console</button><small>First launch: set <code>PCB_ADMIN_PASSWORD</code> before starting backend.</small></form>
  </main>;
}

export default function PlatformApp({ inspectionLab }) {
  const initialPage = ["dashboard", "lab", "live", "access", "account"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "dashboard";
  const [user, setUser] = useState(null), [page, setPageState] = useState(initialPage), [checking, setChecking] = useState(true);
  const setPage = next => { location.hash = next; setPageState(next); };
  useEffect(() => { if (!session.token) return setChecking(false); platformApi("/api/auth/me").then(setUser).catch(() => { session.token = null; }).finally(() => setChecking(false)); }, []);
  function signOut() { session.token = null; setUser(null); }
  if (checking) return <main className="boot-screen">Starting AOI console…</main>;
  if (!user) return <Login onLogin={setUser}/>;
  const pages = { dashboard:<Dashboard onOpenLive={() => setPage("live")}/>, lab:inspectionLab, live:<LiveInspection user={user}/>,
    access:user.role === "administrator" ? <AccessManagement/> : <Dashboard onOpenLive={() => setPage("live")}/>, account:<AccountSettings user={user} onSignOut={signOut}/> };
  return <div className="platform-shell"><Sidebar page={page} onPage={setPage} user={user} onSignOut={signOut}/><main className="platform-content">{pages[page]}</main></div>;
}
