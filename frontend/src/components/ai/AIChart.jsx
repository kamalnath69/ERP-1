import React, { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TitleComponent, ToolboxComponent, TooltipComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { cn } from "@/lib/utils";

echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TitleComponent, ToolboxComponent, TooltipComponent, SVGRenderer]);

const FALLBACK_COLORS = {
  accent: "hsl(27 100% 55%)",
  foreground: "hsl(157 19% 11%)",
  muted: "hsl(150 7% 44%)",
  border: "hsl(150 10% 88%)",
  card: "hsl(0 0% 100%)",
};

const FALLBACK_PALETTE = [
  "hsl(228 91% 64%)",
  "hsl(177 69% 42%)",
  "hsl(248 72% 65%)",
  "hsl(27 91% 59%)",
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

export default function AIChart({ data, className }) {
  const root = useRef(null);
  const chartRef = useRef(null);

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
    const rows = Array.isArray(data?.rows) ? data.rows.slice(0, 100) : [];
    const seriesInfo = (Array.isArray(data?.series) ? data.series.slice(0, 4) : []).filter((item) => item?.key);
    const styles = getComputedStyle(document.documentElement);
    const foreground = cssColor(styles, "--foreground", FALLBACK_COLORS.foreground);
    const muted = cssColor(styles, "--muted-foreground", FALLBACK_COLORS.muted);
    const border = cssColor(styles, "--border", FALLBACK_COLORS.border);
    const card = cssColor(styles, "--card", FALLBACK_COLORS.card);
    const palette = FALLBACK_PALETTE.map((fallback, index) => cssColor(styles, `--chart-${index + 1}`, fallback));
    palette[0] = cssColor(styles, "--accent", FALLBACK_COLORS.accent);
    const type = ["line", "bar", "area", "pie"].includes(data?.chart_type) ? data.chart_type : "line";
    const money = (value) => `INR ${(Number(value || 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
    const shared = {
      color: palette,
      textStyle: { color: foreground, fontFamily: "Manrope" },
      tooltip: { backgroundColor: card, borderColor: border, textStyle: { color: foreground } },
    };
    const safeSeries = seriesInfo.length ? seriesInfo : [{ key: "value", label: "Value" }];
    const option = type === "pie" ? {
      ...shared,
      animation: false,
      tooltip: { ...shared.tooltip, trigger: "item" },
      legend: { bottom: 0, textStyle: { color: muted } },
      toolbox: { iconStyle: { borderColor: muted }, feature: { saveAsImage: { name: "edvatiq-insight" } } },
      series: [{
        type: "pie", radius: ["42%", "70%"],
        itemStyle: { borderColor: card, borderWidth: 3, borderRadius: 6 },
        data: rows.map((row) => ({ name: String(row.label ?? ""), value: safeNumber(row[safeSeries[0]?.key || "value"]) })),
      }],
    } : {
      ...shared,
      animation: false,
      tooltip: { ...shared.tooltip, trigger: "axis", valueFormatter: safeSeries[0]?.format === "money" ? money : undefined },
      grid: { left: 16, right: 16, top: 24, bottom: 20, containLabel: true },
      toolbox: { iconStyle: { borderColor: muted }, feature: { saveAsImage: { name: "edvatiq-insight" } } },
      xAxis: {
        type: "category", data: rows.map((row) => String(row[data?.x_key || "label"] ?? "")),
        axisLabel: { hideOverlap: true, color: muted }, axisLine: { lineStyle: { color: border } }, axisTick: { show: false },
      },
      yAxis: {
        type: "value", axisLabel: { color: muted, formatter: safeSeries[0]?.format === "money" ? (value) => `INR ${Math.round(value / 100).toLocaleString("en-IN")}` : undefined },
        splitLine: { lineStyle: { color: border, opacity: 0.55 } },
      },
      series: safeSeries.map((item, index) => ({
        name: item.label, type: type === "area" ? "line" : type, smooth: type !== "bar", symbolSize: 7,
        lineStyle: { color: palette[index % palette.length] },
        itemStyle: { color: palette[index % palette.length] },
        areaStyle: type === "area" ? { color: palette[index % palette.length], opacity: 0.16 } : undefined,
        data: rows.map((row) => safeNumber(row[item.key])),
      })),
    };
    chart.setOption(option, { notMerge: true, lazyUpdate: false, silent: true });
    resizeWithoutAnimation(chart);
    return undefined;
  }, [data]);
  return <div ref={root} className={cn("h-72 w-full", className)} role="img" aria-label="Interactive business chart" />;
}
