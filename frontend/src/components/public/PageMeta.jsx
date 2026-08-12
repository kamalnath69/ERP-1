import { useEffect } from "react";

const SITE_URL = "https://edvatiq.app";

function meta(name, property = false) {
  const selector = property ? `meta[property="${name}"]` : `meta[name="${name}"]`;
  let node = document.head.querySelector(selector);
  if (!node) {
    node = document.createElement("meta");
    node.setAttribute(property ? "property" : "name", name);
    document.head.appendChild(node);
  }
  return node;
}

export default function PageMeta({ title, description, path = "/", robots = "index,follow" }) {
  useEffect(() => {
    const fullTitle = title.includes("Edvatiq") ? title : `${title} | Edvatiq`;
    const canonicalUrl = `${SITE_URL}${path === "/" ? "" : path}`;
    document.title = fullTitle;
    meta("description").setAttribute("content", description);
    meta("robots").setAttribute("content", robots);
    meta("og:title", true).setAttribute("content", fullTitle);
    meta("og:description", true).setAttribute("content", description);
    meta("og:type", true).setAttribute("content", "website");
    meta("og:url", true).setAttribute("content", canonicalUrl);
    let canonical = document.head.querySelector('link[rel="canonical"]');
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.rel = "canonical";
      document.head.appendChild(canonical);
    }
    canonical.href = canonicalUrl;
  }, [title, description, path, robots]);
  return null;
}
