import React from "react";
import { Navigate, useParams } from "react-router-dom";

export default function RegisterPayment() {
  const { checkoutId } = useParams();
  const target = checkoutId
    ? `/register?payment_return=${encodeURIComponent(checkoutId)}`
    : "/register";
  return <Navigate to={target} replace />;
}
