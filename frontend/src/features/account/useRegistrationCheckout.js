import { useEffect, useRef, useState } from "react";

import api from "@/lib/api";
import { loadCashfreeCheckout } from "@/lib/cashfree";
import { loadRazorpayCheckout } from "@/lib/razorpay";
import {
  boundedSignupRequest, clearSignupCheckout, saveSignupCheckout, updateSignupCheckout,
} from "@/lib/signupRegistration";

const confirmationDelays = [1200, 1700, 2200, 2700];
const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

function checkoutPhase(checkout) {
  if (!checkout) return "idle";
  if (checkout.next_action === "wait") return "waiting";
  if (checkout.next_action === "restart") return "restart";
  if (checkout.next_action === "support") return "support";
  if (checkout.next_action === "verify_email" || checkout.status === "completed") return "completed";
  return "ready";
}

function checkoutError(error, fallback) {
  return error?.response?.data?.detail || error?.message || fallback;
}

export function useRegistrationCheckout({
  initialCheckout,
  paymentReturnId,
  preloadProvider,
  onComplete,
  onCancelled,
  onReturnHandled,
}) {
  const [checkout, setCheckout] = useState(initialCheckout || null);
  const [phase, setPhase] = useState(initialCheckout ? "loading" : "idle");
  const [error, setError] = useState("");
  const mounted = useRef(true);
  const checkoutRef = useRef(initialCheckout || null);
  const onCompleteRef = useRef(onComplete);
  const onCancelledRef = useRef(onCancelled);
  const onReturnHandledRef = useRef(onReturnHandled);
  const initialRecoveryStarted = useRef(false);
  const requestRef = useRef(null);
  const creatingRef = useRef(false);
  const cancellingRef = useRef(false);
  const openingRef = useRef(false);
  const providerAttempt = useRef(0);
  const handoffWatchdog = useRef(null);

  onCompleteRef.current = onComplete;
  onCancelledRef.current = onCancelled;
  onReturnHandledRef.current = onReturnHandled;

  const clearWatchdog = () => {
    if (handoffWatchdog.current) window.clearTimeout(handoffWatchdog.current);
    handoffWatchdog.current = null;
  };

  const acceptCheckout = (data) => {
    const current = checkoutRef.current;
    const merged = {
      ...current,
      ...data,
      checkout_token: data?.checkout_token || current?.checkout_token,
    };
    checkoutRef.current = merged;
    if (merged.checkout_id && merged.checkout_token) {
      if (current?.checkout_id === merged.checkout_id) updateSignupCheckout(merged);
      else saveSignupCheckout(merged);
    }
    if (!mounted.current) return merged;
    setCheckout(merged);
    setError("");
    const nextPhase = checkoutPhase(merged);
    setPhase(nextPhase);
    if (nextPhase === "completed") onCompleteRef.current?.(merged);
    return merged;
  };

  const requestStatus = async ({ reconcile = false, confirm = false, confirmPay = false, initial = false } = {}) => {
    if (requestRef.current) return requestRef.current;
    const current = checkoutRef.current;
    if (!current?.checkout_id || !current?.checkout_token) return null;

    const task = (async () => {
      if (mounted.current) {
        setError("");
        setPhase(initial ? "loading" : "reconciling");
      }
      try {
        const request = (useReconcile) => boundedSignupRequest((signal) => useReconcile
          ? api.post(`/auth/registration/checkouts/${current.checkout_id}/reconcile`, {}, {
            headers: { "X-Signup-Token": current.checkout_token }, signal,
          })
          : api.get(`/auth/registration/checkouts/${current.checkout_id}`, {
            headers: { "X-Signup-Token": current.checkout_token }, forceRefetch: true, signal,
          }));
        let { data } = await request(reconcile);
        acceptCheckout(data);
        if (confirm && (data.next_action === "wait" || (confirmPay && data.next_action === "pay"))) {
          for (const delay of confirmationDelays) {
            await wait(delay);
            if (!mounted.current) break;
            ({ data } = await request(true));
            acceptCheckout(data);
            if (data.next_action !== "wait" && !(confirmPay && data.next_action === "pay")) break;
          }
        }
        if (confirmPay && data.next_action === "pay" && mounted.current) {
          setPhase("ready");
          setError("Payment has not been confirmed. You can safely try again.");
        }
        return data;
      } catch (requestError) {
        if (mounted.current) {
          setError(checkoutError(requestError, "Payment status could not be checked"));
          setPhase(initial ? "error" : checkoutPhase(checkoutRef.current));
        }
        return null;
      }
    })();

    requestRef.current = task;
    try { return await task; }
    finally {
      if (requestRef.current === task) requestRef.current = null;
    }
  };

  const finishOpening = (attempt) => {
    if (attempt !== providerAttempt.current || !openingRef.current) return false;
    clearWatchdog();
    openingRef.current = false;
    if (mounted.current) setPhase(checkoutPhase(checkoutRef.current));
    return true;
  };

  const reconcileProviderResult = (attempt, providerMessage = "", confirmationExpected = false) => {
    const currentAttempt = finishOpening(attempt);
    if (!currentAttempt && openingRef.current) return;
    void requestStatus({ reconcile: true, confirm: confirmationExpected, confirmPay: confirmationExpected }).then((data) => {
      if (currentAttempt && mounted.current && data?.next_action === "pay" && providerMessage) {
        setError(providerMessage);
      }
    });
  };

  const armWatchdog = (attempt) => {
    clearWatchdog();
    handoffWatchdog.current = window.setTimeout(() => {
      handoffWatchdog.current = null;
      if (attempt !== providerAttempt.current || !openingRef.current) return;
      openingRef.current = false;
      if (mounted.current) setPhase(checkoutPhase(checkoutRef.current));
      void requestStatus({ reconcile: checkoutRef.current?.provider === "cashfree" }).then((data) => {
        if (mounted.current && data?.next_action === "pay") {
          setError("The payment window did not respond. You can safely try again.");
        }
      });
    }, 13000);
  };

  const verifyRazorpay = async (attempt, current, result) => {
    const currentAttempt = finishOpening(attempt);
    if (currentAttempt && mounted.current) setPhase("reconciling");
    try {
      const { data } = await boundedSignupRequest((signal) => api.post("/auth/registration/payment/verify", {
        checkout_id: current.checkout_id,
        checkout_token: current.checkout_token,
        razorpay_order_id: result.razorpay_order_id,
        razorpay_payment_id: result.razorpay_payment_id,
        razorpay_signature: result.razorpay_signature,
      }, { signal }));
      if (checkoutRef.current?.checkout_id === current.checkout_id) {
        acceptCheckout(data);
        if (data.next_action === "wait") await requestStatus({ reconcile: true, confirm: true });
      }
    } catch (requestError) {
      if (mounted.current && checkoutRef.current?.checkout_id === current.checkout_id) {
        setPhase(checkoutPhase(checkoutRef.current));
        setError(checkoutError(requestError, "Payment confirmation failed"));
      }
    }
  };

  const beginCashfree = async (current, attempt) => {
    try {
      await loadCashfreeCheckout();
      if (attempt !== providerAttempt.current || !openingRef.current) return;
      if (!current.payment_session_id) throw new Error("This payment session is unavailable. Start a new checkout.");
      const cashfree = window.Cashfree({
        mode: current.checkout_mode || (current.mode === "test" ? "sandbox" : "production"),
      });
      const result = cashfree.checkout({
        paymentSessionId: current.payment_session_id,
        redirectTarget: "_modal",
      });
      Promise.resolve(result).then((providerResult) => {
        const providerMessage = providerResult?.error?.message || "";
        reconcileProviderResult(attempt, providerMessage, !providerMessage);
      }).catch((providerError) => {
        reconcileProviderResult(attempt, providerError?.message || "Cashfree checkout could not be completed");
      });
    } catch (providerError) {
      const currentAttempt = finishOpening(attempt);
      if (currentAttempt && mounted.current) setError(providerError?.message || "Cashfree checkout could not be loaded");
    }
  };

  const beginRazorpay = async (current, attempt) => {
    try {
      await loadRazorpayCheckout();
      if (attempt !== providerAttempt.current || !openingRef.current) return;
      if (!current.key_id || !current.order_id) throw new Error("This payment session is unavailable. Start a new checkout.");
      const modal = new window.Razorpay({
        key: current.key_id,
        amount: current.amount_paise,
        currency: current.currency,
        order_id: current.order_id,
        name: "Edvatiq",
        description: `${current.plan?.name || "Plan"} registration`,
        handler: (result) => { void verifyRazorpay(attempt, current, result); },
        modal: {
          ondismiss: () => reconcileProviderResult(attempt),
        },
        theme: { color: "#0f4a38" },
      });
      modal.on("payment.failed", (result) => {
        reconcileProviderResult(attempt, result?.error?.description || "Payment was not completed");
      });
      modal.open();
    } catch (providerError) {
      const currentAttempt = finishOpening(attempt);
      if (currentAttempt && mounted.current) setError(providerError?.message || "Razorpay checkout could not be loaded");
    }
  };

  const beginMockPayment = async (current, attempt) => {
    try {
      const { data } = await boundedSignupRequest((signal) => api.post(
        `/auth/registration/checkouts/${current.checkout_id}/mock-pay`,
        { checkout_token: current.checkout_token }, { signal },
      ));
      finishOpening(attempt);
      acceptCheckout(data);
    } catch (requestError) {
      finishOpening(attempt);
      if (mounted.current) setError(checkoutError(requestError, "Test payment failed"));
    }
  };

  const openCheckout = (value = checkoutRef.current) => {
    const current = value || checkoutRef.current;
    if (!current || openingRef.current || cancellingRef.current || requestRef.current) return;
    checkoutRef.current = current;
    const attempt = providerAttempt.current + 1;
    providerAttempt.current = attempt;
    openingRef.current = true;
    if (mounted.current) {
      setCheckout(current);
      setError("");
      setPhase("opening");
    }
    armWatchdog(attempt);
    if (current.mock_mode || current.mode === "mock") { void beginMockPayment(current, attempt); return; }
    if (current.provider === "cashfree") { void beginCashfree(current, attempt); return; }
    void beginRazorpay(current, attempt);
  };

  const createCheckout = async (run) => {
    if (creatingRef.current || checkoutRef.current) return checkoutRef.current;
    creatingRef.current = true;
    if (mounted.current) {
      setError("");
      setPhase("creating");
    }
    try {
      const created = await run();
      return acceptCheckout(created);
    } catch (requestError) {
      if (mounted.current) setPhase("idle");
      throw requestError;
    } finally {
      creatingRef.current = false;
    }
  };

  const cancelCheckout = async () => {
    const current = checkoutRef.current;
    if (!current || cancellingRef.current) return false;
    cancellingRef.current = true;
    if (mounted.current) {
      setError("");
      setPhase("cancelling");
    }
    try {
      await boundedSignupRequest((signal) => api.post(
        `/auth/registration/checkouts/${current.checkout_id}/cancel`, {},
        { headers: { "X-Signup-Token": current.checkout_token }, signal },
      ));
      clearWatchdog();
      providerAttempt.current += 1;
      openingRef.current = false;
      checkoutRef.current = null;
      clearSignupCheckout();
      if (mounted.current) {
        setCheckout(null);
        setPhase("idle");
        setError("");
      }
      onCancelledRef.current?.();
      return true;
    } catch (requestError) {
      if (requestError?.response?.status === 409) await requestStatus({ reconcile: true });
      else if (mounted.current) {
        setError(checkoutError(requestError, "Checkout could not be cancelled"));
        setPhase(checkoutPhase(checkoutRef.current));
      }
      throw requestError;
    } finally {
      cancellingRef.current = false;
    }
  };

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearWatchdog();
    };
  }, []);

  useEffect(() => {
    if (!preloadProvider) return;
    const loader = preloadProvider === "cashfree" ? loadCashfreeCheckout : loadRazorpayCheckout;
    void loader().catch(() => undefined);
  }, [preloadProvider]);

  useEffect(() => {
    if (initialRecoveryStarted.current) return;
    initialRecoveryStarted.current = true;
    const current = checkoutRef.current;
    if (!current) {
      if (paymentReturnId) onReturnHandledRef.current?.();
      return;
    }
    const returned = Boolean(paymentReturnId && paymentReturnId === current.checkout_id);
    void requestStatus({ reconcile: returned, confirm: returned, confirmPay: returned, initial: true })
      .then((data) => {
        if (mounted.current && paymentReturnId && data?.next_action !== "verify_email" && data?.status !== "completed") {
          onReturnHandledRef.current?.();
        }
      });
    // Recovery belongs to the checkout present when the registration route mounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    checkout,
    phase,
    error,
    createCheckout,
    openCheckout,
    cancelCheckout,
    retryRecovery: () => { void requestStatus({ initial: true }); },
    confirmPending: () => { void requestStatus({ reconcile: true, confirm: true }); },
  };
}
