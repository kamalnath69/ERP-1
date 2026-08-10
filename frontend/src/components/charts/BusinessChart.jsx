import React, { useEffect, useRef } from "react";
import { useSelector } from "react-redux";
import * as echarts from "echarts/core";
import { BarChart, LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { selectAppearance } from "@/store/slices/preferencesSlice";

echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer]);

const FALLBACK_PALETTE = [
  "hsl(228 91% 64%)",
  "hsl(177 69% 42%)",
  "hsl(248 72% 65%)",
  "hsl(27 91% 59%)",
  "hsl(4 76% 63%)",
];

const safeColor = (value, fallback) => {
  const candidate = typeof value === "string" ? value.trim() : "";
  if (!candidate || ["undefined", "null"].includes(candidate.toLowerCase())) return fallback;
  if (typeof CSS !== "undefined" && CSS.supports && !CSS.supports("color", candidate)) return fallback;
  return candidate;
};

const cssColor = (styles, variable, fallback) => {
  const value = styles.getPropertyValue(variable).trim();
  return safeColor(value ? `hsl(${value})` : "", fallback);
};

const safeNumber = (value) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
};

const resizeWithoutAnimation = (chart) => {
  if (!chart || chart.isDisposed?.()) return;
  chart.resize({ animation: { duration: 0 } });
};

export default function BusinessChart({
  data = [],
  xKey = "date",
  series = [{ key: "value", label: "Value" }],
  type = "area",
  format = "number",
  height = 260,
  ariaLabel = "Business trend chart",
}) {
  const root = useRef(null);
  const chartRef = useRef(null);
  const appearance = useSelector(selectAppearance);

  useEffect(() => {
    if (!root.current) return undefined;
    chartRef.current = echarts.init(root.current, null, { renderer: "svg" });
    let resizeFrame;
    const observer = new ResizeObserver(() => {
      window.cancelAnimationFrame(resizeFrame);
      resizeFrame = window.requestAnimationFrame(() => resizeWithoutAnimation(chartRef.current));
    });
    observer.observe(root.current);
    return () => {
      window.cancelAnimationFrame(resizeFrame);
      observer.disconnect();
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return undefined;
    const styles = getComputedStyle(document.documentElement);
    const foreground = cssColor(styles, "--foreground", "hsl(157 19% 11%)");
    const muted = cssColor(styles, "--muted-foreground", "hsl(150 7% 44%)");
    const border = cssColor(styles, "--border", "hsl(150 10% 88%)");
    const card = cssColor(styles, "--card", "hsl(0 0% 100%)");
    const palette = FALLBACK_PALETTE.map((fallback, index) => cssColor(styles, `--chart-${index + 1}`, fallback));
    const rows = Array.isArray(data) ? data.filter((row) => row && typeof row === "object") : [];
    const seriesList = Array.isArray(series) && series.length ? series.filter((item) => item?.key) : [{ key: "value", label: "Value" }];
    const money = (value) => new Intl.NumberFormat("en-IN", {
      style: "currency", currency: "INR", maximumFractionDigits: 0,
    }).format(Number(value || 0));
    const valueFormatter = (value) => format === "money" ? money(value) : Number(value || 0).toLocaleString("en-IN");
    const categories = rows.map((row) => row[xKey] ?? "");
    const axisLabel = (value) => {
      if (!/^\d{4}-\d{2}-\d{2}/.test(String(value))) return String(value);
      return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(`${String(value).slice(0, 10)}T00:00:00`));
    };
    const option = type === "donut" ? {
      animation: false,
      color: palette,
      tooltip: {
        trigger: "item", backgroundColor: card, borderColor: border,
        textStyle: { color: foreground, fontFamily: "Manrope" },
        valueFormatter,
      },
      legend: { bottom: 0, icon: "circle", itemWidth: 7, itemHeight: 7, textStyle: { color: muted, fontFamily: "Manrope", fontSize: 11 } },
      series: [{
        type: "pie", radius: ["52%", "74%"], center: ["50%", "44%"],
        label: { show: false },
        itemStyle: { borderColor: card, borderWidth: 3, borderRadius: 5 },
        data: rows.map((row) => ({ name: row[xKey] ?? "", value: safeNumber(row[seriesList[0]?.key]) })),
      }],
    } : {
      animation: false,
      color: palette,
      textStyle: { color: foreground, fontFamily: "Manrope" },
      grid: { left: 8, right: 12, top: 18, bottom: 6, containLabel: true },
      tooltip: {
        trigger: "axis", backgroundColor: card, borderColor: border,
        extraCssText: "border-radius:12px;box-shadow:0 12px 30px rgba(0,0,0,.08)",
        textStyle: { color: foreground, fontFamily: "Manrope" },
        valueFormatter,
      },
      legend: seriesList.length > 1 ? { top: 0, right: 0, icon: "circle", itemWidth: 7, itemHeight: 7, textStyle: { color: muted, fontFamily: "Manrope", fontSize: 11 } } : undefined,
      xAxis: {
        type: "category", data: categories, boundaryGap: type === "bar",
        axisLabel: { color: muted, fontSize: 10, hideOverlap: true, formatter: axisLabel },
        axisLine: { lineStyle: { color: border } }, axisTick: { show: false },
      },
      yAxis: {
        type: "value", scale: true,
        axisLabel: {
          color: muted, fontSize: 10,
          formatter: (value) => format === "money"
            ? new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value)
            : new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value),
        },
        axisLine: { show: false }, axisTick: { show: false },
        splitLine: { lineStyle: { color: border, type: "dashed", opacity: 0.7 } },
      },
      series: seriesList.map((item, index) => {
        const seriesColor = safeColor(item.color, palette[index % palette.length]);
        return {
          name: item.label,
          type: type === "bar" ? "bar" : "line",
          data: rows.map((row) => safeNumber(row[item.key])),
          smooth: type !== "bar" ? 0.35 : undefined,
          symbol: "circle", symbolSize: 6, showSymbol: rows.length <= 12,
          lineStyle: { width: 2.5, color: seriesColor },
          itemStyle: { color: seriesColor },
          barMaxWidth: 34, barMinWidth: 8, barGap: "22%",
          areaStyle: type === "area" ? { color: seriesColor, opacity: 0.16 } : undefined,
        };
      }),
    };
    chart.setOption(option, { notMerge: true, lazyUpdate: false, silent: true });
    resizeWithoutAnimation(chart);
    return undefined;
  }, [appearance, data, format, series, type, xKey]);

  return <div ref={root} style={{ height }} className="w-full" role="img" aria-label={ariaLabel} />;
}
