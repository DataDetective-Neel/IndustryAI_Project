import React from "react";

const items = [
  ["dashboard", "Dashboard", "⌁"],
  ["lab", "Inspection Lab", "▦"],
  ["live", "Live Inspection", "◉"],
  ["access", "Access Management", "♙"],
  ["account", "Account Settings", "◌"],
];

export default function Sidebar({ page, onPage, user, onSignOut }) {
  return <aside className="platform-sidebar">
    <div className="platform-brand"><span className="brand-mark">IA</span><div><strong>IndustryAI</strong><small>AOI control</small></div></div>
    <nav aria-label="Primary navigation">
      {items.map(([id, label, icon]) => <button key={id} className={page === id ? "active" : ""}
        onClick={() => onPage(id)} disabled={id === "access" && user.role !== "administrator"}>
        <span aria-hidden="true">{icon}</span>{label}
      </button>)}
    </nav>
    <div className="sidebar-circuit" aria-hidden="true"><i/><i/><i/></div>
    <div className="sidebar-user"><div className="avatar">{user.display_name.slice(0, 2).toUpperCase()}</div>
      <div><strong>{user.display_name}</strong><small>{user.role}</small></div>
      <button onClick={onSignOut} title="Sign out">↪</button>
    </div>
  </aside>;
}
