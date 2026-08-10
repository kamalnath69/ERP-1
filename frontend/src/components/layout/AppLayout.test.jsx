import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import {
  PRIMARY_SIDEBAR_WIDTH_CLASS,
  SidebarWalletCard,
} from "@/components/layout/AppLayout";

const wallet = {
  balance_credits: 420,
  available_credits: 395,
  cycle_grant_credits: 500,
  cycle_end: "2026-08-31T00:00:00Z",
};

test("keeps the expanded primary sidebar wider than the secondary rail", () => {
  expect(PRIMARY_SIDEBAR_WIDTH_CLASS).toBe("w-[232px]");
  expect(PRIMARY_SIDEBAR_WIDTH_CLASS).not.toBe("w-[220px]");
});

test("shows the settled AI wallet at the bottom of the expanded sidebar", () => {
  const html = renderToStaticMarkup(<MemoryRouter><SidebarWalletCard wallet={wallet} compact={false} canManage /></MemoryRouter>);

  expect(html).toContain("420 available");
  expect(html).toContain("Renews 31 Aug");
  expect(html).toContain('href="/app/billing"');
  expect(html).toContain("Plan");
});

test("uses a labelled wallet icon in compact mode", () => {
  const html = renderToStaticMarkup(<MemoryRouter><SidebarWalletCard wallet={wallet} compact canManage={false} /></MemoryRouter>);

  expect(html).toContain("420 AI credits available");
  expect(html).not.toContain("View plan");
});

test("shows trial credits as expiring instead of renewing", () => {
  const html = renderToStaticMarkup(<MemoryRouter><SidebarWalletCard
    wallet={wallet}
    plan={{ slug: "trial", subscription_status: "trialing" }}
    compact={false}
    canManage
  /></MemoryRouter>);

  expect(html).toContain("Expires 31 Aug");
  expect(html).not.toContain("Renews 31 Aug");
});
