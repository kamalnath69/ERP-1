import api from "@/lib/api";

let currentDocumentsRequest = null;
const historicalDocumentRequests = new Map();

export async function loadPublicLegalDocument(kind, version) {
  if (version) return loadHistoricalDocument(kind, version);

  if (!currentDocumentsRequest) {
    currentDocumentsRequest = api.get("/public/legal/current", { forceRefetch: true })
      .then(({ data }) => data?.documents || {})
      .catch((error) => {
        currentDocumentsRequest = null;
        throw error;
      });
  }

  const documents = await currentDocumentsRequest;
  const document = documents[kind];
  if (!document?.content_markdown) {
    currentDocumentsRequest = null;
    throw new Error("Legal document is unavailable");
  }
  return document;
}

export function clearPublicLegalDocumentCache() {
  currentDocumentsRequest = null;
  historicalDocumentRequests.clear();
}

function loadHistoricalDocument(kind, version) {
  const key = `${kind}:${version}`;
  if (!historicalDocumentRequests.has(key)) {
    const request = api.get(`/public/legal/${kind}/${version}`, { forceRefetch: true })
      .then(({ data }) => {
        if (!data?.content_markdown) throw new Error("Legal document is unavailable");
        return data;
      })
      .catch((error) => {
        historicalDocumentRequests.delete(key);
        throw error;
      });
    historicalDocumentRequests.set(key, request);
  }
  return historicalDocumentRequests.get(key);
}
