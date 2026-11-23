import React from "react";

const items = [
  ["dashboard", "Dashboard"],
  ["lab", "Inspection Lab"],
  ["live", "Live Inspection"],
  ["goldens", "Golden PCBs"],
  ["account", "Account Settings"],
];

export default function Sidebar({ page, onPage, user, onSignOut }) {
  return <aside className="platform-sidebar">
    <div className="platform-brand"><span className="brand-mark">FP</span><div><strong>ForgeSight</strong><small>PCB inspection</small></div></div>
    <nav aria-label="Primary navigation">
      {items.map(([id, label]) => <button key={id} className={page === id ? "active" : ""}
        onClick={() => onPage(id)}>
        {label}
      </button>)}
    </nav>
    <div className="sidebar-circuit" aria-hidden="true"><i/><i/><i/></div>
    <div className="sidebar-user"><div className="avatar">{user.display_name.slice(0, 2).toUpperCase()}</div>
      <div><strong>{user.display_name}</strong><small>{user.role}</small></div>
      <button onClick={onSignOut} title="Sign out">↪</button>
    </div>
  </aside>;
}
