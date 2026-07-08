import React, { useRef, useState } from "react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Camera, Trash } from "@phosphor-icons/react";
import { fileToResizedDataUri, estimateBase64Bytes } from "@/lib/avatar";
import { toast } from "sonner";

/**
 * Reusable avatar uploader — controlled component.
 * onChange(dataUri | null) is called after user picks a file (already resized) or clears.
 */
export default function AvatarUploader({ value, onChange, initials = "?", size = 96, disabled = false }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);

  const pick = () => !disabled && inputRef.current && inputRef.current.click();

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const dataUri = await fileToResizedDataUri(file, 256, 0.85);
      const bytes = estimateBase64Bytes(dataUri);
      if (bytes > 120 * 1024) {
        toast.warning(`Avatar is ${(bytes / 1024).toFixed(0)} KB after resize — using a smaller image is recommended.`);
      }
      onChange(dataUri);
    } catch (err) {
      toast.error(err.message || "Failed to process image");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="flex items-center gap-4" data-testid="avatar-uploader">
      <div className="relative">
        <Avatar
          className="rounded-sm"
          style={{ width: size, height: size }}
        >
          {value ? <AvatarImage src={value} alt="avatar" /> : null}
          <AvatarFallback className="rounded-sm bg-primary text-primary-foreground text-2xl font-display">
            {initials}
          </AvatarFallback>
        </Avatar>
      </div>
      <div className="flex flex-col gap-2">
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFile}
          data-testid="avatar-input"
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="rounded-sm"
          onClick={pick}
          disabled={disabled || busy}
          data-testid="avatar-upload-btn"
        >
          <Camera size={14} className="mr-2" /> {value ? "Change" : "Upload"} avatar
        </Button>
        {value && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="rounded-sm text-destructive"
            onClick={() => onChange(null)}
            disabled={disabled || busy}
          >
            <Trash size={14} className="mr-2" /> Remove
          </Button>
        )}
        <span className="text-[11px] text-muted-foreground">JPG/PNG · resized to 256px · stored as base64</span>
      </div>
    </div>
  );
}
