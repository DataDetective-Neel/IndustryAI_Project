import React from "react";

export default function EmptyState({ title, children }) {
  return <div className="platform-empty"><span>◎</span><strong>{title}</strong><p>{children}</p></div>;
}
