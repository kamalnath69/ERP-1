/**
 * Utilities for handling client-side avatar upload (base64, no object storage).
 * Reads a File, resizes to <= max dimension, returns a data-URI JPEG.
 */
export async function fileToResizedDataUri(file, maxSize = 256, quality = 0.85) {
  return new Promise((resolve, reject) => {
    if (!file) return reject(new Error("No file"));
    if (!file.type.startsWith("image/")) return reject(new Error("Not an image file"));
    if (file.size > 5 * 1024 * 1024) return reject(new Error("Image too large (max 5MB)"));

    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("Invalid image"));
      img.onload = () => {
        const { width, height } = img;
        const scale = Math.min(1, maxSize / Math.max(width, height));
        const w = Math.round(width * scale);
        const h = Math.round(height * scale);
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, w, h);
        const dataUri = canvas.toDataURL("image/jpeg", quality);
        resolve(dataUri);
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

export function estimateBase64Bytes(dataUri) {
  if (!dataUri) return 0;
  const b64 = dataUri.split(",")[1] || "";
  return Math.floor((b64.length * 3) / 4);
}
