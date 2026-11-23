import React, { useEffect, useState } from "react";
import PageHeader from "../components/PageHeader.jsx";
import { jsonBody, platformApi } from "../platformApi.js";

const blank = { username: "", display_name: "", role: "operator", password: "" };

export default function AccessManagement() {
  const [users, setUsers] = useState([]), [form, setForm] = useState(blank), [error, setError] = useState("");
  const load = () => platformApi("/api/users").then(data => setUsers(data.users)).catch(error => setError(error.message));
  useEffect(() => { void load(); }, []);
  async function create(event) { event.preventDefault(); try { await platformApi("/api/users", jsonBody(form)); setForm(blank); load(); } catch (e) { setError(e.message); } }
  return <section className="platform-page"><PageHeader title="Access management" description="Local users and backend-enforced AOI roles."/>
    {error && <div className="platform-alert">{error}</div>}<div className="access-grid">
      <article className="platform-panel"><div className="panel-heading"><div><h2>Authorized users</h2><p>{users.length} active account{users.length === 1 ? "" : "s"}</p></div></div>
        <div className="user-list">{users.map(user => <div key={user.username}><div className="avatar">{user.display_name.slice(0,2).toUpperCase()}</div><div><strong>{user.display_name}</strong><small>@{user.username}</small></div><span className="role-chip">{user.role}</span></div>)}</div>
      </article>
      <form className="platform-panel account-form" onSubmit={create}><div className="panel-heading"><div><h2>Add user</h2><p>Passwords are PBKDF2-hashed before storage.</p></div></div>
        <label>Full name<input required value={form.display_name} onChange={e => setForm({...form, display_name:e.target.value})}/></label>
        <label>Username<input required value={form.username} onChange={e => setForm({...form, username:e.target.value})}/></label>
        <label>Role<select value={form.role} onChange={e => setForm({...form, role:e.target.value})}><option value="operator">Operator</option><option value="supervisor">Supervisor</option><option value="administrator">Administrator</option></select></label>
        <label>Temporary password<input required minLength="10" type="password" value={form.password} onChange={e => setForm({...form, password:e.target.value})}/></label>
        <button className="primary">Create user</button>
      </form>
    </div></section>;
}
