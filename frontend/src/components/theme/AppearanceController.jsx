import { useEffect } from "react";
import { useSelector } from "react-redux";
import { selectAppearance } from "@/store/slices/preferencesSlice";

function applyAppearance(appearance) {
  const dark = appearance === "dark" || (appearance === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.dataset.appearance = appearance;
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

export default function AppearanceController() {
  const appearance = useSelector(selectAppearance);
  useEffect(() => {
    applyAppearance(appearance);
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => appearance === "system" && applyAppearance("system");
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, [appearance]);
  return null;
}
