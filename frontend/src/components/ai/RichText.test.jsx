import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RichText from "./RichText";

test("renders safe assistant formatting without exposing markdown markers", () => {
  const html = renderToStaticMarkup(<RichText>{"The manager is **Gopal Vaarma**.\n- Active manager"}</RichText>);
  expect(html).toContain("<strong>Gopal Vaarma</strong>");
  expect(html).not.toContain("**");
  expect(html).toContain("Active manager");
});
