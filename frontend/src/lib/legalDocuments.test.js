import { legalDocumentDate, withoutMarkdownTitle } from "./legalDocuments";

test("removes only the leading document title from legal markdown", () => {
  expect(withoutMarkdownTitle("# Privacy Policy\n\nIntro.\n\n## Information"))
    .toBe("Intro.\n\n## Information");
  expect(withoutMarkdownTitle("Intro.\n\n## Information"))
    .toBe("Intro.\n\n## Information");
});

test("formats the authoritative effective date", () => {
  expect(legalDocumentDate({ effective_at: "2026-08-13T00:00:00Z" }))
    .toContain("13 August 2026");
  expect(legalDocumentDate(null)).toBe("Not yet effective");
});

