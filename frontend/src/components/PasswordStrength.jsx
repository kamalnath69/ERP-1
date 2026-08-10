import React from "react";
import { Check, X } from "@phosphor-icons/react";

const commonPasswords = new Set(["password", "password123", "qwerty123", "admin123", "welcome123", "letmein123"]);

export function passwordChecks(password = "") {
  return {
    length: password.length >= 10,
    upper: /[A-Z]/.test(password),
    lower: /[a-z]/.test(password),
    number: /\d/.test(password),
    symbol: /[^A-Za-z0-9]/.test(password),
    long: password.length >= 14,
    uncommon: password.length > 0 && !commonPasswords.has(password.toLowerCase()),
  };
}

export function isPasswordAcceptable(password) {
  const checks = passwordChecks(password);
  return checks.length && checks.upper && checks.lower && checks.number && checks.uncommon;
}

export default function PasswordStrength({ password = "", compact = false }) {
  const checks = passwordChecks(password);
  const score = !password ? 0 : Math.min(4, [checks.length, checks.upper && checks.lower, checks.number, checks.symbol, checks.long, checks.uncommon].filter(Boolean).length - 1);
  const labels = ["Too weak", "Weak", "Fair", "Good", "Strong"];
  const colors = ["bg-red-500", "bg-red-500", "bg-amber-500", "bg-lime-600", "bg-emerald-600"];
  return <div className="mt-3" aria-live="polite"><div className="flex items-center gap-3"><div className="grid grid-cols-4 gap-1.5 flex-1">{[1, 2, 3, 4].map((level) => <span key={level} className={`h-1.5 rounded-full ${score >= level ? colors[score] : "bg-border"}`} />)}</div><span className={`text-xs font-semibold ${score <= 1 ? "text-red-600" : score === 2 ? "text-amber-700" : "text-emerald-700"}`}>{labels[score]}</span></div>{!compact && <div className="grid sm:grid-cols-2 gap-x-4 gap-y-1 mt-3">{[["length", "10 or more characters"], ["upper", "One uppercase letter"], ["lower", "One lowercase letter"], ["number", "One number"]].map(([key, label]) => <div key={key} className={`text-xs flex items-center gap-1.5 ${checks[key] ? "text-emerald-700" : "text-muted-foreground"}`}>{checks[key] ? <Check weight="bold" /> : <X />} {label}</div>)}</div>}</div>;
}
