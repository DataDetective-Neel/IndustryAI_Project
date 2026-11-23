export const session = {
  get token() { return localStorage.getItem("aoi_token"); },
  set token(value) { value ? localStorage.setItem("aoi_token", value) : localStorage.removeItem("aoi_token"); },
};

export async function platformApi(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (session.token) headers.set("Authorization", `Bearer ${session.token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...options, headers });
  let body;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) throw new Error(body?.detail || `Request failed (${response.status})`);
  return body;
}

export const jsonBody = (value, method = "POST") => ({ method, body: JSON.stringify(value) });
