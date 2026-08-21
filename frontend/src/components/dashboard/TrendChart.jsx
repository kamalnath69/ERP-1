import React from "react";
import BusinessChart from "@/components/charts/BusinessChart";

export default function TrendChart({
  data = [], format = "number", type = "area", xKey = "date", series, height, ariaLabel,
}) {
  const resolvedSeries = Array.isArray(series) && series.length
    ? series.filter((item) => item?.key)
    : [{ key: format === "money" ? "value_paise" : "value", label: "Value" }];
  const points = (Array.isArray(data) ? data : []).map((point) => {
    const normalized = { ...point };
    resolvedSeries.forEach((item) => {
      normalized[item.key] = format === "money"
        ? Number(point[item.key] || 0) / 100
        : Number(point[item.key] || 0);
    });
    return normalized;
  });
  return <BusinessChart
    data={points}
    format={format}
    type={type}
    xKey={xKey}
    series={resolvedSeries}
    height={height}
    ariaLabel={ariaLabel || "Business performance chart"}
  />;
}
