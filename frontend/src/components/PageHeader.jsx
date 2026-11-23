import React from "react";

export default function PageHeader({ title, description, live = false, status = null }) {
  return <header className="platform-header"><div><h1>{title}</h1><p>{description}</p></div>
    <div className={`line-pill ${live ? "online" : ""}`}><span/>{status ? `Line ${status}` : live ? "Line connected" : "Local system"}</div>
  </header>;
}
