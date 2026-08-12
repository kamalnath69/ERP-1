function payloadFor(error) {
  return error?.response?.data || error?.data || error?.error?.data || {};
}

function pathFromLocation(location = []) {
  return location.filter((part) => !["body", "query", "path", "header"].includes(String(part))).join(".");
}

function pushError(target, path, message) {
  if (!path) return;
  target[path] = [...(target[path] || []), message || "Invalid value"];
}

export function normalizeApiError(error, fallback = "The request could not be completed") {
  const payload = payloadFor(error);
  const structured = payload?.error || {};
  const fieldErrors = {};
  const formErrors = Array.isArray(structured.form_errors) ? [...structured.form_errors] : [];

  Object.entries(structured.field_errors || {}).forEach(([path, messages]) => {
    const list = Array.isArray(messages) ? messages : [messages];
    list.filter(Boolean).forEach((message) => pushError(fieldErrors, path, String(message)));
  });

  const validation = payload.validation_errors || (Array.isArray(payload.detail) ? payload.detail : []);
  validation.forEach((item) => {
    const path = pathFromLocation(item?.loc);
    if (path) pushError(fieldErrors, path, item?.msg);
    else formErrors.push(item?.msg || "Invalid form values");
  });

  const detail = payload.detail;
  const message = structured.message
    || payload.display_detail
    || (typeof detail === "string" ? detail : null)
    || (formErrors.length ? formErrors[0] : null)
    || fallback;

  return {
    status: error?.response?.status || error?.status || error?.originalStatus || null,
    code: structured.code || error?.code || null,
    message,
    fieldErrors,
    formErrors,
    payload,
  };
}

export function applyApiErrors(error, setError, { aliases = {}, fallback } = {}) {
  const normalized = normalizeApiError(error, fallback);
  Object.entries(normalized.fieldErrors).forEach(([serverPath, messages]) => {
    const field = aliases[serverPath] || serverPath;
    setError(field, { type: "server", message: messages[0] }, { shouldFocus: false });
  });
  if (normalized.formErrors.length || !Object.keys(normalized.fieldErrors).length) {
    setError("root.server", {
      type: "server",
      message: normalized.formErrors.length ? normalized.formErrors.join(" ") : normalized.message,
    });
  }
  return normalized;
}

export function firstApiError(error, fallback) {
  return normalizeApiError(error, fallback).message;
}

export function zodFieldErrors(error) {
  const fieldErrors = {};
  const formErrors = [];
  for (const issue of error?.issues || []) {
    const path = issue.path?.join(".");
    if (path) pushError(fieldErrors, path, issue.message);
    else formErrors.push(issue.message || "Invalid form values");
  }
  return { fieldErrors, formErrors };
}
