import { useEffect, useRef, useState } from "react";

import api from "@/lib/api";
import {
  boundedSignupRequest, clearSignupEmailVerification, readSignupEmailVerification,
  saveSignupEmailVerification,
} from "@/lib/signupRegistration";

const normalizedEmail = (value) => String(value || "").trim().toLowerCase();
const secondsUntil = (value, now) => Math.max(0, Math.ceil((Date.parse(value || "") - now) / 1000));

function initialState() {
  const stored = readSignupEmailVerification();
  if (!stored) return { status: "idle", challenge: null };
  return {
    status: stored.verification_proof ? "verified" : "code",
    challenge: stored,
  };
}

function message(error, fallback) {
  const detail = error?.response?.data?.detail;
  return typeof detail === "string" ? detail : error?.message || fallback;
}

export function useSignupEmailVerification() {
  const initial = useRef(initialState()).current;
  const [status, setStatus] = useState(initial.status);
  const [challenge, setChallenge] = useState(initial.challenge);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [testCode, setTestCode] = useState("");
  const [now, setNow] = useState(Date.now());
  const requestRef = useRef(null);

  useEffect(() => {
    if (!challenge) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [challenge]);

  useEffect(() => {
    if (status !== "verified" || !challenge?.proof_expires_at) return;
    if (Date.parse(challenge.proof_expires_at) > now) return;
    clearSignupEmailVerification();
    setChallenge(null);
    setStatus("idle");
    setError("Email verification expired. Send a new code to continue.");
  }, [challenge, now, status]);

  const clear = () => {
    clearSignupEmailVerification();
    setChallenge(null);
    setCode("");
    setError("");
    setTestCode("");
    setStatus("idle");
  };

  const restore = (value) => {
    const saved = saveSignupEmailVerification(value);
    if (!saved) return false;
    setChallenge(saved);
    setCode("");
    setError("");
    setTestCode("");
    setNow(Date.now());
    setStatus(saved.verification_proof ? "verified" : "code");
    return true;
  };

  const send = async (email) => {
    if (requestRef.current) return requestRef.current;
    const task = (async () => {
      setStatus("sending");
      setError("");
      try {
        const { data } = await boundedSignupRequest((signal) => api.post(
          "/auth/registration/email/challenges",
          { email: normalizedEmail(email) },
          { signal },
        ));
        const saved = saveSignupEmailVerification(data);
        setChallenge(saved);
        setCode("");
        setTestCode(data.test_code || "");
        setNow(Date.now());
        setStatus("code");
        return data;
      } catch (requestError) {
        setStatus(challenge ? "code" : "idle");
        setError(message(requestError, "Verification code could not be sent"));
        throw requestError;
      }
    })();
    requestRef.current = task;
    try { return await task; }
    finally { requestRef.current = null; }
  };

  const verify = async () => {
    if (requestRef.current || !challenge) return null;
    if (!/^\d{6}$/.test(code)) {
      setError("Enter the six-digit verification code");
      return null;
    }
    const task = (async () => {
      setStatus("verifying");
      setError("");
      try {
        const { data } = await boundedSignupRequest((signal) => api.post(
          `/auth/registration/email/challenges/${challenge.challenge_id}/verify`,
          { challenge_token: challenge.challenge_token, code },
          { signal },
        ));
        const saved = saveSignupEmailVerification({
          ...challenge,
          verification_proof: data.verification_proof,
          proof_expires_at: data.proof_expires_at,
        });
        setChallenge(saved);
        setCode("");
        setTestCode("");
        setStatus("verified");
        return data;
      } catch (requestError) {
        setStatus("code");
        setError(message(requestError, "Email could not be verified"));
        throw requestError;
      }
    })();
    requestRef.current = task;
    try { return await task; }
    finally { requestRef.current = null; }
  };

  const invalidateIfDifferent = (email) => {
    if (challenge && normalizedEmail(email) !== challenge.email) clear();
  };

  return {
    status,
    challenge,
    code,
    setCode: (value) => { setCode(value.replace(/\D/g, "").slice(0, 6)); setError(""); },
    error,
    testCode,
    resendSeconds: secondsUntil(challenge?.resend_at, now),
    expiresSeconds: secondsUntil(challenge?.expires_at, now),
    isVerified: (email) => status === "verified"
      && Boolean(challenge?.verification_proof)
      && normalizedEmail(email) === challenge?.email,
    proofPayload: challenge?.verification_proof ? {
      challenge_id: challenge.challenge_id,
      proof: challenge.verification_proof,
    } : null,
    send,
    verify,
    clear,
    restore,
    invalidateIfDifferent,
  };
}
