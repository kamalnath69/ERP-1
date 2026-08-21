export const FALLBACK_PUBLIC_PHONE = "+919787867648";

export function publicPhone(phone) {
  const value = String(phone || FALLBACK_PUBLIC_PHONE).trim();
  const digits = value.replace(/\D/g, "");
  if (digits.length === 10) return `+91${digits}`;
  return value.startsWith("+") ? `+${digits}` : `+${digits}`;
}

export function displayPublicPhone(phone) {
  const canonical = publicPhone(phone);
  const digits = canonical.replace(/\D/g, "");
  if (digits.length === 12 && digits.startsWith("91")) {
    return `+91 ${digits.slice(2, 7)} ${digits.slice(7)}`;
  }
  return canonical;
}

export function publicContactLinks(phone, message = "Hi Edvatiq, I'd like to discuss a custom software project.") {
  const canonical = publicPhone(phone);
  return {
    phone: canonical,
    display: displayPublicPhone(canonical),
    tel: `tel:${canonical}`,
    whatsapp: `https://wa.me/${canonical.replace(/\D/g, "")}?text=${encodeURIComponent(message)}`,
  };
}
